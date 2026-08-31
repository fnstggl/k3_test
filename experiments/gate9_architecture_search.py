#!/usr/bin/env python3
"""Gate 9D — physics-aware architecture search for native K3 on NAND.

Models PHYSICAL SENSE EVENTS and useful exact-K3 work per sense, composing the
Gate-9A audited mechanisms:
  read modes  : conventional | cr-read (AiF charge recycling) | MWS-assisted
  reducer     : shift-add lanes (Gate 7) | exposed-failbit-count (L3) | export
  dataflow    : token-stationary | expert-stationary (group tokens by expert)
  batching    : B tokens share dense-pool senses; expert reuse via union
  organization: channels x dies x planes; SLC-mode capacity penalty; die size
  precision   : NATIVE K3 only for QUALIFYING results (MXFP4 experts + BF16 dense);
                FP8-dense is a labeled NON-QUALIFYING deviation.

Every candidate is scored in three cases (optimistic / central / adversarial)
and against the primary KPI: complete-system $/million output tokens, subject to
the per-user latency floor. Nothing here invents a constant: mechanism numbers
come from configs/nand_capabilities.yaml + reports/07a; economics from Gate 6 +
the refreshed GPU baseline. Provenance embedded in outputs.

Run: python3 experiments/gate9_architecture_search.py
Outputs: results/gate9_all_candidates.csv, gate9_pareto.csv, gate9_sensitivity.json
"""

import csv
import itertools
import json
import math
import subprocess
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from k3.workload import (nand_bytes_per_token, active_params_per_token,
                         storage_bytes, N_MOE, TOPK, N_EXPERTS, LATENT, EXP_HID)

RESULTS = Path(__file__).resolve().parent.parent / "results"

# ---- fixed K3 quantities (Gate 3, native precision) ----
NB = nand_bytes_per_token()
EXPERT_BYTES_B1 = NB["expert_bytes"]        # 25.83 GB (16 experts, MXFP4)
DENSE_BYTES_BF16 = NB["dense_bytes"]         # 111.1 GB (BF16 dense-active pool)
EXPERT_STORE = N_MOE * N_EXPERTS * 3 * LATENT * EXP_HID * 4.25 / 8   # 1.45 TB
DENSE_STORE = DENSE_BYTES_BF16                                        # ~0.11 TB
MACS_PER_TOKEN = active_params_per_token()
# dynamic side per token (ctx 4096, bf16 KDA state) — DRAM-bound, not NAND
DYN_BYTES = 69 * 6.29e6 * 2 * 0.5 + 24 * 4096 * 576 * 2

# ---- audited mechanism constants (configs/nand_capabilities.yaml) ----
# FACT/L2: Flash-Cosmos SLC-mode tR=22.5us on 48-layer TLC; Z-NAND-class 3us.
# AiF cr-read: verified anchors (see reports/07a); ranges are optimistic/central/adversarial.
CR_READ = {
    # effective-tR multiplier for the recycled fraction of a chain
    "opt": 1 / 2.8, "central": 1 / 2.2, "adv": 1 / 1.6,
    # energy multiplier for recycled reads
    "e_opt": 0.28, "e_central": 0.40, "e_adv": 0.60,
}
CMD_SEQ_S = 290e-9

# sense energy per bit (pJ/bit) — AiF regular ~18.3; range to Flash-Cosmos-implied
SENSE_PJ_PER_BIT = {"opt": 6.0, "central": 11.0, "adv": 18.3}
IO_PJ_PER_BIT = 25.0            # ONFI I/O (Gate 2 calibrated 200 pJ/B)
DRAM_PJ_PER_BIT = 7.5
REDUCER_PJ_PER_MAC = {"opt": 0.2, "central": 0.5, "adv": 1.0}

# ---- economics (Gate 6 complete-appliance model + refreshed GPU baseline) ----
NAND_GB_PRICE = {"opt": 0.10, "central": 0.20, "adv": 0.35}   # $/GB (2026 range)
CTRL_PER_8CH = 30.0            # $/8-ch PIM controller ASIC (F2 periphery)
DRAM_PER_GB = 4.0
CHASSIS = 500.0
PERIPHERY_MARKUP = {"opt": 0.0, "central": 0.15, "adv": 0.30}
ELEC_KWH = 0.10
HOURS_3Y = 3 * 365 * 24
SEC_3Y = HOURS_3Y * 3600
UTIL = {"opt": 0.85, "central": 0.6, "adv": 0.4}   # appliance utilization

# GPU K3 baseline (refreshed in reports/07c from the GPU-baseline audit; central
# defaults below are the pre-audit Gate-6 anchors, overwritten if audit lands).
GPU_BASELINE = {
    "node_tok_s_at_interactive": 2232.0,   # 8xB300, B=64, ~35 tok/s/user (Gate 6)
    "usd_per_Mtok_capex": 2.75,
    "usd_per_Mtok_rental": 5.97,
    "J_per_token": 5.4,
    "best_dollar_per_Mtok": 0.96,          # B=256 (non-interactive)
}


def distinct_experts(batch: int) -> float:
    return N_EXPERTS * (1.0 - (1.0 - TOPK / N_EXPERTS) ** batch)


@dataclass
class Arch:
    name: str
    family: str
    # organization
    channels: int
    dies_per_channel: int
    planes_per_die: int
    page_kb: float
    die_cap_gb: float
    tR_us: float
    slc_mode: bool          # SLC-mode-on-TLC (2x capacity cost)
    # mechanisms
    cr_read: bool
    cr_chain: int           # avg consecutive recycled senses (block/contig limited)
    reducer: str            # 'shiftadd' | 'failbit_count' | 'export'
    lanes: int
    dataflow: str           # 'token' | 'expert_stationary'
    batch: int
    dense_fp8: bool         # NON-QUALIFYING flag
    ecc: float = 0.10
    # evidence/mod bookkeeping
    evidence: str = "L2"
    mod_class: str = "F2"
    unverified: tuple = ()


def eff_tR(a: Arch, case: str) -> float:
    tR = a.tR_us * 1e-6
    if not a.cr_read:
        return tR
    mult = CR_READ[case]
    n = max(1, a.cr_chain)
    # first sense full, (n-1) recycled, averaged over the chain
    return tR * (1 + (n - 1) * mult) / n


# active MAC split per token (Gate 3): dense-active + expert-active
DENSE_MACS = 55.6e9
EXPERT_MACS = 48.6e9
EXPERT_PARAMS_EACH = EXPERT_STORE / (4.25 / 8) / N_EXPERTS   # params per expert, all layers


def evaluate(a: Arch, case: str) -> dict:
    n_dies = a.channels * a.dies_per_channel
    n_planes = n_dies * a.planes_per_die
    raw_cap = n_dies * a.die_cap_gb * 1e9
    # SLC mode halves usable capacity (Flash-Cosmos ESP: 2x cells)
    usable_cap = raw_cap * (0.5 if a.slc_mode else 1.0)
    page_b = a.page_kb * 1024 * (1 - a.ecc)

    dense_store = DENSE_STORE * (8.25 / 16 if a.dense_fp8 else 1.0)
    need = EXPERT_STORE + dense_store
    if usable_cap * 0.9 < need:
        return None    # doesn't fit

    dense_b = DENSE_BYTES_BF16 * (8.25 / 16 if a.dense_fp8 else 1.0)
    B = a.batch

    # --- per-pool sense bytes per wave of B tokens ---
    dense_bytes = dense_b                                   # sensed ONCE, reused x B
    n_distinct = distinct_experts(B)
    expert_bytes = n_distinct * (EXPERT_STORE / N_EXPERTS)  # distinct experts sensed once
    sensed_wave = dense_bytes + expert_bytes

    # --- aggregate sense bandwidth & reducer throughput ---
    tR = eff_tR(a, case)
    agg_sense_bw = n_planes * page_b / tR                   # B/s
    total_lanes = n_planes * a.lanes
    reduce_ops_s = total_lanes * 400e6                      # MAC-equiv/s (shiftadd lanes)
    cmd_overhead = a.dies_per_channel * CMD_SEQ_S

    def pool_time(bytes_sensed, macs_wave):
        t_sense = bytes_sensed / agg_sense_bw
        if a.reducer == "export":
            # weights must leave the die: channel-bound, no local reduce
            t_out = bytes_sensed / (a.channels * 3.2e9)
            return max(t_sense, t_out) + cmd_overhead, "export"
        if a.reducer == "failbit_count":
            # one popcount per sense of a 32-lane block; needs ~popcounts_per_block
            # senses; Gate-4 showed this loses at MXFP4 density -> model as counts
            t_reduce = macs_wave / (n_planes * 400e6)      # 1 count op/plane/cycle
            return max(t_sense, t_reduce) + cmd_overhead, "count"
        # shiftadd lanes: B MACs per sensed weight (reuse), reducer must keep up
        t_reduce = macs_wave / reduce_ops_s
        b = "sense" if t_sense >= t_reduce else "compute"
        return max(t_sense, t_reduce) + cmd_overhead, b

    t_dense, bneck_d = pool_time(dense_bytes, DENSE_MACS * B)
    t_expert, bneck_e = pool_time(expert_bytes, EXPERT_MACS * B)
    t_dyn = DYN_BYTES * B / 102.4e9
    wave_time = t_dense + t_expert + t_dyn
    agg_tok_s = B / wave_time
    per_user_tok_s = 1.0 / wave_time
    tpot_ms = wave_time * 1e3
    leave_frac = 1.0 if a.reducer == "export" else 0.02

    # --- effective sensed bytes/token & senses/token ---
    sensed_per_token = sensed_wave / B
    senses_per_token = sensed_per_token / page_b
    macs_per_sense = MACS_PER_TOKEN * B / max(1.0, sensed_wave / page_b)

    # --- energy per token ---
    e_sense = sensed_per_token * 8 * SENSE_PJ_PER_BIT[case] * 1e-12
    if a.cr_read:
        e_sense *= (CR_READ[f"e_{case}"] if case in ("opt", "central", "adv") else 1.0)
    e_io = (sensed_per_token * leave_frac + sensed_per_token * 0.01) * 8 * IO_PJ_PER_BIT * 1e-12
    e_reduce = MACS_PER_TOKEN * REDUCER_PJ_PER_MAC[case] * 1e-12
    e_dram = DYN_BYTES * 8 * DRAM_PJ_PER_BIT * 1e-12
    j_token = e_sense + e_io + e_reduce + e_dram

    # --- complete-appliance economics ---
    nand_gb = raw_cap / 1e9
    capex = (nand_gb * NAND_GB_PRICE[case] * (1 + PERIPHERY_MARKUP[case])
             + a.channels * CTRL_PER_8CH / 8 * (n_dies)  # controller fanout ~ dies
             + (dense_store + EXPERT_STORE) / 1e9 * 0 + 8 * DRAM_PER_GB * 1024 / 1024
             + CHASSIS)
    # simplify controller term: one 8-ch PIM controller block per 8 channels
    capex = (nand_gb * NAND_GB_PRICE[case] * (1 + PERIPHERY_MARKUP[case])
             + math.ceil(a.channels / 8) * CTRL_PER_8CH
             + 16 * DRAM_PER_GB      # 16 GB DRAM appliance
             + CHASSIS)
    watts = j_token * agg_tok_s + 20.0    # + controller/DRAM overhead
    toks_3y = agg_tok_s * SEC_3Y * UTIL[case]
    opex = watts / 1000 * HOURS_3Y * ELEC_KWH
    usd_per_Mtok = (capex + opex) / toks_3y * 1e6 if toks_3y > 0 else float("inf")

    return {
        "name": a.name, "family": a.family, "case": case,
        "qualifying": not a.dense_fp8,   # native precision only
        "evidence": a.evidence, "mod_class": a.mod_class,
        "unverified": ";".join(a.unverified),
        "batch": B, "dataflow": a.dataflow, "reducer": a.reducer,
        "cr_read": a.cr_read, "slc_mode": a.slc_mode,
        "channels": a.channels, "dies_per_channel": a.dies_per_channel,
        "planes_per_die": a.planes_per_die, "n_planes": n_planes,
        "tR_us": a.tR_us, "eff_tR_us": round(tR * 1e6, 2),
        "agg_tok_s": round(agg_tok_s, 1),
        "per_user_tok_s": round(per_user_tok_s, 1),
        "tpot_ms": round(tpot_ms, 1),
        "usd_per_Mtok": round(usd_per_Mtok, 3),
        "J_per_token": round(j_token, 2),
        "capex_usd": round(capex),
        "wall_W": round(watts),
        "sensed_GB_per_token": round(sensed_per_token / 1e9, 2),
        "senses_per_token_M": round(senses_per_token / 1e6, 2),
        "macs_per_sense": round(macs_per_sense),
        "raw_cap_TB": round(raw_cap / 1e12, 2),
        "usable_cap_TB": round(usable_cap / 1e12, 2),
        # target checks
        "hits_500_agg": agg_tok_s >= 500,
        "hits_25_user": per_user_tok_s >= 25,
        "hits_0p10_dollar": usd_per_Mtok <= 0.10,
    }


if __name__ == "__main__":
    print("gate9 evaluator module — run experiments/gate9_run.py for the search")
