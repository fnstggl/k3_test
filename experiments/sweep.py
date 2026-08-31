#!/usr/bin/env python3
"""Gate 5 — NAND system design-space sweep for K3 decode.

Closed-form steady-state evaluator using the Gate-2-calibrated window model
(period = max(tR_eff, compute, data) + dies/ch x 290ns cmd), cross-checked
against the step-level simulator on Gate-3 configs (agreement reported).

Axes swept:
  cell profile   : SLC-Z (2KB/3us), SLC-mode-on-TLC (16KB/tR sweep, 1/3 density),
                   TLC (16KB/tR sweep), QLC (16KB/tR sweep, +ECC)
  tR             : 1..90 us (per-profile ranges; every value labeled MODEL range)
  organization   : channels x dies/channel x planes/die; die capacity per profile
  overprovision  : F = planes beyond capacity-minimum (more dies than needed)
  PIM            : lanes/plane {1..32} @ {200,400,800} MHz
  page size      : {2,4,8,16} KB
  ECC parity     : {0,10,15,25}%
  batch          : {1,2,4,8,16,32,64} with MoE expert-union amortization
                   D(B) = 896*(1-(1-16/896)^B) distinct experts/layer/batch
  dense precision: BF16 native / FP8 deployment variant

Objectives: tokens/s (throughput), TPOT (latency), J/token, tokens/$/s proxy.
Outputs: results/sweep.csv, results/sweep_summary.json, results/plots/*.png
"""

import csv
import itertools
import json
import math
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from k3.workload import (nand_bytes_per_token, active_params_per_token,
                         K3Precisions, N_MOE, TOPK, N_EXPERTS, LATENT, EXP_HID)
from sim.arithmetic import WFormat

RESULTS = Path(__file__).resolve().parent.parent / "results"
PLOTS = RESULTS / "plots"

CMD_SEQ_S = 290e-9          # ONFI command sequence (Gate 2 grounded)
E_SENSE_J_PER_KB = 89.4e-9  # calibrated (Gate 2); ICC-model alt in Gate 6
E_IO_J_PER_B = 200e-12
E_MAC_J = 1.0e-12
E_DRAM_J_PER_B = 60e-12
DRAM_BW = 102.4e9           # appliance dyn side (Gate 3)

EXPERT_BYTES_1 = nand_bytes_per_token()["expert_bytes"]     # 25.8 GB (B=1)
DENSE_BYTES_BF16 = nand_bytes_per_token()["dense_bytes"]    # 111.1 GB
DENSE_BYTES_FP8 = DENSE_BYTES_BF16 * 8.25 / 16.0
EXPERT_STORE = N_MOE * N_EXPERTS * 3 * LATENT * EXP_HID * 4.25 / 8   # 1.45 TB
DENSE_STORE_BF16 = DENSE_BYTES_BF16                                   # dense pool stored once
MACS_PER_TOKEN = active_params_per_token()
# dynamic side per token (ctx 4096, bf16 KDA state): KDA 69*6.3MB*2*0.5 + KV
DYN_BYTES_PER_TOKEN = 69 * 6.29e6 * 2 * 0.5 + 24 * 4096 * 576 * 2


def distinct_experts(batch: int) -> float:
    return N_EXPERTS * (1.0 - (1.0 - TOPK / N_EXPERTS) ** batch)


def evaluate(profile: str, tR_us: float, page_kb: float, planes_per_die: int,
             die_cap_gb: float, channels: int, dies_per_channel: int,
             lanes: int, freq_mhz: float, ecc: float, batch: int,
             dense_fp8: bool, retry_extra: float = 0.0,
             ch_bw_gbps: float = 3.2) -> dict | None:
    n_dies = channels * dies_per_channel
    n_planes = n_dies * planes_per_die
    capacity = n_dies * die_cap_gb * 1e9
    dense_store = DENSE_STORE_BF16 * (8.25 / 16 if dense_fp8 else 1.0)
    need = EXPERT_STORE + dense_store
    if capacity * 0.9 < need:
        return None
    page_b = page_kb * 1024 * (1 - ecc)
    tR = tR_us * 1e-6 * (1 + retry_extra)

    dense_b = DENSE_BYTES_FP8 if dense_fp8 else DENSE_BYTES_BF16
    exp_b_tok = EXPERT_BYTES_1 * distinct_experts(batch) / (TOPK * batch) * 1.0
    dense_b_tok = dense_b / batch
    bytes_tok = exp_b_tok + dense_b_tok            # sensed bytes per token
    bytes_batch = bytes_tok * batch

    # per-window compute: elems(page,fmt) * batch dots / lanes
    elems_mx = page_b * 8 / 4.25
    elems_dense = page_b * 8 / (8.25 if dense_fp8 else 16.0)
    t_c_mx = elems_mx * batch / (lanes * freq_mhz * 1e6)
    t_c_de = elems_dense * batch / (lanes * freq_mhz * 1e6)
    # input broadcast per window (R=8 reuse), MXFP8 acts on experts
    in_mx_b = elems_mx / 8 * (8.25 / 8) * batch
    in_de_b = elems_dense / 8 * (1.03125 if dense_fp8 else 2.0) * batch
    ch_bw = ch_bw_gbps * 1e9
    cmd = dies_per_channel * CMD_SEQ_S

    def period(t_c, in_b):
        out_b = 8 * 4.0 * batch * dies_per_channel * planes_per_die / 8.0
        data = (in_b + out_b) / ch_bw
        return max(tR, t_c, data) + cmd, (
            "sense" if tR >= max(t_c, data) else
            "compute" if t_c >= data else "channel")

    p_mx, b_mx = period(t_c_mx, in_mx_b)
    p_de, b_de = period(t_c_de, in_de_b)
    # weighted throughput across the two pools
    f_mx = (exp_b_tok * batch) / bytes_batch
    rate_mx = page_b / p_mx * n_planes          # B/s while on expert pages
    rate_de = page_b / p_de * n_planes
    t_batch_nand = (exp_b_tok * batch) / rate_mx + (dense_b_tok * batch) / rate_de
    # dynamic side per batch (per-token state/KV traffic does not amortize)
    t_batch_dyn = DYN_BYTES_PER_TOKEN * batch / DRAM_BW
    # serialization/fill overhead calibrated vs step-simulator (cross-check below)
    t_batch = (t_batch_nand + t_batch_dyn) * FILL_FACTOR
    tok_s = batch / t_batch
    tpot_ms = t_batch * 1e3

    pages_tok = bytes_tok / page_b
    e_sense = bytes_tok / 1024 * E_SENSE_J_PER_KB * (page_kb * 1024 / page_b)
    e_io = (in_mx_b + in_de_b) / batch * pages_tok / 2 * E_IO_J_PER_B  # approx
    e_mac = MACS_PER_TOKEN * E_MAC_J
    e_dram = DYN_BYTES_PER_TOKEN * E_DRAM_J_PER_B
    j_tok = e_sense + e_io + e_mac + e_dram

    return {
        "profile": profile, "tR_us": tR_us, "page_kb": page_kb,
        "planes_per_die": planes_per_die, "die_cap_gb": die_cap_gb,
        "channels": channels, "dies_per_channel": dies_per_channel,
        "n_planes": n_planes, "capacity_TB": round(capacity / 1e12, 2),
        "lanes": lanes, "freq_mhz": freq_mhz, "ecc": ecc, "batch": batch,
        "dense_fp8": dense_fp8,
        "ch_bw_gbps": ch_bw_gbps,
        "tok_s": round(tok_s, 3), "tpot_ms": round(tpot_ms, 1),
        "J_per_token": round(j_tok, 2),
        "bottleneck_expert": b_mx, "bottleneck_dense": b_de,
        "sensed_GB_per_token": round(bytes_tok / 1e9, 1),
        "total_lanes": lanes * n_planes,
    }


# fill/serialization factor: ratio of step-simulator TPOT to closed-form on the
# Gate-3 reference configs (set below after cross-check)
FILL_FACTOR = 1.0


def cross_check() -> float:
    """Compare closed-form vs Gate-3 step simulator on the reference config."""
    from experiments.k3_baseline import znand_slc_2tb, make_system, geom
    from k3.workload import build_token_workload
    from k3.mapping import K3MappingConfig
    from sim.scheduler import simulate_token
    sysc = make_system(znand_slc_2tb(), lanes=4)
    wl = build_token_workload(ctx=4096, mapping=K3MappingConfig(expert_strategy="wide"),
                              nand_geom=geom(sysc.nand))
    r = simulate_token(sysc, wl)
    detailed_ms = r.latency_s * 1e3
    cf = evaluate("slc-z", 3.0, 2.0, 8, 8, 32, 8, 4, 400, 0.0, 1, False)
    ratio = detailed_ms / cf["tpot_ms"]
    return detailed_ms, cf["tpot_ms"], ratio


def profile_space():
    """(profile, page_kb, planes/die, die_cap_gb, tR list, ecc list)
    tR values are MODEL ranges for the cell class, not part specs."""
    return [
        ("slc-z", 2, 8, 8, [1, 3, 10], [0.0]),
        ("slc-mode-tlc", 16, 4, 42.7, [15, 25, 35], [0.0, 0.10]),
        ("slc-mode-tlc-6pl", 16, 6, 42.7, [15, 25, 35], [0.0, 0.10]),
        ("tlc", 16, 4, 128, [40, 50, 60, 90], [0.10, 0.15]),
        ("tlc-8pl", 16, 8, 128, [40, 50, 60], [0.10]),
        ("qlc", 16, 4, 256, [60, 90, 140], [0.15, 0.25]),
        ("hyp-fastpage-tlc", 8, 8, 128, [20, 40, 60], [0.10]),
    ]


def main():
    global FILL_FACTOR
    det, cf, ratio = cross_check()
    print(f"cross-check: detailed {det:.1f}ms vs closed-form {cf:.1f}ms "
          f"-> FILL_FACTOR {ratio:.3f}")
    FILL_FACTOR = ratio

    rows = []
    orgs = [(8, 2), (8, 4), (8, 8), (16, 4), (16, 8), (32, 8), (32, 16), (64, 8)]
    for (prof, pkb, ppd, dcap, tRs, eccs) in profile_space():
        for tR, ecc, (ch, dpc), lanes, batch in itertools.product(
                tRs, eccs, orgs, [1, 4, 8, 16, 32], [1, 4, 8, 16, 32, 64]):
            for fp8 in (False, True):
                r = evaluate(prof, tR, pkb, ppd, dcap, ch, dpc, lanes, 400.0,
                             ecc, batch, fp8)
                if r:
                    rows.append(r)
    # channel-bandwidth axis addendum (ONFI 4.8/2.4 GB/s) on two key profiles
    for (prof, pkb, ppd, dcap, tRs, eccs) in profile_space():
        if prof not in ("slc-z", "slc-mode-tlc-6pl"):
            continue
        for tR, (ch, dpc), lanes, batch, bw in itertools.product(
                tRs, [(16, 8), (32, 8)], [8, 32], [1, 4, 16], [2.4, 4.8]):
            r = evaluate(prof, tR, pkb, ppd, dcap, ch, dpc, lanes, 400.0,
                         eccs[0], batch, True, ch_bw_gbps=bw)
            if r:
                rows.append(r)
    print(f"{len(rows)} feasible points")

    RESULTS.mkdir(exist_ok=True)
    with open(RESULTS / "sweep.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # frontier: max tok/s per (J/token bucket); and best per profile
    best_by_prof = {}
    for r in rows:
        k = r["profile"]
        if k not in best_by_prof or r["tok_s"] > best_by_prof[k]["tok_s"]:
            best_by_prof[k] = r
    # latency-constrained best (single-user-ish: tpot <= 250ms)
    lat_ok = [r for r in rows if r["tpot_ms"] <= 250]
    best_latency = sorted(lat_ok, key=lambda r: -r["tok_s"])[:10]
    # efficiency frontier
    eff = sorted(rows, key=lambda r: r["J_per_token"])[:10]

    summary = {
        "provenance": {"git": subprocess.getoutput("git rev-parse HEAD"),
                       "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "fill_factor": FILL_FACTOR,
                       "cross_check_ms": {"detailed": det, "closed_form": cf}},
        "n_points": len(rows),
        "best_by_profile": best_by_prof,
        "best_tok_s_latency_le_250ms": best_latency,
        "lowest_J_per_token": eff,
    }
    with open(RESULTS / "sweep_summary.json", "w") as f:
        json.dump(summary, f, indent=1)

    for k, r in best_by_prof.items():
        print(f"best {k:18s}: {r['tok_s']:8.2f} tok/s  tpot {r['tpot_ms']:7.1f}ms "
              f"J/tok {r['J_per_token']:6.1f}  B={r['batch']} lanes={r['lanes']} "
              f"{r['channels']}x{r['dies_per_channel']}x{r['planes_per_die']} "
              f"cap {r['capacity_TB']}TB")

    make_plots(rows)


def make_plots(rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    PLOTS.mkdir(exist_ok=True, parents=True)

    # 1: tok/s vs tR by profile (best over other axes, B=1)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    profs = sorted(set(r["profile"] for r in rows))
    for p in profs:
        pts = {}
        for r in rows:
            if r["profile"] == p and r["batch"] == 1 and not r["dense_fp8"]:
                pts[r["tR_us"]] = max(pts.get(r["tR_us"], 0), r["tok_s"])
        if pts:
            xs = sorted(pts)
            ax.plot(xs, [pts[x] for x in xs], marker="o", label=p)
    ax.set_xlabel("tR [us]"), ax.set_ylabel("tok/s (B=1, best org)")
    ax.set_xscale("log"), ax.set_yscale("log")
    ax.grid(alpha=.3), ax.legend(fontsize=7)
    fig.tight_layout(), fig.savefig(PLOTS / "tok_s_vs_tR.png", dpi=130)

    # 2: tok/s vs total planes (all points, colored by profile)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for p in profs:
        xs = [r["n_planes"] for r in rows if r["profile"] == p and r["batch"] == 1]
        ys = [r["tok_s"] for r in rows if r["profile"] == p and r["batch"] == 1]
        ax.scatter(xs, ys, s=6, alpha=.4, label=p)
    ax.set_xlabel("total planes"), ax.set_ylabel("tok/s (B=1)")
    ax.set_xscale("log"), ax.set_yscale("log")
    ax.grid(alpha=.3), ax.legend(fontsize=7)
    fig.tight_layout(), fig.savefig(PLOTS / "tok_s_vs_planes.png", dpi=130)

    # 3: J/token vs batch (best per batch, by profile)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for p in profs:
        pts = {}
        for r in rows:
            if r["profile"] == p:
                b = r["batch"]
                if b not in pts or r["J_per_token"] < pts[b]:
                    pts[b] = r["J_per_token"]
        xs = sorted(pts)
        ax.plot(xs, [pts[x] for x in xs], marker="s", label=p)
    ax.set_xlabel("batch"), ax.set_ylabel("J/token (best)")
    ax.set_xscale("log", base=2), ax.set_yscale("log")
    ax.grid(alpha=.3), ax.legend(fontsize=7)
    fig.tight_layout(), fig.savefig(PLOTS / "J_per_token_vs_batch.png", dpi=130)

    # 4: throughput-latency frontier
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for p in profs:
        xs = [r["tpot_ms"] for r in rows if r["profile"] == p]
        ys = [r["tok_s"] for r in rows if r["profile"] == p]
        ax.scatter(xs, ys, s=5, alpha=.35, label=p)
    ax.set_xlabel("TPOT (batch latency) [ms]"), ax.set_ylabel("tok/s")
    ax.set_xscale("log"), ax.set_yscale("log")
    ax.grid(alpha=.3), ax.legend(fontsize=7)
    fig.tight_layout(), fig.savefig(PLOTS / "throughput_vs_latency.png", dpi=130)
    print("plots written to results/plots/")


if __name__ == "__main__":
    main()
