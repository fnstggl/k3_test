# GPU comparison — matched Kimi K3 single-stream decode

Same model (the released 2.8T K3 checkpoint: MXFP4 experts + BF16 dense), batch = 1 user, decode. GPU numbers are **measured** (SemiAnalysis InferenceX, OpenZeka, Artificial Analysis; see `data/sources/llm_decode_benchmarks_sourced.csv`) or come from the GPU model in `k3cim/architectures.py::gpu`, which is calibrated to the measured non-speculative point (DGX B300, 101 tok/s). CIM numbers are model outputs.

## 1. Measured K3 single-user decode on GPUs

| hardware | GPUs | tok/s per user | spec. decoding | context | J/token | source | date |
|---|---:|---:|---|---|---:|---|---|
| GB300 | 8 | 258.4 | MTP | agentic traces; median input 290232 tok | 28.4 | SemiAnalysis InferenceX (API) | 2026-09-15 |
| GB300 | 32 | 259.1 | MTP | agentic traces; median input 290232 tok |  | SemiAnalysis InferenceX (API) | 2026-09-15 |
| B300 | 8 | 236.4 | MTP | agentic traces; median input 231922 tok |  | SemiAnalysis InferenceX (API) | 2026-08-16 |
| GB200 | 16 | 222.7 | MTP | agentic traces; median input 222654 tok | 55.6 | SemiAnalysis InferenceX (API) | 2026-09-19 |
| B200 | 16 | 216.0 | MTP | agentic traces; median input 227999 tok | 49.0 | SemiAnalysis InferenceX (API) | 2026-10-02 |
| MI355X | 8 | 171.8 | MTP | agentic traces; median input 168264 tok |  | SemiAnalysis InferenceX (API) | 2026-09-30 |
| MI355X | 8 | 159.0 | MTP | agentic traces; median input 166683 tok | 36.4 | SemiAnalysis InferenceX (API) | 2026-09-29 |
| H200 | 32 | 5.3 | MTP | agentic traces; median input 330301 tok | 1149.3 | SemiAnalysis InferenceX (API) | 2026-09-13 |
| NVIDIA DGX B300 (8x B300) | 8 | 187.7 | DSpark (7 drafts) | ~128 in / 128 out |  | OpenZeka whitepaper (vLLM + DSpark spec decode) | 2026-07 |
| NVIDIA DGX B300 (8x B300) | 8 | 100.8 | none | ~128 in / 128 out |  | OpenZeka whitepaper (vLLM, no spec decode) | 2026-07 |
| 2 nodes x 8 NVIDIA H200 (16 GPUs) | 16 | 16.8 | see source | 512-token completions, reasoning_effort= |  | Hugging Face moonshotai/Kimi-K3 discussion #136 (community) | 2026-07-28 |

## 2. Model comparison at matched context (realistic scenario)

| context | 8xB300 model, no spec (tok/s) | with 7-draft spec decoding (tok/s) | J/token (no spec) | W |
|---|---:|---:|---:|---:|
| 2K | 101 | 192 | 32.9 | 3336 |
| 32K | 101 | 190 | 33.1 | 3345 |
| 128K | 100 | 185 | 33.8 | 3374 |
| 1024K | 91 | 150 | 39.8 | 3610 |

The calibrated GPU model reproduces 101 tok/s (measured, no speculation) and 188 tok/s with a 7-token DSpark draft (measured; per-token acceptance fitted to 0.773, drafter cost 1 ms/token). Measured MTP numbers on GB300 (258 tok/s at ~290K context) are higher than the model's DSpark-calibrated value because MTP drafts are cheaper.

Why GPUs are stuck near 100 tok/s without speculation: per token they must stream 137 GB of weights (2.1 ms at 64 TB/s) but the measured time is 9.9 ms; the remaining ~84 µs per layer is synchronisation (tensor-parallel all-reduces, MoE dispatch, kernel boundaries) that a single stream cannot hide.

### What would it take on the GPU side (same 8xB300, model)

The ~84 us/layer is software and interconnect latency, not physics. Sweeping it in the calibrated model:

| per-layer sync | tok/s 2K | tok/s 128K | tok/s 1M | 128K, 7-draft spec | binding limit at 128K |
|---:|---:|---:|---:|---:|---|
| 84 us | 101 | 100 | 91 | 185 | critical path |
| 30 us | 207 | 201 | 167 | 245 | critical path |
| 10 us | 327 | 320 | 241 | 278 | critical path |
| 2 us | 327 | 327 | 294 | 293 | HBM bandwidth |

With BF16 always-active weights an 8xB300 node is HBM-bound at ~330 tok/s single-stream once synchronisation drops to ~10 us/layer (persistent 'megakernel' execution, fused MoE dispatch). That is the honest software-only competitor for any new silicon: roughly 3x today's measured number on the same ~$320K node.

## 3. Best CIM / NVM designs vs GPU (from `architecture_comparison.csv`)

| arch | scenario | design | tok/s 32K | tok/s 128K | tok/s 1M | J/token 128K | W 128K | silicon USD (normalized) | GPU-system USD | precision |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| A0 | real | fastest | 0 | 0 | 0 | 14.74 | 3 | 105 | n/a | exact_digital |
| A1 | real | fastest | 1 | 1 | 1 | 7.47 | 9 | 268 | n/a | exact_digital |
| A2 | real | cheapest_meeting_100tok_s | 259 | 144 | 22 | 5.87 | 844 | 2520 | n/a | exact_digital |
| A2 | real | fastest | 259 | 259 | 57 | 5.86 | 1518 | 3833 | n/a | exact_digital |
| G | real | fastest | 907 | 689 | 212 | 0.29 | 197 | 1839 | n/a | exceeds_budget |
| H | real | fastest | 101 | 100 | 91 | 33.76 | 3374 | n/a | 320000 | exact_digital |
| B-mp | real | fastest | 5 | 5 | 5 | 10.00 | 54 | 1500 | n/a | exceeds_budget |
| E-mp | real | fastest | 25 | 25 | 23 | 2.39 | 59 | 1500 | n/a | exceeds_budget |
| B | real | cheapest_meeting_500tok_s | 612 | 504 | 191 | 0.35 | 178 | 2022 | n/a | marginal |
| B | real | cheapest_meeting_100tok_s | 206 | 111 | 21 | 0.67 | 75 | 850 | n/a | marginal |
| B | real | fastest | 625 | 513 | 192 | 0.32 | 164 | 1670 | n/a | exceeds_budget |
| C | real | cheapest_meeting_500tok_s | 728 | 519 | 141 | 0.32 | 164 | 1477 | n/a | marginal |
| C | real | cheapest_meeting_100tok_s | 276 | 130 | 22 | 0.66 | 85 | 884 | n/a | marginal |
| C | real | fastest | 880 | 673 | 210 | 0.29 | 195 | 1670 | n/a | exceeds_budget |
| D | real | cheapest_meeting_500tok_s | 871 | 587 | 145 | 0.38 | 223 | 2270 | n/a | marginal |
| D | real | cheapest_meeting_100tok_s | 199 | 110 | 21 | 0.86 | 94 | 1534 | n/a | marginal |
| D | real | fastest | 1078 | 783 | 220 | 0.28 | 216 | 1670 | n/a | exceeds_budget |
| E | real | cheapest_meeting_500tok_s | 767 | 538 | 142 | 0.36 | 196 | 2270 | n/a | marginal |
| E | real | cheapest_meeting_100tok_s | 253 | 124 | 22 | 0.76 | 94 | 1534 | n/a | marginal |
| E | real | fastest | 889 | 678 | 211 | 0.29 | 194 | 1670 | n/a | exceeds_budget |
| F | real | fastest | 1274 | 882 | 227 | 1.17 | 1030 | 270002 | n/a | exceeds_budget |

## 4. Energy per useful operation

A K3 token at 128K context is 2 x 104.2 G weight MACs + 2 x 328.6 G attention MACs = 0.87 TFLOP. Measured GB300 single-stream energy is 28.4 J/token (GPU boards only) = ~33 pJ/FLOP; under batched load it falls to 7.9 J/token. The cheapest analog-NAND designs meeting 100 / 500 tok/s at 128K (table above) spend 0.3-0.7 J/token (model), 50-100x less per token than the measured single-stream GPU figure, mostly because weights never move; see `results/energy_breakdown.csv` for the per-mechanism split (pJ per weight op and per op incl. attention).

## 5. Prefill (time to first token)

| design | 32K prompt | 128K prompt | 1M prompt |
|---|---:|---:|---:|
| 8xB300 (model) | 0.7 s | 6 s | 5 min |
| E analog NAND (real, 1024-ADC pool, mid engine) | 16.4 s | 227 s | 231 min |
| A2 digital NAND (real) | 17.6 s | 232 s | 232 min |

Weight-stationary CIM processes one prompt token per array operation, and 1M-token prefill is 2.98 EFLOP of mostly causal attention: both NAND-PIM papers in this repo offload prefill to a GPU/NPU, and so must any K3 deployment that needs long prompts.
