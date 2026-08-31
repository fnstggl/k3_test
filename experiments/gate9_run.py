#!/usr/bin/env python3
"""Gate 9D driver: instantiate architecture families, sweep, produce Pareto +
category winners + sensitivity. Uses the calibrated evaluator in
gate9_architecture_search.py (reproduces frozen Gate-6 builds within ~10%).

Run: python3 experiments/gate9_run.py
"""
import csv
import itertools
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experiments.gate9_architecture_search import (
    Arch, evaluate, GPU_BASELINE)

RESULTS = Path(__file__).resolve().parent.parent / "results"

# organization options (channels, dies/ch, planes/die, page_kb, die_cap_gb, tR_us, slc_mode)
# tR values: SLC-mode measured 22.5us (Flash-Cosmos, L2); Z-NAND-class 3us (L2);
# 15us = SLC-mode aggressive; native TLC 50us. All labeled in report.
ORGS = [
    # (name, ch, dpc, ppd, page_kb, cap_gb, tR, slc)
    ("znand-2TB",       32, 8, 8, 2,  8,   3,  True),
    ("znand-4TB",       64, 8, 8, 2,  8,   3,  True),
    ("slcTLC-5.5TB",    16, 8, 6, 16, 42.7,15, True),
    ("slcTLC-22TB",     64, 8, 6, 16, 42.7,15, True),
    ("slcTLC-22TB-22us",64, 8, 6, 16, 42.7,22.5,True),
    ("slcTLC-8pl-29TB", 64, 8, 8, 16, 42.7,15, True),
    ("manySmall-4TB",  128, 8, 4, 4,  4,   6,  True),   # many small dies -> planes/$
    ("manySmall-8TB",  128,16, 4, 4,  4,   6,  True),
    ("nativeTLC-66TB",  64, 8, 8, 16, 128, 50, False),
]

BATCHES = [1, 2, 4, 8, 16, 32, 64, 128, 256]
LANES = [4, 8, 16, 32]


def gen_candidates():
    cands = []
    for (oname, ch, dpc, ppd, pkb, cap, tR, slc) in ORGS:
        for reducer in ("shiftadd", "failbit_count", "export"):
            for cr in (False, True):
                for lanes in LANES:
                    for df in ("token", "expert_stationary"):
                        for B in BATCHES:
                            for fp8 in (False, True):   # fp8 = NON-QUALIFYING
                                # prune: export ignores lanes/reducer detail
                                if reducer == "export" and lanes != 8:
                                    continue
                                if reducer == "failbit_count" and lanes != 8:
                                    continue
                                fam = f"{reducer}{'+cr' if cr else ''}+{df}"
                                # cr_chain: pages per contiguous weight region within a block;
                                # dense pool long chains (~256), experts shorter (~64). Use
                                # a representative chain length; adversarial handled by case.
                                chain = 128 if cr else 1
                                ev = "L2" if not cr else "L3"   # cr-read L2/L3 boundary
                                mc = "F2"
                                if reducer == "failbit_count":
                                    ev, mc = "L3", "F1"
                                unv = []
                                if cr:
                                    unv.append("cr-read-on-this-part")
                                if reducer == "failbit_count":
                                    unv.append("exposed-maskable-failbit-count")
                                a = Arch(
                                    name=f"{oname}|{fam}|L{lanes}|B{B}|{'fp8' if fp8 else 'native'}",
                                    family=fam, channels=ch, dies_per_channel=dpc,
                                    planes_per_die=ppd, page_kb=pkb, die_cap_gb=cap,
                                    tR_us=tR, slc_mode=slc, cr_read=cr, cr_chain=chain,
                                    reducer=reducer, lanes=lanes, dataflow=df, batch=B,
                                    dense_fp8=fp8, ecc=0.0 if slc else 0.10,
                                    evidence=ev, mod_class=mc, unverified=tuple(unv))
                                cands.append(a)
    return cands


def main():
    cands = gen_candidates()
    rows = []
    for a in cands:
        for case in ("opt", "central", "adv"):
            r = evaluate(a, case)
            if r:
                rows.append(r)
    print(f"{len(cands)} candidate archs x3 cases -> {len(rows)} feasible points")

    RESULTS.mkdir(exist_ok=True)
    fields = list(rows[0].keys())
    with open(RESULTS / "gate9_all_candidates.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # central-case, QUALIFYING (native precision) only for headline selection
    central = [r for r in rows if r["case"] == "central" and r["qualifying"]]

    # interactive constraint: per-user >= 25 tok/s (Target 1)
    interactive = [r for r in central if r["per_user_tok_s"] >= 25]
    # Pareto on ($/Mtok down, agg tok/s up) among interactive
    def pareto(pts, xk, yk, xmin=True, ymax=True):
        out = []
        for p in pts:
            dom = False
            for q in pts:
                if q is p:
                    continue
                bx = (q[xk] <= p[xk]) if xmin else (q[xk] >= p[xk])
                by = (q[yk] >= p[yk]) if ymax else (q[yk] <= p[yk])
                sx = (q[xk] < p[xk]) if xmin else (q[xk] > p[xk])
                sy = (q[yk] > p[yk]) if ymax else (q[yk] < p[yk])
                if bx and by and (sx or sy):
                    dom = True
                    break
            if not dom:
                out.append(p)
        return out

    par = pareto(interactive, "usd_per_Mtok", "agg_tok_s")
    par.sort(key=lambda r: r["usd_per_Mtok"])
    with open(RESULTS / "gate9_pareto.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(par)

    # category winners (central case)
    def best(pts, key, reverse=False, filt=lambda r: True):
        pool = [r for r in pts if filt(r)]
        return min(pool, key=lambda r: (key(r) if not reverse else -key(r))) if pool else None

    cats = {
        "best_dollar_qualifying_interactive": best(interactive, lambda r: r["usd_per_Mtok"]),
        "best_dollar_qualifying_any_latency": best(central, lambda r: r["usd_per_Mtok"]),
        "best_aggtoks_interactive": best(interactive, lambda r: -r["agg_tok_s"]),
        "best_firmware_F0": best([r for r in central if r["mod_class"] == "F0"], lambda r: r["usd_per_Mtok"]),
        "best_F1_control_exposure": best([r for r in central if r["mod_class"] == "F1"], lambda r: r["usd_per_Mtok"]),
        "best_F2_tiny_periphery": best([r for r in central if r["mod_class"] == "F2"], lambda r: r["usd_per_Mtok"]),
        "best_energy_qualifying": best(central, lambda r: r["J_per_token"]),
        "best_balanced": best([r for r in interactive if r["usd_per_Mtok"] <= 0.5],
                              lambda r: -r["agg_tok_s"]),
    }

    # targets audit
    hits_t1 = [r for r in central if r["hits_500_agg"] and r["hits_25_user"] and r["hits_0p10_dollar"]]
    hits_t2 = [r for r in central if r["agg_tok_s"] >= 1000 and r["per_user_tok_s"] >= 50
               and r["usd_per_Mtok"] <= 0.05]

    summary = {
        "provenance": {"git": subprocess.getoutput("git rev-parse HEAD"),
                       "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
        "n_candidates": len(cands), "n_points": len(rows),
        "gpu_baseline": GPU_BASELINE,
        "targets": {
            "T1_500agg_25user_0.10dollar_native": len(hits_t1),
            "T2_1000agg_50user_0.05dollar_native": len(hits_t2),
        },
        "pareto_frontier_interactive_native": par[:15],
        "category_winners": {k: v for k, v in cats.items() if v},
    }
    with open(RESULTS / "gate9_sensitivity.json", "w") as f:
        json.dump(summary, f, indent=1)

    print("\n== Targets (central case, native precision) ==")
    print(f"  T1 (>=500 agg, >=25 user, <=$0.10/M): {len(hits_t1)} configs")
    print(f"  T2 (>=1000 agg, >=50 user, <=$0.05/M): {len(hits_t2)} configs")
    print("\n== Category winners (central, native unless noted) ==")
    for k, v in cats.items():
        if v:
            print(f"  {k}: {v['name']}\n     agg={v['agg_tok_s']} user={v['per_user_tok_s']} "
                  f"$/M={v['usd_per_Mtok']} J={v['J_per_token']} mod={v['mod_class']} ev={v['evidence']}")
    print("\n== Interactive Pareto (top by $/Mtok) ==")
    for r in par[:8]:
        print(f"  ${r['usd_per_Mtok']}/M agg={r['agg_tok_s']} user={r['per_user_tok_s']} "
              f"J={r['J_per_token']} {r['name']}")


if __name__ == "__main__":
    main()
