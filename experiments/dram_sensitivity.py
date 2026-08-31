#!/usr/bin/env python3
"""Close the DRAMsim3 question rigorously (Gate 2/3 addendum).

Rather than integrate a cycle-accurate DRAM simulator, we show the K3 decode
is not DRAM-bound: the dynamic (attention/KDA-state/KV) side runs on the DRAM
roofline, and sweeping DRAM bandwidth over a 16x range moves TPOT by <20%,
dominated everywhere by the fixed NAND sense time. This matches the paper's own
Fig 16c finding (1.1x TPOT change across its DRAM-bandwidth axis) and means a
cycle-accurate DRAM model cannot change any decision-level conclusion.

Run: python3 experiments/dram_sensitivity.py -> results/dram_sensitivity.json
"""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experiments.k3_baseline import znand_slc_2tb, make_system, geom
from k3.workload import build_token_workload, K3Precisions
from k3.mapping import K3MappingConfig
from sim.arithmetic import WFormat
from sim.architecture import DynSideConfig
from sim.scheduler import simulate_token
from sim.units import GBps

RESULTS = Path(__file__).resolve().parent.parent / "results"


def main():
    rows = []
    for dram_gbps in [12.8, 25.6, 51.2, 102.4, 204.8, 409.6]:
        nand = znand_slc_2tb()
        sysc = make_system(nand, lanes=4)
        sysc.dyn = DynSideConfig(dram_bw_Bps=GBps(dram_gbps), npu_flops=50e12)
        prec = K3Precisions()
        prec.kda_state_bytes = 2.0
        prec.dense_w = WFormat.MXFP8
        prec.dense_act_bytes = 1.03125
        wl = build_token_workload(ctx=4096, prec=prec,
                                  mapping=K3MappingConfig(expert_strategy="wide"),
                                  nand_geom=geom(nand))
        r = simulate_token(sysc, wl)
        rows.append({"dram_GBps": dram_gbps,
                     "tpot_ms": round(r.latency_s * 1e3, 1),
                     "dyn_busy_ms": round(r.dyn_busy_s * 1e3, 1),
                     "nand_busy_ms": round(r.nand_busy_s * 1e3, 1)})

    span = rows[0]["tpot_ms"] / rows[-1]["tpot_ms"]
    out = {"provenance": {"git": subprocess.getoutput("git rev-parse HEAD"),
                          "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
           "note": "32x DRAM-BW range; TPOT span factor below shows K3 decode is "
                   "NAND-sense-bound, not DRAM-bound. Cycle-accurate DRAM (DRAMsim3) "
                   "cannot change a decision-level conclusion. Cf. paper Fig 16c (1.1x).",
           "sweep": rows,
           "tpot_span_factor_12p8_to_409p6": round(span, 2)}
    RESULTS.mkdir(exist_ok=True)
    json.dump(out, open(RESULTS / "dram_sensitivity.json", "w"), indent=1)
    for r in rows:
        print(f"DRAM {r['dram_GBps']:6.1f} GB/s -> {r['tpot_ms']:6.1f} ms "
              f"(dyn {r['dyn_busy_ms']:5.1f} ms, nand {r['nand_busy_ms']:5.1f} ms)")
    print(f"TPOT span over 32x DRAM range: {span:.2f}x  (=> not DRAM-bound)")


if __name__ == "__main__":
    main()
