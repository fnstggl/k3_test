#!/usr/bin/env python3
"""'What would it take' table: cheapest explored configuration per target x context x scenario.

Reads data/dse_results.csv, writes results/what_it_takes.csv with, for every
(tok/s target, context, scenario), the cheapest design per architecture family
that meets the target with an analog error not exceeding the MXFP8 budget,
plus the design knobs it needed (encoding, contributors, cell bits, ADC bits,
ADC pool, attention engine) and its limiting resource.
"""
import csv
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DSE = os.path.join(ROOT, "data", "dse_results.csv")
OUT = os.path.join(ROOT, "results", "what_it_takes.csv")


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main():
    rows = list(csv.DictReader(open(DSE)))
    fam = defaultdict(list)
    for r in rows:
        key = r["tag"] + ("|" + r["encoding"] if r["tag"].startswith("nand_analog") else "")
        fam[key].append(r)
    out = []
    for target in (100, 250, 500, 1000):
        for ctx in ("32k", "128k", "1024k"):
            for scen in ("pess", "real", "opt"):
                for key, rs in sorted(fam.items()):
                    best = None
                    for r in rs:
                        if r["scenario"] != scen:
                            continue
                        t = f(r[f"tok_s_{ctx}"])
                        if t is None or t < target:
                            continue
                        if r.get("precision_verdict", "").startswith("exceeds"):
                            continue
                        c = f(r["silicon_usd_normalized_128k"]) or f(r.get("system_market_usd"))
                        if c is None:
                            continue
                        if best is None or c < best[0]:
                            best = (c, r)
                    row = {"target_tok_s": target, "context": ctx, "scenario": scen, "family": key}
                    if best is None:
                        row["feasible"] = "no"
                    else:
                        c, r = best
                        row.update(feasible="yes", silicon_usd_normalized=c,
                                   silicon_usd_shortage=f(r.get("silicon_usd_shortage_128k")),
                                   tok_s=f(r[f"tok_s_{ctx}"]), J_per_token=f(r[f"J_tok_{ctx}"]),
                                   encoding=r["encoding"], contributors=r["contributors"], cell_bits=r["cell_bits"],
                                   adc_bits=r["adc_bits"], adc_pool_per_die=r["adc_pool_per_die"],
                                   attn_engine=r["attn_engine"], dies=r["dies"],
                                   precision_verdict=r.get("precision_verdict"), budget_ratio=r.get("budget_ratio"),
                                   limiter=r.get(f"limiter_{ctx}"))
                    out.append(row)
    keys = []
    for r in out:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(out)
    print("wrote", OUT, len(out))


if __name__ == "__main__":
    main()
