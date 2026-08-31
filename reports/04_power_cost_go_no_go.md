# Gate 6 — Power + economics: the >10× question

Run: `python3 experiments/economics.py` → `results/economics.json`.
Architecture-side numbers come from the calibrated simulator (Gates 2–5).
The GPU comparison is a **separate, labeled reference model** built on sourced
anchors — it is not a simulation of GPU internals.

## Inputs and their status

| Input | Value | Status |
|---|---|---|
| K3 checkpoint size | 1.56 TB MXFP4(+BF16 pools) | FACT — matches our derived 1.45+0.11 TB (runpod K3 FAQ: "roughly 1.56 TB on disk") |
| Min GPU deployment | 8×B300 (2.3 TB) single node | FACT (runpod K3 FAQ) |
| HGX B200-class node price | $450–650k (B300 premium modeled) | FACT-anchored RANGE (street/node quotes, Aug 2026) |
| GPU power | ~1 kW/GPU; node 10–14 kW | FACT-anchored |
| GPU rental | $4–8/GPU-hr (specialist clouds) | FACT (Aug 2026) |
| NAND price | $0.10–0.35/GB; central $0.28 (512Gb TLC wafer spot ≈ $17.9, 2026 shortage) | FACT-anchored RANGE (TrendForce/DRAMeXchange) |
| NAND sense energy | 42–89 pJ/B (ICC-vs-calculator range, Gate 2) | MODEL RANGE |
| GPU node decode throughput | HBM roofline × efficiency 0.4–0.6 on exact K3 bytes/step (expert-union math) | MODEL (TR confirms decode experts are "memory-bound streaming") |
| Custom page-buffer periphery cost | +0–30% on die cost | MODEL RANGE (NRE amortization unknown — flagged) |
| Electricity | $0.10/kWh | RANGE 0.05–0.15 |

## Results (central scenario)

NAND-PIM builds (Gate 5 frontier):

| Build | tok/s | per-user | J/token | Capex | Wall power | $/Mtok (3y capex+power) |
|---|---|---|---|---|---|---|
| A: 5.5 TB SLC-mode-TLC, 768 pl, B=1 | 8.0 | 8.0 | 10.4 (5.8 low) | $2 851 | 98 W | $4.11 |
| B: 22 TB SLC-mode-TLC, 3 072 pl, B=4 | 50.7 | 12.7 | 5.0 (2.9 low) | $8 312 | 268 W | $1.88 |
| C: 2 TB SLC-Z, 2 048 pl, B=1 | 8.7 | 8.7 | 8.2 | $1 784* | 86 W | $2.44 |

*Z-NAND die pricing is speculative (niche part) — build C's $ is illustrative only.

GPU 8×B300 node (efficiency 0.6, BF16 dense + MXFP4 experts, expert-union bytes):

| Batch | per-user tok/s | node tok/s | J/token | $/Mtok (capex 3y) | $/Mtok (rental $6/hr) |
|---|---|---|---|---|---|
| 1 | 280 | 280 | 42.8 | $21.92 | $47.55 |
| 8 | 126 | 1 006 | 11.9 | $6.11 | $13.25 |
| 64 | 35 | 2 232 | 5.4 | $2.75 | $5.97 |
| 256 | 25 | 6 370 | **1.9** | **$0.96** | $2.09 |

## The kill-threshold verdict

> Does a physically defensible configuration plausibly support >10× lower
> joules/token OR >10× lower tokens/$ while preserving useful K3 latency?

**NO for general (throughput-oriented) serving — robustly.** At the batch
sizes GPUs actually run (64–256), the GPU node reads *fewer weight bytes per
token* than the NAND system can (5.9 GB/token at B=256 vs ≥27 GB/token for
NAND at its B=4–8 sweet spot), because K3's 1.8%-active expert pool only
amortizes at batch ≥~100 — a regime NAND's ~1–3 TB/s array bandwidth cannot
reach at useful latency, while 38 TB/s of effective HBM can. Central-scenario
ratios (GPU/NAND; >10 required): J/token ×0.4, $/Mtok ×0.5 at GPU B=256 —
i.e. **the GPU is ~2–2.5× better**. No point in the sensitivity range
(NAND at $0.10/GB and 42 pJ/B, GPU at eff=0.4 and $650k) brings the
high-batch comparison above ~×2.5 in NAND's favor.

**YES — but only against low-concurrency GPU deployments.** For dedicated
single/low-stream serving (private/on-prem/sovereign, 1–8 users of one
1.56 TB model), the GPU alternative idles a $450–650k, 12 kW node at B=1–8:

| Comparison (central) | J ratio | $ capex ratio | $ rental ratio |
|---|---|---|---|
| Build B vs GPU B=1 | ×8.6 | ×11.7 | ×25.3 |
| Build C vs GPU B=1 | ×5.2 | ×9.0 | ×19.5 |
| Build A vs GPU B=8 | ×1.1 | ×1.5 | ×3.2 |

The >10× line is crossed only vs GPU B≈1 (and rental at B≤8 for build B).
There is also a granularity/accessibility argument — minimum viable K3
deployment: ~$3k & 100 W vs ~$550k & 12 kW — real, but it is a market-shape
advantage, not the claimed structural economics advantage.

## Why (structural, not parametric)

1. **Per-bit read energy is comparable** — NAND sense 5–11 pJ/bit vs HBM
   ~4–8 pJ/bit. There is no order-of-magnitude energy-per-bit win to harvest.
2. **The batch asymmetry decides it.** J/token = bytes/token × pJ/bit.
   GPUs cut bytes/token ~23× via batch 256; NAND-PIM's array bandwidth caps
   it at B≈4–8 (bytes/token ↓ ~4×) before latency collapses. K3's MoE
   makes this worse: expert reads barely amortize below B≈100
   (D(B)=896(1−(1−16/896)^B)).
3. **NAND's genuine edge is capacity-$ per stream**, which only monetizes
   when concurrency per model instance is low.
4. 2026 NAND shortage pricing ($0.28/GB) erodes what was the strongest NAND
   argument in 2024-era pricing ($0.06–0.10/GB); at $0.10/GB the low-batch
   advantage widens ~2× but the high-batch verdict is unchanged.

## Endurance / refresh check (viability, not economics)

Continuous decode re-reads every weight page ~8×/s (build A). Read-disturb
budget for SLC-mode blocks (10⁵–10⁶ reads between refreshes, MODEL range):
refresh traffic = capacity × read_rate / N_rd ≈ 44–440 MB/s of background
SLC programming — 1–10% of array program capability; full-array rewrite every
3.5–35 h → ≤2 400 P/E cycles/year vs ~30–100k SLC-mode endurance → decades.
**Viable with routine refresh scheduling; not a blocker** (needs BABOL-class
confirmation of read-disturb rates on the actual part).

## Anchor

Moonshot API list ≈ $15/Mtok out (reported): both NAND ($1.9–4.1) and GPU
($0.96–2.75 capex-basis) serve far below list price; nothing here contradicts
observed market pricing.

## Bottom line for GO_NO_GO

The mission's >10× structural claim is **falsified for datacenter serving
economics** and **supported only for the low-concurrency/on-prem regime**
(vs GPU B≤8, where ratios reach 12–25×). Carried to the final verdict.
