"""Generate results/gpu_comparison.md (matched K3 single-stream decode workload)."""
from __future__ import annotations

import csv
import os

from .architectures import analog_nand, digital_nand, gpu, orchestrator
from .scheduler import Scheduler, prefill_seconds, speculative_tok_per_s

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def generate(path=os.path.join(ROOT, "results", "gpu_comparison.md")):
    bench = list(csv.DictReader(open(os.path.join(ROOT, "data", "sources", "llm_decode_benchmarks_sourced.csv"))))
    comp = list(csv.DictReader(open(os.path.join(ROOT, "results", "architecture_comparison.csv"))))
    L = []
    w = L.append
    w("# GPU comparison — matched Kimi K3 single-stream decode\n")
    w("Same model (the released 2.8T K3 checkpoint: MXFP4 experts + BF16 dense), batch = 1 user, decode. "
      "GPU numbers are **measured** (SemiAnalysis InferenceX, OpenZeka, Artificial Analysis; see "
      "`data/sources/llm_decode_benchmarks_sourced.csv`) or come from the GPU model in `k3cim/architectures.py::gpu`, "
      "which is calibrated to the measured non-speculative point (DGX B300, 101 tok/s). CIM numbers are model outputs.\n")
    w("## 1. Measured K3 single-user decode on GPUs\n")
    w("| hardware | GPUs | tok/s per user | spec. decoding | context | J/token | source | date |\n|---|---:|---:|---|---|---:|---|---|")
    for r in bench:
        if r["model"].strip() != "Kimi K3":
            continue
        if r.get("batch_or_concurrency", "").strip() != "concurrency 1":
            continue
        notes = r.get("notes", "")
        spec = ("MTP" if "spec decode=mtp" in notes else "DSpark (7 drafts)" if "speculative tokens" in notes
                else "none" if ("spec decode=none" in notes or "without spec" in notes) else "see source")
        jt = ""
        if "J per output token" in notes:
            jt = notes.split("J per output token")[0].split(";")[-1].strip()
        w(f"| {r['hardware']} | {r['num_chips']} | {r['single_stream_tok_per_s']} | {spec} | {r['context_len'][:40]} | {jt} | "
          f"{r['source_short']} | {r['date']} |")
    w("\n## 2. Model comparison at matched context (realistic scenario)\n")
    g = Scheduler(gpu("real"))
    rows = []
    for L_ in (2048, 32768, 131072, 1048576):
        rg = g.evaluate(L_)
        sp, _ = speculative_tok_per_s(g, L_, 7)
        rows.append((L_, rg["tok_per_s"], sp, rg["energy_j_per_token"], rg["power_w"]))
    w("| context | 8xB300 model, no spec (tok/s) | with 7-draft spec decoding (tok/s) | J/token (no spec) | W |\n|---|---:|---:|---:|---:|")
    for L_, t, sp, e, p in rows:
        w(f"| {L_ // 1024}K | {t:.0f} | {sp:.0f} | {e:.1f} | {p:.0f} |")
    w("\nThe calibrated GPU model reproduces 101 tok/s (measured, no speculation) and 188 tok/s with a 7-token DSpark "
      "draft (measured; per-token acceptance fitted to 0.773, drafter cost 1 ms/token). Measured MTP numbers on GB300 "
      "(258 tok/s at ~290K context) are higher than the model's DSpark-calibrated value because MTP drafts are cheaper.\n")
    w("Why GPUs are stuck near 100 tok/s without speculation: per token they must stream 137 GB of weights "
      "(2.1 ms at 64 TB/s) but the measured time is 9.9 ms; the remaining ~84 µs per layer is synchronisation "
      "(tensor-parallel all-reduces, MoE dispatch, kernel boundaries) that a single stream cannot hide.\n")
    w("## 3. Best CIM / NVM designs vs GPU (from `architecture_comparison.csv`)\n")
    w("| arch | scenario | design | tok/s 32K | tok/s 128K | tok/s 1M | J/token 128K | W 128K | silicon USD (normalized) | GPU-system USD | precision |\n"
      "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for r in comp:
        if r.get("feasible") != "yes" or r["selection"] not in ("fastest_at_128K", "cheapest_meeting_500tok_s_at_128K"):
            continue
        if r["scenario"] != "real":
            continue
        def fm(k, fmt="{:.0f}"):
            v = _f(r.get(k))
            return fmt.format(v) if v is not None else "n/a"
        w(f"| {r['arch_id']} | {r['scenario']} | {r['selection'].replace('_at_128K', '')} | {fm('tok_s_32k')} | "
          f"{fm('tok_s_128k')} | {fm('tok_s_1024k')} | {fm('J_tok_128k', '{:.2f}')} | {fm('W_128k')} | "
          f"{fm('silicon_usd_normalized_128k')} | {fm('system_market_usd')} | {r.get('precision_verdict', '')} |")
    w("\n## 4. Energy per useful operation\n")
    w("A K3 token at 128K context is 2 x 104.2 G weight MACs + 2 x 328.6 G attention MACs = 0.87 TFLOP. "
      "Measured GB300 single-stream energy is 28.4 J/token (GPU boards only) = ~33 pJ/FLOP; under batched load it falls to "
      "7.9 J/token. See `results/energy_breakdown.csv` for the CIM designs (pJ per weight op and per op incl. attention).\n")
    w("## 5. Prefill (time to first token)\n")
    w("| design | 32K prompt | 128K prompt | 1M prompt |\n|---|---:|---:|---:|")
    a = analog_nand("real", "E", adc_bits=8)
    a.update(adc_sharing="die_pool", adc_pool_per_die=1024)
    for name, arch in (("8xB300 (model)", gpu("real")), ("E analog NAND (real, 1024-ADC pool, mid engine)", a),
                       ("A2 digital NAND (real)", digital_nand("real", "A2"))):
        sc = Scheduler(arch)
        t = [prefill_seconds(sc, T)[0] for T in (32768, 131072, 1048576)]
        w(f"| {name} | {t[0]:.1f} s | {t[1]:.0f} s | {t[2] / 60:.0f} min |")
    w("\nWeight-stationary CIM processes one prompt token per array operation, and 1M-token prefill is "
      "2.98 EFLOP of mostly causal attention: both NAND-PIM papers in this repo offload prefill to a GPU/NPU, "
      "and so must any K3 deployment that needs long prompts.\n")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write("\n".join(L))
    return path
