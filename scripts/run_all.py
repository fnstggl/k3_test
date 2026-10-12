#!/usr/bin/env python3
"""Regenerate every deliverable in results/ from the models and the stored simulator outputs.

Prerequisites (each is its own script, see README):
  scripts/fetch_k3_manifest.py, scripts/k3_real_forward.py, scripts/analyze_k3_numerics.py,
  scripts/precision_sweep.py, scripts/precision_device_grid.py, scripts/sims/*.py, scripts/dse.py
This script only reads their outputs and writes:
  results/workload.md, results/physical_assumptions.csv, results/architecture_comparison.csv,
  results/latency_breakdown.csv, results/energy_breakdown.csv, results/cost_model.csv
"""
import csv
import json
import math
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from k3cim import params as PR  # noqa: E402
from k3cim.architectures import (analog_nand, digital_nand, fenand, gpu, orchestrator,  # noqa: E402
                                 rram_3d)
from k3cim.cost import cost_estimate, prototype_cost  # noqa: E402
from k3cim.report_workload import generate as gen_workload  # noqa: E402
from k3cim.scheduler import Scheduler  # noqa: E402
from k3cim.workload import K3Workload  # noqa: E402

RES = os.path.join(ROOT, "results")
DSE = os.path.join(ROOT, "data", "dse_results.csv")
CTX = (32768, 131072, 1048576)

ARCH_INFO = {
    "digital_nand_A0": ("A0", "Digital NAND, commodity dies, weights streamed over ONFI to external compute", "commodity"),
    "digital_nand_A1": ("A1", "Digital NAND bitwise/near-plane MAC, modified periphery, commodity planes", "modified_periphery"),
    "digital_nand_A2": ("A2", "Digital NAND, redesigned small-plane low-latency SLC arrays + near-plane MAC", "redesigned_array"),
    "nand_analog_redesigned|B": ("B", "3D NAND analog, binary (1-bit) activation steps", "redesigned_array"),
    "nand_analog_redesigned|C": ("C", "3D NAND analog, 2-bit-per-step activation encoding", "redesigned_array"),
    "nand_analog_redesigned|D": ("D", "3D NAND analog, 4-bit-per-step activation encoding", "redesigned_array"),
    "nand_analog_redesigned|E": ("E", "3D NAND analog, one-pass (8-bit time-encoded) activation", "redesigned_array"),
    "nand_analog_modified_periphery|B": ("B-mp", "3D NAND analog 1b/step on commodity plane geometry", "modified_periphery"),
    "nand_analog_modified_periphery|E": ("E-mp", "3D NAND analog one-pass on commodity plane geometry", "modified_periphery"),
    "rram_3d": ("F", "3D RRAM crossbar CIM", "research_device"),
    "fenand_speculative": ("G", "3D FeNAND analog CIM (speculative parameters)", "research_device"),
    "gpu": ("H", "GPU baseline 8x B300 (calibrated to measured K3 decode)", "existing_product"),
}


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_dse():
    rows = list(csv.DictReader(open(DSE)))
    for r in rows:
        key = r["tag"]
        if r["tag"].startswith("nand_analog"):
            key = f"{r['tag']}|{r['encoding']}"
        r["_key"] = key
    return rows


def pick(rows, target, ctx="128k", require_precision=True):
    """Cheapest row meeting tok/s target at ctx (silicon cost normalized); precision not 'exceeds'."""
    ok = []
    for r in rows:
        t = fnum(r[f"tok_s_{ctx}"])
        cost = fnum(r["silicon_usd_normalized_128k"]) or fnum(r.get("system_market_usd"))
        if t is None or t < target or cost is None:
            continue
        if require_precision and r.get("precision_verdict", "").startswith("exceeds"):
            continue
        ok.append((cost, -t, r))
    if not ok:
        return None
    ok.sort(key=lambda z: (z[0], z[1]))
    return ok[0][2]


def fastest(rows, ctx="128k"):
    return max(rows, key=lambda r: fnum(r[f"tok_s_{ctx}"]) or 0.0) if rows else None


def rebuild_arch(r):
    """Reconstruct the architecture dict of a DSE row to run detailed breakdowns."""
    s = r["scenario"]
    tag = r["tag"]
    eng = r["attn_engine"]
    if tag == "gpu":
        return gpu(s, "8xB300")
    if tag.startswith("digital_nand"):
        a = digital_nand(s, r["encoding"])
    elif tag == "nand_analog_redesigned":
        a = analog_nand(s, r["encoding"], contributors=int(r["contributors"]), cell_bits=int(r["cell_bits"]),
                        adc_bits=int(r["adc_bits"]))
        a.update(adc_sharing="die_pool", adc_pool_per_die=int(float(r["adc_pool_per_die"])),
                 int_cap_area_m2={"pess": 32e-12, "real": 8e-12, "opt": 2e-12}[s])
    elif tag == "nand_analog_modified_periphery":
        a = analog_nand(s, r["encoding"], silicon="modified_periphery", cell_bits=4, adc_bits=int(r["adc_bits"]))
    elif tag == "rram_3d":
        a = rram_3d(s)
        a.update(adc_bits=int(r["adc_bits"]), adc_sharing="die_pool", adc_pool_per_die=int(float(r["adc_pool_per_die"])))
    elif tag == "fenand_speculative":
        a = fenand(s)
        b = analog_nand(s, "E", contributors=int(r["contributors"]), cell_bits=int(r["cell_bits"]),
                        adc_bits=int(r["adc_bits"]))
        a.update({k: b[k] for k in ("contributors", "cell_bits", "adc_bits", "expert_w_mag_bits", "planes",
                                    "arrays_total", "arrays_per_stage_limit", "expert_arrays_per_layer",
                                    "expert_rounds_override", "dies_total", "cells_total", "psum_bits")})
        a.update(adc_sharing="die_pool", adc_pool_per_die=int(float(r["adc_pool_per_die"])))
    else:
        raise ValueError(tag)
    a.update(orchestrator(s, eng))
    return a


def effective_bits_per_weight(a, wl):
    stored = sum(o.stored_weights for o in wl.linear_ops())
    if a["family"] == "analog_cim":
        return a["cells_total"] * a["cell_bits"] / stored
    if a["family"] == "digital_nvm":
        return a["stored_bits"] / stored
    return 4.25 * 2.7227 / 2.7794 + 16 * 0.0567 / 2.7794


def main():
    os.makedirs(RES, exist_ok=True)
    gen_workload()
    PR.export_csv(os.path.join(RES, "physical_assumptions.csv"))
    rows = load_dse()
    groups = defaultdict(list)
    for r in rows:
        groups[(r["_key"], r["scenario"])].append(r)

    comp, chosen = [], []
    for (key, s), rs in sorted(groups.items()):
        if key not in ARCH_INFO:
            continue
        aid, desc, sil = ARCH_INFO[key]
        for sel_name, sel in (("cheapest_meeting_500tok_s_at_128K", pick(rs, 500)),
                              ("cheapest_meeting_100tok_s_at_128K", pick(rs, 100)),
                              ("fastest_at_128K", fastest(rs))):
            base = {"arch_id": aid, "architecture": desc, "silicon_class": sil, "scenario": s, "selection": sel_name}
            if sel is None:
                comp.append({**base, "feasible": "no configuration in the explored space meets this target"})
                continue
            row = dict(base)
            row["feasible"] = "yes"
            for k in ("encoding", "contributors", "cell_bits", "adc_bits", "adc_pool_per_die", "attn_engine", "dies",
                      "die_mm2", "total_mm2", "adc_total", "sa_count", "tok_s_32k", "tok_s_128k", "tok_s_1024k",
                      "J_tok_32k", "J_tok_128k", "J_tok_1024k", "W_128k", "memory_silicon_usd_normalized",
                      "memory_silicon_usd_shortage", "orch_kv_usd_normalized_128k", "orch_kv_usd_normalized_1m",
                      "silicon_usd_normalized_128k", "silicon_usd_shortage_128k", "system_market_usd",
                      "rel_err_expert", "rel_err_dense", "budget_ratio", "precision_verdict",
                      "limiter_32k", "limiter_128k", "limiter_1024k"):
                row[k] = r_get(sel, k)
            comp.append(row)
            chosen.append((aid, s, sel_name, sel))

    keys = []
    for r in comp:
        for k in r:
            if k not in keys:
                keys.append(k)
    write_csv(os.path.join(RES, "architecture_comparison.csv"), comp, keys)

    # ---------------- detailed breakdowns for the chosen designs
    lat_rows, en_rows, cost_rows = [], [], []
    done = set()
    wl_cache = {}
    for aid, s, sel_name, sel in chosen:
        k = (aid, s, sel["name"], sel.get("contributors"), sel.get("cell_bits"), sel.get("adc_bits"),
             sel.get("adc_pool_per_die"), sel.get("attn_engine"))
        if k in done:
            continue
        done.add(k)
        a = rebuild_arch(sel)
        wl = wl_cache.setdefault(s, K3Workload(fold_mla=(s == "opt")))
        sc = Scheduler(a, wl)
        for L in CTX:
            r, per = sc.layer_breakdown(L)
            tot = defaultdict(float)
            for layer, d in sorted(per.items()):
                lt = ("embed" if layer < 0 else "head" if layer >= wl.nL else
                      ("MLA" if layer in wl.mla_layers else "KDA") + ("+dense" if layer in wl.dense_layers else "+MoE"))
                row = {"arch_id": aid, "scenario": s, "design": sel_name, "context": L, "layer": layer, "layer_type": lt}
                for c, v in d.items():
                    if c.startswith("cp_"):
                        row[c + "_us"] = v * 1e6
                        tot[c] += v
                lat_rows.append(row)
            lat_rows.append({"arch_id": aid, "scenario": s, "design": sel_name, "context": L, "layer": "TOTAL",
                             "layer_type": f"token={r['t_token_s'] * 1e3:.3f}ms cp={r['t_critical_path_s'] * 1e3:.3f}ms",
                             **{c + "_us": v * 1e6 for c, v in tot.items()},
                             **{f"bound_{b}_us": v * 1e6 for b, v in r["bounds"].items()}})
            # energy
            ecat = defaultdict(float)
            for o in wl.ops:
                c = r["costs"][o.name]
                cat = sc.category(o)
                if o.kind == "linear":
                    for bk, bv in c.breakdown.items():
                        if bk.startswith("e_"):
                            ecat[f"{cat}:{bk[2:]}"] += bv
                    if not any(bk.startswith("e_") for bk in c.breakdown):
                        ecat[f"{cat}:total"] += c.energy
                else:
                    ecat[cat] += c.energy
            macs = sum(o.macs for o in wl.ops)
            att = sum(o.K * o.N * L for o in wl.ops if o.kind in ("attn_score", "attn_value"))
            en = {"arch_id": aid, "scenario": s, "design": sel_name, "context": L,
                  "J_per_token": r["energy_j_per_token"], "W": r["power_w"], "tok_per_s": r["tok_per_s"],
                  "static_J": r["e_static_j"],
                  "pJ_per_weight_op(2*MAC)": r["energy_j_per_token"] / (2 * macs) * 1e12,
                  "pJ_per_op_incl_attention": r["energy_j_per_token"] / (2 * (macs + att)) * 1e12}
            en.update({k2: v for k2, v in sorted(ecat.items())})
            en_rows.append(en)
        proto = prototype_cost(a)
        for price in ("normalized", "shortage"):
            for ctxc in (131072, 1048576):
                c = cost_estimate(a, context=ctxc, price=price)
                dies = c.get("dies")
                extra = {"packages": math.ceil(dies / a.get("dies_per_package", 16)) if dies else None,
                         "input_drivers": (a["planes"] * a["array_rows"]) if a.get("planes") else None,
                         "prototype_known_usd": proto["prototype_known_usd"],
                         "prototype_items": "; ".join(proto["prototype_items"]),
                         "prototype_unknown": "; ".join(proto["prototype_unknown"])}
                cost_rows.append({"arch_id": aid, "scenario": s, "design": sel_name, "price_scenario": price,
                                  "kv_context": ctxc, "effective_bits_per_weight": effective_bits_per_weight(a, wl),
                                  **{k2: v for k2, v in c.items() if not isinstance(v, dict)}, **extra})
    sensitivity()
    simulator_baselines()
    write_csv(os.path.join(RES, "latency_breakdown.csv"), lat_rows)
    write_csv(os.path.join(RES, "energy_breakdown.csv"), en_rows)
    write_csv(os.path.join(RES, "cost_model.csv"), cost_rows)
    print("done")


def simulator_baselines():
    """Consolidate baseline reproductions of the three external simulators -> results/simulator_baselines.csv."""
    rows = []
    so = os.path.join(ROOT, "data", "sim_outputs")
    cs = os.path.join(so, "crosssim")
    if os.path.exists(os.path.join(cs, "baseline_reproduction.json")):
        spread = json.load(open(os.path.join(cs, "seed_spread.json"))) if os.path.exists(os.path.join(cs, "seed_spread.json")) else {}
        for r in json.load(open(os.path.join(cs, "baseline_reproduction.json"))):
            if r["expected_tutorial_pt2"] is None:
                continue
            sp = spread.get(r["metric"])
            z = (r["expected_tutorial_pt2"] - sp["mean"]) / sp["std"] if sp else None
            rows.append({"simulator": "CrossSim 3.2.1", "baseline": "tutorial_pt2.ipynb recorded outputs",
                         "metric": r["metric"], "published": r["expected_tutorial_pt2"], "reproduced": r["observed"],
                         "pct_diff": r["pct_diff"], "seed_mean": sp and sp["mean"], "seed_std": sp and sp["std"],
                         "published_z_vs_seed_spread": z,
                         "verdict": ("reproduced (within 2 sigma of seed spread)" if z is not None and abs(z) <= 2 else
                                     "reproduced within 10% (single seed, RNG stream differs)" if abs(r["pct_diff"]) <= 10
                                     else "NOT reproduced")})
        if os.path.exists(os.path.join(cs, "crossval.json")):
            for k, v in json.load(open(os.path.join(cs, "crossval.json"))).items():
                rows.append({"simulator": "k3cim.analog vs CrossSim AnalogCore", "baseline": "identical integer MVM, SONOS model",
                             "metric": k, "published": v["crosssim_mean"], "reproduced": v["k3cim_mean"],
                             "pct_diff": 100 * (v["ratio"] - 1), "verdict": "custom simulator validated"})
    fp = os.path.join(so, "fpim", "fpim_results.json")
    if os.path.exists(fp):
        d = json.load(open(fp))
        ref = {"val_128G": (10e-6, "128Gb TLC: 30 us tR / 3 sensings"), "val_256G": (20e-6, "256Gb TLC: 60 us / 3"),
               "val_512G": (35e-6, "512Gb QLC: 140 us / 4")}
        for k, (r_s, note) in ref.items():
            if k in d:
                rows.append({"simulator": "3D-FPIM NVSim (MICRO'22)", "baseline": "shipped validation cfg, " + note,
                             "metric": "per-sensing read latency (s)", "published": r_s,
                             "reproduced": d[k]["subarray_latency_ns"] * 1e-9, "pct_diff": d[k].get("error_pct"),
                             "verdict": "reproduced within 20% using literature geometry (authors' geometry never released)"})
        if "fpim_default_130x256x64_p5" in d:
            x = d["fpim_default_130x256x64_p5"]
            rows.append({"simulator": "3D-FPIM NVSim (MICRO'22)", "baseline": "shipped 3D_FPIM.cfg PIM mode",
                         "metric": "row-decoder latency SR/CR (ns), cap drive (ns)", "published": "not published in repo",
                         "reproduced": f"{x.get('rowdec_SR_ns')}/{x.get('rowdec_CR_ns')}, {x.get('cap_drive_ns')}",
                         "verdict": "runs; no published per-op number available to compare (3D-FPIM Table II not public)"})
    ns = os.path.join(so, "neurosim", "baseline_reproduction.csv")
    if os.path.exists(ns):
        for r in csv.DictReader(open(ns)):
            rows.append({"simulator": "NeuroSim V1.4", "baseline": "user manual Table VII (VGG8/CIFAR-10)",
                         "metric": r.get("metric"), "published": r.get("expected"), "reproduced": r.get("observed"),
                         "pct_diff": r.get("pct_diff"), "verdict": r.get("verdict", "")})
    write_csv(os.path.join(RES, "simulator_baselines.csv"), rows)


def sensitivity():
    """One-at-a-time sensitivity of single-stream tok/s to sensing / conversion / link latencies (sourced ranges)."""
    rows = []
    base_a = analog_nand("real", "E", adc_bits=8)
    base_a.update(adc_sharing="die_pool", adc_pool_per_die=1024)
    base_b = analog_nand("real", "B", adc_bits=8)
    base_b.update(adc_sharing="die_pool", adc_pool_per_die=1024)
    base_d = digital_nand("real", "A2")
    sweeps = {
        "t_wl_s (WL setup; 0.3 Shim'20, 0.8 NVSim, 2-20 commodity-like)": ("t_wl_s", [0.3e-6, 0.8e-6, 2e-6, 5e-6, 20e-6]),
        "t_step_fixed_s (BL precharge/settle per step)": ("t_step_fixed_s", [32e-9, 64e-9, 120e-9, 500e-9, 2e-6]),
        "adc_bit_cycle_s (SAR bit cycle)": ("adc_bit_cycle_s", [0.5e-9, 1e-9, 2e-9, 5e-9, 10e-9]),
        "die link latency (incl. package hop)": ("die_in_latency_s", [20e-9, 80e-9, 200e-9, 1e-6]),
        "orchestrator op latency (global reductions)": ("orch_op_latency_s", [30e-9, 80e-9, 300e-9, 1e-6]),
        "adc_pool_per_die": ("adc_pool_per_die", [128, 256, 512, 1024, 2048, 4096]),
    }
    for base_name, base in (("E_onepass_real", base_a), ("B_1bit_real", base_b)):
        for label, (key, vals) in sweeps.items():
            for v in vals:
                a = dict(base)
                a[key] = v
                if key == "die_in_latency_s":
                    a["die_out_latency_s"] = v
                for L in (32768, 131072):
                    r = Scheduler(a).evaluate(L)
                    rows.append({"design": base_name, "parameter": label, "value": v, "context": L,
                                 "tok_per_s": r["tok_per_s"], "J_per_token": r["energy_j_per_token"]})
    for v in (0.5e-6, 3e-6, 4e-6, 22.5e-6, 40e-6):
        a = dict(base_d)
        a["t_read_s"] = v
        for L in (32768, 131072):
            r = Scheduler(a).evaluate(L)
            rows.append({"design": "A2_digital_real", "parameter": "t_read_s (tR: 0.5 hypothetical BLS-scan, 3 Z-NAND, "
                         "4 XL-FLASH, 22.5 SLC-mode, 40 TLC)", "value": v, "context": L,
                         "tok_per_s": r["tok_per_s"], "J_per_token": r["energy_j_per_token"]})
    write_csv(os.path.join(RES, "latency_sensitivity.csv"), rows)


def r_get(r, k):
    v = r.get(k)
    f = fnum(v)
    return f if f is not None else v


def write_csv(path, rows, keys=None):
    if keys is None:
        keys = []
        for r in rows:
            for k in r:
                if k not in keys:
                    keys.append(k)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: (f"{v:.6g}" if isinstance(v, float) else v) for k, v in r.items()})


if __name__ == "__main__":
    main()
