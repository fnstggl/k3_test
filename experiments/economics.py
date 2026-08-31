#!/usr/bin/env python3
"""Gate 6 — power + economics: K3-on-NAND vs GPU serving.

Every input is labeled FACT (sourced), MODEL (derived), or RANGE (sensitivity).
The GPU comparison is a separate, clearly-labeled section — it is not part of
the architecture simulation.

Sources (fetched 2026-08-31, see reports/04_power_cost_go_no_go.md):
  [S1] runpod.io K3 technical FAQ: 8xB300 (288GB, ~2.3TB) fits K3 weights+KV;
       K3 checkpoint ~1.56TB MXFP4 (matches our derived 1.56TB).
  [S2] B200 street/node pricing: HGX B200 8-GPU node ~$450k; B200 ~1kW/GPU;
       on-demand rental $4-8/GPU-hr (specialist clouds, Aug 2026).
  [S3] TrendForce/DRAMeXchange: 512Gb TLC wafer spot ~$17.9 (~$0.28/GB),
       2026 NAND shortage (+65% MoM Jan'26). Range used: $0.10-0.35/GB.
  [S4] Moonshot API list price ~$3/M in, $15/M out (reported; anchor only).
Energy coefficients: Gate 2 calibration (sense 42-89 pJ/B range from the
ICC-vs-calculator tension; ONFI I/O 200 pJ/B; DRAM 60 pJ/B).
"""

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from k3.workload import nand_bytes_per_token
from experiments.sweep import distinct_experts, EXPERT_BYTES_1, DENSE_BYTES_BF16, DENSE_BYTES_FP8

RESULTS = Path(__file__).resolve().parent.parent / "results"

HOURS_3Y = 3 * 365 * 24
SEC_3Y = HOURS_3Y * 3600
ELEC_KWH = 0.10          # $/kWh (RANGE 0.05-0.15)

# ---------------- NAND-PIM builds (Gate 5 frontier, MODEL) ----------------
# (name, raw_TB, tok_s, tpot_ms, J_tok_central, J_tok_low, n_ctrl8ch, note)
NAND_BUILDS = [
    ("A: 5.5TB slc-mode-TLC 16x8x6, B=1", 5.5, 8.0, 125, 10.4, 5.8, 2,
     "commodity 1Tb TLC dies in SLC mode; single-stream"),
    ("B: 22TB slc-mode-TLC 64x8x6, B=4", 21.9, 50.7, 79, 5.0, 2.9, 8,
     "4 concurrent streams; 3072 planes"),
    ("C: 2TB SLC-Z 32x8x8, B=1", 2.0, 8.7, 115, 8.2, 4.6, 4,
     "Z-NAND-class dies (niche part; price extra-uncertain)"),
]

NAND_GB_PRICE = {"low": 0.10, "central": 0.28, "high": 0.35}   # [S3] RANGE
CTRL_PRICE = 30.0        # $ per 8-ch PIM controller ASIC (MODEL RANGE 15-60)
DRAM_128GB = 520.0       # $ (2026 DDR5 ~ $4/GB, RANGE 2.5-6)
CHASSIS = 500.0          # board/PSU/NIC (MODEL)
PERIPHERY_MARKUP = {"low": 0.0, "central": 0.15, "high": 0.30}
# custom page-buffer periphery: amortized NRE+margin as fraction of die cost (RANGE)


def nand_build_economics(name, raw_tb, tok_s, tpot_ms, j_tok, j_tok_low, nctrl, note):
    out = {"build": name, "tok_s": tok_s, "tpot_ms": tpot_ms, "note": note,
           "J_per_token": {"central": j_tok, "low": j_tok_low}}
    toks_3y = tok_s * SEC_3Y
    for sc in ("low", "central", "high"):
        dies = raw_tb * 1e3 * NAND_GB_PRICE[sc] * (1 + PERIPHERY_MARKUP[sc])
        capex = dies + nctrl * CTRL_PRICE + DRAM_128GB + CHASSIS
        watts = j_tok * tok_s + 15.0     # + controller/DRAM overhead (MODEL)
        opex_power = watts / 1000 * HOURS_3Y * ELEC_KWH
        usd_per_M = (capex + opex_power) / toks_3y * 1e6
        out[sc] = {"capex_usd": round(capex), "wall_W": round(watts),
                   "usd_per_Mtok_3y": round(usd_per_M, 2)}
    return out


# ---------------- GPU reference (labeled separately, MODEL on FACT anchors) --
GPU_NODE_PRICE = {"low": 450e3, "central": 550e3, "high": 650e3}  # 8xB300 [S1,S2]
GPU_NODE_KW = {"low": 10.0, "central": 12.0, "high": 14.0}        # [S2] + host
GPU_HBM_TBs = 8 * 8.0     # 8x ~8TB/s HBM3e (B300 class, MODEL)
GPU_EFF = {"roofline": 1.0, "central": 0.6, "poor": 0.4}          # kernel eff RANGE
GPU_RENT_HR = {"low": 4.0, "central": 6.0, "high": 8.0}           # $/GPU-hr [S2]
GPU_HBM_PJ_PER_BIT = 6.0   # HBM3e-class device+PHY (MODEL RANGE 4-8)


def gpu_bytes_per_step(batch, dense_fp8=False):
    dense = DENSE_BYTES_FP8 if dense_fp8 else DENSE_BYTES_BF16
    exp = EXPERT_BYTES_1 / 16.0 * distinct_experts(batch)  # bytes per LAYER-set scaled
    return dense + exp


def gpu_economics(batch, eff_key="central", dense_fp8=False):
    bytes_step = gpu_bytes_per_step(batch, dense_fp8)
    bw = GPU_HBM_TBs * 1e12 * GPU_EFF[eff_key]
    t_step = bytes_step / bw
    user_tok_s = 1.0 / t_step
    node_tok_s = batch / t_step
    out = {"batch": batch, "eff": GPU_EFF[eff_key], "dense_fp8": dense_fp8,
           "bytes_per_step_GB": round(bytes_step / 1e9, 1),
           "user_tok_s": round(user_tok_s, 1),
           "node_tok_s": round(node_tok_s, 1)}
    for sc in ("low", "central", "high"):
        kw = GPU_NODE_KW[sc]
        j_tok = kw * 1000 / node_tok_s
        toks_3y = node_tok_s * SEC_3Y
        capex_per_M = GPU_NODE_PRICE[sc] / toks_3y * 1e6
        power_per_M = kw * HOURS_3Y * ELEC_KWH / toks_3y * 1e6
        rent_per_M = 8 * GPU_RENT_HR[sc] / (node_tok_s * 3600) * 1e6
        out[sc] = {"J_per_token": round(j_tok, 2),
                   "usd_per_Mtok_capex3y": round(capex_per_M + power_per_M, 2),
                   "usd_per_Mtok_rental": round(rent_per_M, 2)}
    return out


def main():
    nand = [nand_build_economics(*b) for b in NAND_BUILDS]
    gpu = []
    for b in (1, 8, 64, 256):
        gpu.append(gpu_economics(b, "central", dense_fp8=False))
    gpu_roof = gpu_economics(256, "roofline", dense_fp8=False)
    gpu_poor = gpu_economics(64, "poor", dense_fp8=False)

    # threshold matrix: NAND central vs GPU central at comparable latency class
    def ratio(a, b):
        return round(b / a, 1) if a > 0 else None
    matrix = []
    for nb in nand:
        for gb in gpu:
            matrix.append({
                "nand": nb["build"], "gpu_batch": gb["batch"],
                "nand_user_tok_s": nb["tok_s"], "gpu_user_tok_s": gb["user_tok_s"],
                "J_ratio_gpu_over_nand": ratio(nb["J_per_token"]["central"],
                                               gb["central"]["J_per_token"]),
                "usd_ratio_capex_gpu_over_nand": ratio(
                    nb["central"]["usd_per_Mtok_3y"],
                    gb["central"]["usd_per_Mtok_capex3y"]),
                "usd_ratio_rental_gpu_over_nand": ratio(
                    nb["central"]["usd_per_Mtok_3y"],
                    gb["central"]["usd_per_Mtok_rental"]),
            })

    out = {"provenance": {"git": subprocess.getoutput("git rev-parse HEAD"),
                          "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
           "nand_builds": nand, "gpu_reference": gpu,
           "gpu_roofline_b256": gpu_roof, "gpu_poor_b64": gpu_poor,
           "threshold_matrix": matrix,
           "api_price_anchor_usd_per_Mtok_out": 15.0}
    RESULTS.mkdir(exist_ok=True)
    with open(RESULTS / "economics.json", "w") as f:
        json.dump(out, f, indent=1)

    print("== NAND builds (central scenario) ==")
    for nb in nand:
        print(f"{nb['build']:42s} {nb['tok_s']:6.1f} tok/s {nb['tpot_ms']:5.0f}ms "
              f"{nb['J_per_token']['central']:5.1f} J/tok  capex ${nb['central']['capex_usd']:>6}  "
              f"${nb['central']['usd_per_Mtok_3y']:>7}/Mtok  {nb['central']['wall_W']}W")
    print("== GPU 8xB300 node (central eff=0.6) ==")
    for gb in gpu:
        print(f"B={gb['batch']:<4d} user {gb['user_tok_s']:7.1f} tok/s  node "
              f"{gb['node_tok_s']:8.1f} tok/s  {gb['central']['J_per_token']:6.1f} J/tok  "
              f"${gb['central']['usd_per_Mtok_capex3y']:>7}/Mtok capex  "
              f"${gb['central']['usd_per_Mtok_rental']:>7}/Mtok rental")
    print("== threshold matrix (ratios >10 needed for GO) ==")
    for m in matrix:
        print(f"{m['nand'][:28]:28s} vs GPU B={m['gpu_batch']:<4d} "
              f"J x{m['J_ratio_gpu_over_nand']:>6}  $capex x{m['usd_ratio_capex_gpu_over_nand']:>6}  "
              f"$rent x{m['usd_ratio_rental_gpu_over_nand']:>6}")


if __name__ == "__main__":
    main()
