#!/usr/bin/env python3
"""Compact summary of data/dse_results.csv used to write results/final_verdict.md.

For every architecture family x scenario: fastest point per context, and the cheapest point
(silicon cost with KV memory sized for that context) meeting 100 / 500 / 1000 tok/s whose
precision verdict is not 'exceeds_budget', separately for 'within_budget'-only.
Writes results/dse_summary.csv and prints a readable table.
"""
import csv
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DSE = os.path.join(ROOT, "data", "dse_results.csv")
OUT = os.path.join(ROOT, "results", "dse_summary.csv")
COST = {"32k": "silicon_usd_normalized_32k", "128k": "silicon_usd_normalized_128k", "1024k": "silicon_usd_normalized_1m"}
FAM = {"digital_nand_A0": "A0", "digital_nand_A1": "A1", "digital_nand_A2": "A2", "rram_3d": "F",
       "fenand_speculative": "G", "gpu": "H"}


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def fam(r):
    if r["tag"] == "nand_analog_redesigned":
        return r["encoding"]
    if r["tag"] == "nand_analog_modified_periphery":
        return r["encoding"] + "-mp"
    return FAM[r["tag"]]


def cost(r, ctx):
    return f(r.get(COST[ctx])) or f(r.get("silicon_usd_normalized_128k")) or f(r.get("system_market_usd"))


def desc(r):
    if r["family"] == "analog_cim":
        return (f"{fam(r)} C={r['contributors']} {r['cell_bits']}b-cell ADC{r['adc_bits']} "
                f"pool{r['adc_pool_per_die'] or r.get('adcs_per_array')} {r['attn_engine']}")
    return f"{fam(r)} {r['attn_engine']}"


def main():
    rows = list(csv.DictReader(open(DSE)))
    groups = {}
    for r in rows:
        groups.setdefault((fam(r), r["scenario"]), []).append(r)
    out = []
    for (fm, s), rs in sorted(groups.items()):
        for ctx in ("32k", "128k", "1024k"):
            best = max(rs, key=lambda r: f(r[f"tok_s_{ctx}"]) or 0)
            out.append({"family": fm, "scenario": s, "context": ctx, "selection": "fastest",
                        "tok_s": f(best[f"tok_s_{ctx}"]), "usd": cost(best, ctx), "J_tok": f(best[f"J_tok_{ctx}"]),
                        "W": f(best[f"W_{ctx}"]), "dies": best["dies"], "precision": best.get("precision_verdict"),
                        "budget_ratio": best.get("budget_ratio"), "limiter": best[f"limiter_{ctx}"], "design": desc(best)})
            for target in (100, 500, 1000):
                for strict in (False, True):
                    ok = [r for r in rs if (f(r[f"tok_s_{ctx}"]) or 0) >= target and cost(r, ctx) is not None
                          and not r.get("precision_verdict", "").startswith("exceeds")
                          and (not strict or r.get("precision_verdict") in ("within_budget", "exact_digital"))]
                    sel = f"cheapest>={target}" + ("_within" if strict else "")
                    if not ok:
                        out.append({"family": fm, "scenario": s, "context": ctx, "selection": sel, "tok_s": None})
                        continue
                    b = min(ok, key=lambda r: (cost(r, ctx), -(f(r[f"tok_s_{ctx}"]) or 0)))
                    out.append({"family": fm, "scenario": s, "context": ctx, "selection": sel,
                                "tok_s": f(b[f"tok_s_{ctx}"]), "usd": cost(b, ctx), "J_tok": f(b[f"J_tok_{ctx}"]),
                                "W": f(b[f"W_{ctx}"]), "dies": b["dies"], "precision": b.get("precision_verdict"),
                                "budget_ratio": b.get("budget_ratio"), "limiter": b[f"limiter_{ctx}"],
                                "mem_usd": f(b.get("memory_silicon_usd_normalized")), "design": desc(b)})
    keys = []
    for r in out:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for r in out:
            w.writerow({k: (f"{v:.5g}" if isinstance(v, float) else v) for k, v in r.items()})
    print("wrote", OUT, len(out))


if __name__ == "__main__":
    main()
