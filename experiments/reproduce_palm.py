#!/usr/bin/env python3
"""Gate 2 — reproduce LLM-on-the-Palm from first principles.

Nothing in this script hard-codes the paper's TPOT. Inputs:
  - model geometry (GPT-3 6.7B/13B from Brown et al.; 30B treated as OPT-30B, see notes)
  - paper NAND organization (Table I): 8ch x 4die x 8planes, 2KB page, tR=3us, 3.2GB/s
  - ONFI command-sequence timing from MQSim's ONFI_Channel_NVDDR2 defaults
    (t_CS=20, t_WC=25, t_WB=100, t_RR=20 ns -> 290ns per die per window)
  - LPDDR5-6400 x64 DRAM = 51.2 GB/s for KV streaming (paper Fig 16c default range)

Scheduling model variants:
  ideal      : no command overhead, full overlap (physics lower bound)
  primary    : 1 ONFI cmd sequence per die per window serialized with the sense
               window (MQSim-style die scheduling); input broadcast per die,
               overlapped with sensing
  pessimistic: input broadcast per die NOT overlapped with sensing

Acceptance: primary within 10% of the paper's Fig 10 TPOTs and Fig 16a capacity
sensitivity. Outputs results/palm_reproduction.json.
"""

import json
import math
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim.architecture import SystemConfig, DynSideConfig, EnergyParams
from sim.nand import NandConfig
from sim.arithmetic import PimConfig, WFormat
from sim.mapping import MappingPolicy
from sim.workload import gpt3_token_workload
from sim.scheduler import simulate_token
from sim.energy import token_energy
from sim.units import GBps

RESULTS = Path(__file__).resolve().parent.parent / "results"

# Paper targets (references/llm_on_the_palm_parameters.yaml) — used ONLY for
# comparison, never as model inputs.
PAPER = {
    "tpot_ms": {
        "6.7B": {(128, 128): 105, (128, 1024): 109, (1024, 128): 114, (1024, 1024): 118},
        "13B": {(128, 128): 204, (128, 1024): 211, (1024, 128): 218, (1024, 1024): 225},
        "30B": {(128, 128): 477, (128, 1024): 489, (1024, 128): 501, (1024, 1024): 513},
    },
    "capacity_ms": {"6.7B": {128: 185, 256: 112, 512: 75, 1024: 56},
                    "13B": {128: 359, 256: 215, 512: 142, 1024: 106},
                    "30B": {128: 834, 256: 495, 512: 326, 1024: 241}},
    "internal_bw_GBps": 117.0,
    "energy_J": {"6.7B": 1.5, "13B": 2.8, "30B": 6.6},
    "energy_split": {"io_pct": 21.8, "pe_pct": 1.3},
}

MODELS = {
    # (hidden, layers, ffn_mult, source note)
    "6.7B": dict(hidden=4096, n_layers=32, ffn_mult=4,
                 note="GPT-3 6.7B (Brown et al. Table 2.1)"),
    "13B": dict(hidden=5140, n_layers=40, ffn_mult=4,
                note="GPT-3 13B (Brown et al. Table 2.1: d=5140, 40L)"),
    "30B": dict(hidden=7168, n_layers=48, ffn_mult=4,
                note="'GPT-3 30B' does not exist; OPT-30B geometry (d=7168, 48L) per paper Fig 8 OPT labels"),
}

IN_OUT = [(128, 128), (128, 1024), (1024, 128), (1024, 1024)]


def make_system(variant: str, capacity_gb: int = 256) -> SystemConfig:
    dies = int(capacity_gb // 8)
    nand = NandConfig()  # paper defaults
    nand.dies_per_channel = max(1, dies // nand.n_channels)
    sysc = SystemConfig(nand=nand, pim=PimConfig(),
                        dyn=DynSideConfig(dram_bw_Bps=GBps(51.2), npu_flops=17e12),
                        mapping=MappingPolicy(plane_fraction=1.0, input_scope='channel',
                                              rows_per_page=1, export_every_page=True),
                        energy=EnergyParams())
    if variant == "ideal":
        nand.cmd_seqs_per_die_window = 0
    elif variant == "primary":
        nand.cmd_seqs_per_die_window = 1
        nand.cmd_serializes_with_sense = True
    elif variant == "pessimistic":
        nand.cmd_seqs_per_die_window = 1
        nand.cmd_serializes_with_sense = True
        sysc.mapping.channel_overlaps_sense = False
    else:
        raise ValueError(variant)
    return sysc


def avg_tpot_s(sysc: SystemConfig, model: dict, n_in: int, n_out: int,
               include_lm_head=False, lm_head_on_nand=True) -> tuple[float, object]:
    """Average TPOT over the decode of n_out tokens (ctx grows n_in..n_in+n_out).
    Attention cost is linear in ctx -> evaluate at mean ctx (exact for the mean)."""
    mean_ctx = n_in + (n_out - 1) / 2.0
    wl = gpt3_token_workload(hidden=model["hidden"], n_layers=model["n_layers"],
                             ffn_mult=model["ffn_mult"], ctx=int(round(mean_ctx)),
                             include_lm_head=include_lm_head,
                             lm_head_on_nand=lm_head_on_nand)
    res = simulate_token(sysc, wl)
    return res.latency_s, res


def pct_err(model_val, paper_val):
    return 100.0 * (model_val - paper_val) / paper_val


def main():
    out = {"provenance": provenance(), "variants": {}, "acceptance": {}}

    # ---- TPOT vs paper Fig 10 for the three scheduling variants ----
    for variant in ("ideal", "primary", "pessimistic"):
        v = {"tpot_ms": {}, "err_pct": {}}
        for mname, m in MODELS.items():
            v["tpot_ms"][mname] = {}
            v["err_pct"][mname] = {}
            for (i, o) in IN_OUT:
                sysc = make_system(variant)
                t, _ = avg_tpot_s(sysc, m, i, o)
                v["tpot_ms"][mname][f"{i}/{o}"] = round(t * 1e3, 1)
                v["err_pct"][mname][f"{i}/{o}"] = round(
                    pct_err(t * 1e3, PAPER["tpot_ms"][mname][(i, o)]), 1)
        out["variants"][variant] = v

    # ---- capacity sensitivity (primary) vs Fig 16a ----
    cap = {"model_ms": {}, "err_pct": {}}
    for mname, m in MODELS.items():
        cap["model_ms"][mname] = {}
        cap["err_pct"][mname] = {}
        for cgb in (128, 256, 512, 1024):
            sysc = make_system("primary", capacity_gb=cgb)
            # paper Fig 16a plots the 4-config average
            ts = [avg_tpot_s(sysc, m, i, o)[0] for (i, o) in IN_OUT]
            t_ms = sum(ts) / len(ts) * 1e3
            cap["model_ms"][mname][cgb] = round(t_ms, 1)
            cap["err_pct"][mname][cgb] = round(
                pct_err(t_ms, PAPER["capacity_ms"][mname][cgb]), 1)
    out["capacity_sensitivity"] = cap

    # ---- effective internal bandwidth (primary, 6.7B) ----
    sysc = make_system("primary")
    _, res = avg_tpot_s(sysc, MODELS["6.7B"], 128, 128)
    eff_bw = res.internal_weight_bytes / res.nand_busy_s
    out["internal_bw_GBps"] = {"model": round(eff_bw / 1e9, 1),
                               "paper": PAPER["internal_bw_GBps"],
                               "err_pct": round(pct_err(eff_bw / 1e9, 117.0), 1)}

    # ---- LM-head placement sensitivity (paper is silent; document impact) ----
    lm = {}
    for mode, kw in {"excluded": dict(include_lm_head=False),
                     "on_nand": dict(include_lm_head=True, lm_head_on_nand=True),
                     "on_npu_dram": dict(include_lm_head=True, lm_head_on_nand=False)}.items():
        t, _ = avg_tpot_s(make_system("primary"), MODELS["6.7B"], 128, 128, **kw)
        lm[mode] = round(t * 1e3, 1)
    out["lm_head_sensitivity_ms"] = lm

    # ---- energy (primary), calibrated coefficients documented in report ----
    en = {}
    for mname, m in MODELS.items():
        sysc = make_system("primary")
        ts = []
        _, res = avg_tpot_s(sysc, m, 128, 128)
        eb = token_energy(sysc, res)
        icc_sysc = make_system("primary")
        icc_sysc.energy.page_read_model = "icc"
        eb_icc = token_energy(icc_sysc, res)
        en[mname] = {
            "total_J_calibrated": round(eb.total_J, 2),
            "paper_J": PAPER["energy_J"][mname],
            "err_pct": round(pct_err(eb.total_J, PAPER["energy_J"][mname]), 1),
            "split": {k: round(v, 3) for k, v in eb.as_dict().items()},
            "total_J_icc_model": round(eb_icc.total_J, 2),
        }
    out["energy"] = en

    # ---- acceptance ----
    prim = out["variants"]["primary"]["err_pct"]
    tpot_errs = [abs(e) for md in prim.values() for e in md.values()]
    cap_errs = [abs(e) for md in cap["err_pct"].values() for e in md.values()]
    out["acceptance"] = {
        "tpot_max_abs_err_pct": max(tpot_errs),
        "tpot_all_within_10pct": max(tpot_errs) <= 10.0,
        "capacity_max_abs_err_pct": max(cap_errs),
        "capacity_all_within_10pct": max(cap_errs) <= 10.0,
        "internal_bw_within_10pct": abs(out["internal_bw_GBps"]["err_pct"]) <= 10.0,
    }

    RESULTS.mkdir(exist_ok=True)
    with open(RESULTS / "palm_reproduction.json", "w") as f:
        json.dump(out, f, indent=1)

    # console summary
    print("=== Gate 2: LLM-on-the-Palm reproduction (primary model) ===")
    for mname in MODELS:
        row = out["variants"]["primary"]["tpot_ms"][mname]
        errs = out["variants"]["primary"]["err_pct"][mname]
        print(f"{mname}: " + "  ".join(f"{k}:{v}ms({errs[k]:+.1f}%)" for k, v in row.items()))
    print("capacity 6.7B:", cap["model_ms"]["6.7B"], "err%:", cap["err_pct"]["6.7B"])
    print("internal BW:", out["internal_bw_GBps"])
    print("energy 6.7B:", en["6.7B"]["total_J_calibrated"], "J vs paper", 1.5,
          "| icc-model:", en["6.7B"]["total_J_icc_model"], "J")
    print("acceptance:", out["acceptance"])


def provenance():
    def sh(cmd):
        try:
            return subprocess.check_output(cmd, shell=True, text=True).strip()
        except Exception:
            return "n/a"
    return {
        "git_commit": sh("git rev-parse HEAD"),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": sh("uname -srm"),
        "python": sys.version.split()[0],
    }


if __name__ == "__main__":
    main()
