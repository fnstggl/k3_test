#!/usr/bin/env python3
"""Gate 4 — minimum stock-NAND primitive search for K3 dot products.

Question: what is the minimum set of NAND-internal primitives that lets K3's
fixed-weight dot products stay inside NAND (no intermediate weight export)?

Capability ladder (classification of each capability is in CLASSES below and
justified in reports/03_minimum_primitive.md):

  A0_EXPORT   read + export raw pages; all arithmetic outside the die (ISP).
  A1_BOOL     A0 + COTS-demonstrated bulk boolean ops (MCFlash, Flash-Cosmos).
              Analysis: these compute f(stored, stored) per bitline; a GEMV
              needs f(stored, runtime) and a cross-bitline SUM -> contributes
              nothing to K3 GEMV; performance == A0 (proof in report).
  A2_CMP_CNT  A0 + hypothetical exposed fail-bit counter (latch XNOR + count
              across the page), the strongest stock-adjacent reduction
              primitive we can postulate (BABOL target). Bit-serial popcount
              dot products; MX block scales force per-32-block counting.
  B_SHIFT     A0 + lateral shift in the page buffer (new wiring, no adder).
              Shift alone cannot sum -> perf == A0 for GEMV (kept for table).
  C_ADD       B + SIMD add between latch words (lateral carry chain).
              Bit-serial multiply (E2M1 = 2-bit shift + conditional add) +
              log-depth in-buffer reduction; partials exported per page.
  D_ACC       C + retained per-block accumulators across pages (no per-page
              partial export; accumulate a row chunk across its page sequence).
  E_MAC       full per-plane digital MAC/reduce lanes (Gate 3's 4-lane PU).

Output: results/primitive_search.csv + console Pareto summary.
"""

import csv
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim.nand import NandConfig
from sim.arithmetic import PimConfig, WFormat
from sim.units import GBps
from k3.workload import nand_bytes_per_token, active_params_per_token

RESULTS = Path(__file__).resolve().parent.parent / "results"

# --- capability classification (sources in report) ---
CLASSES = {
    "A0_EXPORT": "KNOWN STOCK",
    "A1_BOOL": "LITERATURE-DEMONSTRATED ON COTS (MCFlash arXiv:2605.05119; "
               "Flash-Cosmos MICRO'22) — inapplicable to GEMV (see report)",
    "A2_CMP_CNT": "VENDOR/UNDOCUMENTED POSSIBILITY (program-verify fail-bit "
                  "counters exist in silicon; on-demand exposed count is the "
                  "BABOL question)",
    "B_SHIFT": "REQUIRES NEW SILICON (no lateral bitline datapath in stock "
               "page buffers)",
    "C_ADD": "REQUIRES NEW SILICON (tiny: SIMD latch adder)",
    "D_ACC": "REQUIRES NEW SILICON (tiny: adder + retained accumulators)",
    "E_MAC": "REQUIRES NEW SILICON (small: 4 MAC lanes/plane, Palm-class x4)",
}

# --- NAND profiles (Gate 3 baselines) ---


def slc_2tb() -> NandConfig:
    n = NandConfig()
    n.n_channels, n.dies_per_channel, n.planes_per_die = 32, 8, 8
    n.page_bytes, n.tR_us, n.bits_per_cell = 2048, 3.0, 1
    n.die_capacity_bytes = 8 * 1024**3
    return n


def tlc_2tb() -> NandConfig:
    n = NandConfig()
    n.n_channels, n.dies_per_channel, n.planes_per_die = 8, 2, 4
    n.page_bytes, n.tR_us, n.bits_per_cell = 16384, 50.0, 3
    n.die_capacity_bytes = 128 * 1024**3
    n.ecc_parity_overhead = 0.10
    return n


# --- K3 per-token quantities (native precisions: MXFP4 experts, BF16 dense) ---
NB = nand_bytes_per_token()
K3_NAND_BYTES = NB["total"]          # 137.0 GB weight bytes / token
K3_MACS = active_params_per_token()  # ~104.2e9 MACs on NAND-resident weights
PARTIAL_B = 4.0                      # FP32 partial export width
AVG_BITS_PER_PARAM = K3_NAND_BYTES * 8 / K3_MACS   # ~10.5 (mixed MXFP4/BF16)


def channel_page_export_rate_Bps(n: NandConfig) -> float:
    """Stock read+export ceiling per channel: one cmd sequence + data-out per
    page (MQSim-validated structure, Gate 2)."""
    t = n.cmd_seq_time_s + 30e-9 + n.usable_page_bytes / n.channel_bw_Bps
    return n.usable_page_bytes / t


def sense_rate_Bps(n: NandConfig, overhead_passes_s: float = 0.0) -> float:
    """Aggregate internal sense bandwidth with per-window compute overhead
    (period = max(tR, passes) + dies/ch*cmd, calibrated Gate 2 model)."""
    period = max(n.effective_tR_s, overhead_passes_s) \
        + n.dies_per_channel * n.cmd_seq_time_s
    return n.usable_page_bytes / period * n.n_planes


def result_row(set_name, profile_name, n, tok_s, leave_B, enter_B,
               passes_per_page, acc, notes) -> dict:
    return {
        "set": set_name, "class": CLASSES[set_name], "nand": profile_name,
        "tok_per_s": round(tok_s, 3),
        "tpot_ms": round(1e3 / tok_s, 1) if tok_s > 0 else float("inf"),
        "bytes_leaving_nand_per_token_GB": round(leave_B / 1e9, 3),
        "bytes_entering_nand_per_token_GB": round(enter_B / 1e9, 3),
        "internal_sense_GB_per_token": round(K3_NAND_BYTES / 1e9, 1),
        "passes_per_page": passes_per_page,
        "accumulator": acc,
        "planes": n.n_planes,
        "notes": notes,
    }


def eval_export(set_name, profile_name, n: NandConfig) -> dict:
    """A0/A1/B_SHIFT: every weight byte leaves the die; controller computes.
    Rate = min(aggregate export ceiling, host-side ingest) — controller NPU
    assumed adequate (generous to the stock case)."""
    agg = min(channel_page_export_rate_Bps(n) * n.n_channels,
              sense_rate_Bps(n))          # cannot export faster than sensing
    tok_s = agg / K3_NAND_BYTES
    enter = 0.002e9  # commands only, negligible
    note = ("all weights exported; needs ~%.0f GFLOPS in controller"
            % (2 * K3_MACS * tok_s / 1e9))
    if set_name == "A1_BOOL":
        note = ("boolean ops need both operands pre-stored + give no "
                "cross-bitline sum -> zero GEMV benefit; " + note)
    if set_name == "B_SHIFT":
        note = "shift without add cannot reduce; " + note
    return result_row(set_name, profile_name, n, tok_s, K3_NAND_BYTES, enter,
                      0, "none (external)", note)


def eval_cmp_count(profile_name, n: NandConfig, t_count_us: float) -> dict:
    """A2: bit-serial popcount dot products via hypothetical exposed
    XNOR+fail-bit-count primitive.

    Layout: weights bit-plane-separated. For an E2M1 weight (4 bit-planes incl
    sign handled as plane) x E4M3 act (8 bit-planes broadcast into a latch):
    per weight-page-set: 4x8 = 32 count ops IF one count could cover the whole
    page. MX block scaling (E8M0 per 32 elems) forces counting per 32-column
    block -> blocks_per_page independent masked counts (a fail-bit counter
    reports one number per operation)."""
    page_positions = n.usable_page_bytes * 8          # bit positions per page
    blocks = page_positions / 32.0
    counts_per_pageset = 4 * 8 * blocks               # per 4-bitplane weight set
    t_counts = counts_per_pageset * t_count_us * 1e-6
    # act bit-plane loads: 8 planes x page over channel per column window,
    # shared per die group; minor vs counts — folded into note.
    sense_t = 4 * n.effective_tR_s                    # sense 4 weight bitplanes
    weights_per_pageset = page_positions              # one weight per position
    rate_per_plane = weights_per_pageset / (sense_t + t_counts)
    agg_rate = rate_per_plane * n.n_planes            # weights/s
    tok_s = agg_rate / K3_MACS
    # counts leave as ~3B each
    leave = counts_per_pageset * 3.0 * (K3_MACS / weights_per_pageset)
    enter = 8 * n.usable_page_bytes * (K3_MACS / weights_per_pageset)
    return result_row(
        "A2_CMP_CNT", profile_name, n, tok_s, leave, enter,
        f"{int(4*8*blocks)} counts (t_count={t_count_us}us)",
        "external (counts)",
        f"MX 32-block scales force {int(blocks)} masked counts per bitplane "
        f"pair; BABOL must find sub-{t_count_us}us count op for this to move")


def eval_lateral(set_name, profile_name, n: NandConfig, pass_ns: float,
                 retained: bool) -> dict:
    """C_ADD / D_ACC: SIMD shift+add lanes over the page buffer.
    Bit-serial MXFP4xMXFP8 multiply: E2M1 magnitude in {0,.5,1,1.5,2,3,4,6} =
    (k*a)>>1 with k in {0..4,6,8,12} -> per act, <=2 shift-adds; process 4-bit
    weight in ~8 passes + per-32-block reduction tree log2(32)=5 + inter-block
    FP32 accumulate ~4 passes -> ~17 passes; BF16 dense pool bit-serial is
    wider (~16b acts): ~40 passes (conservative).
    Retained accumulators (D) drop per-page partial export."""
    passes_mx, passes_bf16 = 17, 40
    # weighted mix by page share: experts 25.8GB, dense 111.1GB
    f_mx = NB["expert_bytes"] / K3_NAND_BYTES
    passes = f_mx * passes_mx + (1 - f_mx) * passes_bf16
    t_passes = passes * pass_ns * 1e-9
    rate = sense_rate_Bps(n, overhead_passes_s=t_passes)
    tok_s = rate / K3_NAND_BYTES
    pages_per_token = K3_NAND_BYTES / n.usable_page_bytes
    rows_per_page = 8
    leave = pages_per_token * rows_per_page * PARTIAL_B
    if retained:
        leave /= 8.0     # export once per row sweep (~8-page chunks)
    enter = pages_per_token * 0.25 * n.usable_page_bytes  # input broadcast ~25%
    return result_row(set_name, profile_name, n, tok_s, leave, enter,
                      round(passes, 1),
                      "per-32-block int18 + FP32 chain"
                      + (" (retained)" if retained else " (export/page)"),
                      f"pass={pass_ns}ns SIMD latch op; sense-bound iff "
                      f"passes*t_pass <= tR ({t_passes*1e6:.1f}us vs "
                      f"{n.effective_tR_s*1e6:.0f}us)")


def eval_mac(profile_name, n: NandConfig, lanes: int) -> dict:
    """E_MAC: digital lanes consuming the page buffer (Gate 3 model)."""
    elems_mx = n.usable_page_bytes * 8 / 4.25
    elems_bf = n.usable_page_bytes * 8 / 16
    f_mx = NB["expert_bytes"] / K3_NAND_BYTES
    t_mx = elems_mx / (lanes * 400e6)
    t_bf = elems_bf / (lanes * 400e6)
    t_c = f_mx * t_mx + (1 - f_mx) * t_bf
    rate = sense_rate_Bps(n, overhead_passes_s=t_c)
    tok_s = rate / K3_NAND_BYTES
    pages_per_token = K3_NAND_BYTES / n.usable_page_bytes
    leave = pages_per_token * 8 * PARTIAL_B
    enter = pages_per_token * 0.25 * n.usable_page_bytes
    return result_row("E_MAC", profile_name, n, tok_s, leave, enter,
                      f"{lanes} lanes @400MHz",
                      "FP32 (Palm-style) or int18+FP32 block chain",
                      f"compute/page {t_c*1e6:.1f}us vs tR "
                      f"{n.effective_tR_s*1e6:.0f}us")


def main():
    rows = []
    for pname, n in (("slc-2TB-2048pl", slc_2tb()), ("tlc-2TB-64pl", tlc_2tb())):
        rows.append(eval_export("A0_EXPORT", pname, n))
        rows.append(eval_export("A1_BOOL", pname, n))
        for tc in (1.0, 10.0, 100.0):
            r = eval_cmp_count(pname, n, tc)
            r["set"] = f"A2_CMP_CNT(t={tc}us)"
            r["class"] = CLASSES["A2_CMP_CNT"]
            rows.append(r)
        rows.append(eval_export("B_SHIFT", pname, n))
        for pn in (50.0, 200.0):
            r = eval_lateral("C_ADD", pname, n, pn, retained=False)
            r["set"] = f"C_ADD(pass={int(pn)}ns)"
            r["class"] = CLASSES["C_ADD"]
            rows.append(r)
            r = eval_lateral("D_ACC", pname, n, pn, retained=True)
            r["set"] = f"D_ACC(pass={int(pn)}ns)"
            r["class"] = CLASSES["D_ACC"]
            rows.append(r)
        for lanes in (1, 4):
            r = eval_mac(pname, n, lanes)
            r["set"] = f"E_MAC({lanes}lane)"
            rows.append(r)

    RESULTS.mkdir(exist_ok=True)
    with open(RESULTS / "primitive_search.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with open(RESULTS / "primitive_search_provenance.json", "w") as f:
        json.dump({"git": subprocess.getoutput("git rev-parse HEAD"),
                   "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "k3_nand_bytes_per_token_GB": K3_NAND_BYTES / 1e9,
                   "k3_macs_per_token_G": K3_MACS / 1e9}, f, indent=1)

    print(f"{'set':22s} {'nand':16s} {'tok/s':>8s} {'leave GB':>9s} {'class':40s}")
    for r in rows:
        print(f"{r['set']:22s} {r['nand']:16s} {r['tok_per_s']:8.3f} "
              f"{r['bytes_leaving_nand_per_token_GB']:9.3f} {r['class'][:40]:40s}")


if __name__ == "__main__":
    main()
