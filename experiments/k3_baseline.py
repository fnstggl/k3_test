#!/usr/bin/env python3
"""Gate 3 — K3 decode baseline on NAND-PIM (Palm-class architecture scaled up).

Baseline systems (all parameters explicit; Gate 5 sweeps them):
  znand-slc-2TB : 32ch x 8die x 8pl = 2048 planes, 2KB page, tR=3us SLC no-ECC
                  (Z-NAND-class cell, paper-calibrated command model)
  tlc-2TB       : 8ch x 2die x 4pl = 64 planes of 1Tb TLC-class dies, 16KB page,
                  tR=50us, 10% ECC parity (commodity high-density profile;
                  every number a sensitivity variable, see configs/nand/)

Dynamic side (appliance-class): DRAM 102.4 GB/s (dual-channel DDR5/LPDDR5X-6400
class), NPU 50 TFLOPS-class for attention/gating. KDA state FP32 (bf16 variant).

Outputs results/k3_baseline.json with per-component ms attribution.
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim.architecture import SystemConfig, DynSideConfig, EnergyParams
from sim.nand import NandConfig
from sim.arithmetic import PimConfig
from sim.mapping import MappingPolicy
from sim.scheduler import simulate_token
from sim.energy import token_energy
from sim.units import GBps
from k3.workload import (build_token_workload, assert_published_totals,
                         nand_bytes_per_token, storage_bytes, K3Precisions,
                         ResidencyPolicy)
from k3.mapping import K3MappingConfig, capacity_required_bytes
from sim.workload import TokenWorkload

RESULTS = Path(__file__).resolve().parent.parent / "results"

CATEGORIES = [
    ("kda_proj", r"\.kda\.(qkvg|o)$"),
    ("kda_state", r"\.kda\.state$"),
    ("mla_proj", r"\.mla\.(q_a|kv_a|gate|q_b|kv_b|o)$"),
    ("mla_attn", r"\.mla\.attn$"),
    ("attnres", r"\.attnres$"),
    ("moe_pre", r"\.moe\.(router|wdown|shared_gu)$"),
    ("experts", r"\.moe\.exp"),
    ("moe_shared_d", r"\.moe\.shared_d"),
    ("moe_wup", r"\.moe\.wup$"),
    ("dense_ffn", r"L1\.dense\."),
    ("lm_head", r"lm_head"),
]


def categorize(name: str) -> str:
    for cat, pat in CATEGORIES:
        if re.search(pat, name):
            return cat
    return "other"


STEP_CATEGORIES = [
    ("kda_proj", r"\.kda\.(qkvg|o)$"),
    ("kda_state", r"\.kda\.state$"),
    ("mla_proj", r"\.mla\.(a|q_b|kv_b_absorbed|o)$"),
    ("mla_attn", r"\.mla\.attn$"),
    ("attnres", r"\.attnres$"),
    ("moe_pre", r"\.moe\.pre$"),
    ("experts", r"\.moe\.experts"),
    ("moe_shared_d", r"\.moe\.shared_d$"),
    ("moe_wup", r"\.moe\.wup$"),
    ("dense_ffn", r"L1\.dense\."),
    ("lm_head", r"lm_head"),
]


def categorize_step(name: str) -> str:
    for cat, pat in STEP_CATEGORIES:
        if re.search(pat, name):
            return cat
    return "other"


def znand_slc_2tb() -> NandConfig:
    n = NandConfig()                      # paper-calibrated timing/cmd model
    n.n_channels = 32
    n.dies_per_channel = 8
    n.planes_per_die = 8
    n.page_bytes = 2048
    n.die_capacity_bytes = 8 * 1024**3
    n.tR_us = 3.0
    n.bits_per_cell = 1
    return n


def tlc_2tb() -> NandConfig:
    n = NandConfig()
    n.n_channels = 8
    n.dies_per_channel = 2
    n.planes_per_die = 4
    n.page_bytes = 16384
    n.die_capacity_bytes = 128 * 1024**3
    n.tR_us = 50.0
    n.bits_per_cell = 3
    n.ecc_parity_overhead = 0.10
    return n


def make_system(nand: NandConfig, lanes: int = 1) -> SystemConfig:
    return SystemConfig(
        nand=nand, pim=PimConfig(lanes_per_plane=lanes),
        dyn=DynSideConfig(dram_bw_Bps=GBps(102.4), npu_flops=50e12),
        mapping=MappingPolicy(plane_fraction=1.0, input_scope='channel'),
        energy=EnergyParams(),
    )


def geom(nand: NandConfig) -> dict:
    return {"n_channels": nand.n_channels, "dies_per_channel": nand.dies_per_channel,
            "planes_per_die": nand.planes_per_die}


def run_config(name: str, nand: NandConfig, ctx: int, prec: K3Precisions,
               res: ResidencyPolicy, mapping: K3MappingConfig,
               lanes: int = 1, kda_state_bytes: float = None) -> dict:
    if kda_state_bytes is not None:
        prec.kda_state_bytes = kda_state_bytes
    sysc = make_system(nand, lanes=lanes)
    wl = build_token_workload(ctx=ctx, prec=prec, res=res, mapping=mapping,
                              nand_geom=geom(nand))
    t0 = time.time()
    r = simulate_token(sysc, wl)
    eb = token_energy(sysc, r)
    cat_ms = {}
    for sname, st_s in r.step_times:
        c = categorize_step(sname)
        cat_ms[c] = cat_ms.get(c, 0.0) + st_s * 1e3
    # capacity check
    st = storage_bytes(prec)
    cap_needed = capacity_required_bytes(st, mapping)
    fits = cap_needed <= nand.capacity_bytes * 0.9
    return {
        "config": name, "ctx": ctx,
        "tpot_ms": round(r.latency_s * 1e3, 1),
        "tok_per_s": round(1.0 / r.latency_s, 2),
        "category_ms": {k: round(v, 2) for k, v in sorted(cat_ms.items(),
                                                          key=lambda kv: -kv[1])},
        "nand_busy_ms": round(r.nand_busy_s * 1e3, 1),
        "dyn_busy_ms": round(r.dyn_busy_s * 1e3, 1),
        "pages_sensed_M": round(r.pages_sensed / 1e6, 2),
        "internal_weight_GB": round(r.internal_weight_bytes / 1e9, 1),
        "bytes_entering_nand_MB": round(r.bytes_entering_nand / 1e6, 1),
        "bytes_leaving_nand_MB": round(r.bytes_leaving_nand / 1e6, 1),
        "dram_GB": round(r.dram_bytes / 1e9, 2),
        "energy_J": {k: round(v, 3) for k, v in eb.as_dict().items()},
        "capacity_needed_TB": round(cap_needed / 1e12, 2),
        "capacity_TB": round(nand.capacity_bytes / 1e12, 2),
        "fits": fits,
        "sim_wall_s": round(time.time() - t0, 1),
    }


def main():
    checks = assert_published_totals()
    out = {"provenance": provenance(),
           "param_check": {"total_T": round(checks["total"] / 1e12, 4),
                           "active_B": round(checks["active"] / 1e9, 2),
                           "total_err_pct": round(100 * checks["total_err"], 2),
                           "active_err_pct": round(100 * checks["active_err"], 2)},
           "nand_bytes_per_token_GB": {k: round(v / 1e9, 2)
                                       for k, v in nand_bytes_per_token().items()},
           "runs": []}

    from sim.arithmetic import WFormat
    grouped_map = K3MappingConfig(expert_strategy="grouped", n_expert_groups=16)
    wide_map = K3MappingConfig(expert_strategy="wide")
    fp8 = K3Precisions(dense_w=WFormat.MXFP8, dense_act_bytes=1.03125)
    runs = [
        # (name, nand, ctx, prec, res, mapping, lanes, kda_state_bytes)
        ("znand-slc-2TB/palm-pu-grouped", znand_slc_2tb(), 4096, K3Precisions(),
         ResidencyPolicy(), grouped_map, 1, None),
        ("znand-slc-2TB/palm-pu-wide", znand_slc_2tb(), 4096, K3Precisions(),
         ResidencyPolicy(), wide_map, 1, None),
        ("znand-slc-2TB/4lanes-wide", znand_slc_2tb(), 4096, K3Precisions(),
         ResidencyPolicy(), wide_map, 4, None),
        ("znand-slc-2TB/4lanes-wide-fp8dense", znand_slc_2tb(), 4096, fp8,
         ResidencyPolicy(), wide_map, 4, None),
        ("znand-slc-2TB/4lanes-wide-fp8dense-bf16state", znand_slc_2tb(), 4096,
         K3Precisions(dense_w=WFormat.MXFP8, dense_act_bytes=1.03125),
         ResidencyPolicy(), wide_map, 4, 2.0),
        ("znand-slc-2TB/replicate2-grouped", znand_slc_2tb(), 4096, K3Precisions(),
         ResidencyPolicy(),
         K3MappingConfig(expert_strategy="grouped", n_expert_groups=16,
                         expert_replication=2), 1, None),
        ("znand-slc-2TB/4lanes-wide-ctx65536", znand_slc_2tb(), 65536, K3Precisions(),
         ResidencyPolicy(), wide_map, 4, None),
        ("tlc-2TB/palm-pu-grouped", tlc_2tb(), 4096, K3Precisions(),
         ResidencyPolicy(), grouped_map, 1, None),
        ("tlc-2TB/16lanes-wide", tlc_2tb(), 4096, K3Precisions(),
         ResidencyPolicy(), wide_map, 16, None),
        ("znand-slc-2TB/experts-only-nand-dense-dram", znand_slc_2tb(), 4096,
         K3Precisions(), ResidencyPolicy(dense_pool="dram"), wide_map, 4, None),
    ]
    for name, nand, ctx, prec, res, mapping, lanes, ksb in runs:
        try:
            out["runs"].append(run_config(name, nand, ctx, prec, res, mapping,
                                          lanes=lanes, kda_state_bytes=ksb))
        except AssertionError as e:
            out["runs"].append({"config": name, "error": str(e)})

    RESULTS.mkdir(exist_ok=True)
    with open(RESULTS / "k3_baseline.json", "w") as f:
        json.dump(out, f, indent=1)

    print("param check:", out["param_check"])
    print("nand bytes/token:", out["nand_bytes_per_token_GB"])
    for r in out["runs"]:
        if "error" in r:
            print(f"{r['config']}: ERROR {r['error']}")
            continue
        top = list(r["category_ms"].items())[:4]
        print(f"{r['config']}: {r['tpot_ms']}ms ({r['tok_per_s']} tok/s) "
              f"fits={r['fits']} top: {top}")


def provenance():
    def sh(cmd):
        try:
            return subprocess.check_output(cmd, shell=True, text=True).strip()
        except Exception:
            return "n/a"
    return {"git_commit": sh("git rev-parse HEAD"),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "host": sh("uname -srm")}


if __name__ == "__main__":
    main()
