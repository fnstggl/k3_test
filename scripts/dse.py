#!/usr/bin/env python3
"""Design-space exploration: cheapest configuration meeting each single-stream target.

For every architecture family the knobs that trade latency against silicon
cost are swept; each point gets
  * tok/s at 32K / 128K / 1M context (critical path + resource bounds),
  * J/token and W,
  * silicon area, die count and volume silicon cost (normalized + shortage),
  * an analog-accuracy estimate from the real-tensor precision study
    (results/precision_sweep.csv + data/sim_outputs/crosssim/device_grid.json).
Writes data/dse_results.csv
"""
import csv
import itertools
import json
import math
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from k3cim.architectures import ATTN_ENGINES, analog_nand, digital_nand, fenand, gpu, orchestrator, rram_3d  # noqa: E402
from k3cim.cost import cost_estimate  # noqa: E402
from k3cim.precision_model import PrecisionModel  # noqa: E402
from k3cim.scheduler import Scheduler  # noqa: E402
from k3cim.workload import K3Workload  # noqa: E402

CTX = (32768, 131072, 1048576)
OUT = os.path.join(ROOT, "data", "dse_results.csv")


def evaluate(arch, wl, pm, tag):
    rows = []
    sc = Scheduler(arch, wl)
    res = {L: sc.evaluate(L) for L in CTX}
    c_norm = cost_estimate(arch, context=131072, price="normalized")
    c_short = cost_estimate(arch, context=131072, price="shortage")
    c_1m = cost_estimate(arch, context=1048576, price="normalized")
    prec = pm.estimate(arch) if arch["family"] == "analog_cim" else {"rel_err_expert": 0.0, "rel_err_dense": 0.0,
                                                                     "budget_ratio": 0.0, "precision_verdict": "exact_digital"}
    r = {"tag": tag, "name": arch["name"], "family": arch["family"], "silicon": arch.get("silicon"),
         "scenario": arch["scenario"], "attn_engine": arch.get("attn_engine"),
         "encoding": arch.get("encoding", arch.get("variant", "")), "contributors": arch.get("contributors"),
         "cell_bits": arch.get("cell_bits", arch.get("bits_per_cell")), "adc_bits": arch.get("adc_bits"),
         "adc_sharing": arch.get("adc_sharing", "per_plane"), "adc_pool_per_die": arch.get("adc_pool_per_die"),
         "adcs_per_array": arch.get("adcs_per_array"),
         "dies": c_norm.get("dies"), "die_mm2": c_norm.get("die_mm2"), "total_mm2": c_norm.get("total_mm2"),
         "adc_total": c_norm.get("adc_total"), "sa_count": c_norm.get("sa_count"),
         "memory_silicon_usd_normalized": c_norm.get("memory_silicon_usd"),
         "memory_silicon_usd_shortage": c_short.get("memory_silicon_usd"),
         "orch_kv_usd_normalized_128k": c_norm.get("orchestrator_and_kv_usd"),
         "orch_kv_usd_normalized_1m": c_1m.get("orchestrator_and_kv_usd"),
         "silicon_usd_normalized_128k": c_norm.get("silicon_usd"),
         "silicon_usd_shortage_128k": c_short.get("silicon_usd"),
         "system_market_usd": c_norm.get("system_market_usd"),
         **prec}
    for L in CTX:
        k = f"{L // 1024}k"
        r[f"tok_s_{k}"] = res[L]["tok_per_s"]
        r[f"J_tok_{k}"] = res[L]["energy_j_per_token"]
        r[f"W_{k}"] = res[L]["power_w"]
        r[f"limiter_{k}"] = max([("critical_path", res[L]["t_critical_path_s"])] + list(res[L]["bounds"].items()),
                                key=lambda kv: kv[1])[0]
    rows.append(r)
    return rows


def main():
    quick = "--quick" in sys.argv
    pm = PrecisionModel()
    wls = {s: K3Workload(fold_mla=(s == "opt")) for s in ("pess", "real", "opt")}
    rows = []
    t0 = time.time()
    engines = ["edge", "mid", "mid2", "mid3", "high", "xhigh", "sram_a", "sram_b", "sram_c"]
    for s in ("pess", "real", "opt"):
        wl = wls[s]
        # ---------------- analog NAND (redesigned arrays), B/C/D/E
        grid = itertools.product("BCDE", (32, 64, 128, 256), (1, 2, 3, 4), (6, 8, 10, 12),
                                 (128, 512, 2048), engines)
        if quick:
            grid = itertools.product("BE", (32, 128), (4,), (8,), (512,), ("mid",))
        for enc, C, cb, ab, pool, eng in grid:
            a = analog_nand(s, enc, contributors=C, cell_bits=cb, adc_bits=ab)
            a.update(adc_sharing="die_pool", adc_pool_per_die=pool, int_cap_area_m2={"pess": 32e-12, "real": 8e-12, "opt": 2e-12}[s])
            a.update(orchestrator(s, eng))
            rows += evaluate(a, wl, pm, "nand_analog_redesigned")
        # ---------------- analog NAND, modified periphery on commodity planes (per-plane ADCs)
        for enc, eng in itertools.product("BE", engines):
            a = analog_nand(s, enc, silicon="modified_periphery", cell_bits=4, adc_bits=9 if enc == "B" else 12)
            a.update(orchestrator(s, eng))
            rows += evaluate(a, wl, pm, "nand_analog_modified_periphery")
        # ---------------- FeNAND (speculative)
        for C, cb, ab, pool, eng in itertools.product((64, 128, 256), (2, 3, 4), (8, 10), (512, 2048), engines):
            a = fenand(s)
            b = analog_nand(s, "E", contributors=C, cell_bits=cb, adc_bits=ab)
            a.update({k: b[k] for k in ("contributors", "cell_bits", "adc_bits", "expert_w_mag_bits", "planes",
                                        "arrays_total", "arrays_per_stage_limit", "expert_arrays_per_layer",
                                        "expert_rounds_override", "dies_total", "cells_total", "psum_bits")})
            a.update(adc_sharing="die_pool", adc_pool_per_die=pool, int_cap_area_m2=b.get("int_cap_area_m2", 8e-12))
            a.update(orchestrator(s, eng))
            rows += evaluate(a, wl, pm, "fenand_speculative")
        # ---------------- 3D RRAM
        for pool, ab, eng in itertools.product((256, 1024, 4096), (8, 10), engines):
            a = rram_3d(s)
            a.update(adc_bits=ab, adc_sharing="die_pool", adc_pool_per_die=pool)
            a.update(orchestrator(s, eng))
            rows += evaluate(a, wl, pm, "rram_3d")
        # ---------------- digital NAND
        for v in ("A0", "A1", "A2"):
            for eng in engines:
                a = digital_nand(s, v)
                a.update(orchestrator(s, eng))
                rows += evaluate(a, wl, pm, f"digital_nand_{v}")
        # ---------------- GPU
        rows += evaluate(gpu(s, "8xB300"), wl, pm, "gpu")
        print(f"scenario {s} done: {len(rows)} rows ({time.time() - t0:.0f}s)", flush=True)
    keys = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print("wrote", OUT, len(rows))


if __name__ == "__main__":
    main()
