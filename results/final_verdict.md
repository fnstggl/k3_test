# Final verdict: can a low-cost NVM compute architecture run the complete Kimi K3 at 100-1,000 tok/s?

Everything here is reproducible from this repository (`README.md` → *Reproduce*). Numbers are model outputs
unless marked *measured*; §7 classifies every claim by evidence. Silicon costs are volume silicon at
normalized (2025) memory prices; packaging, board and NRE are **unknown** and excluded, and 2026 shortage
prices are ~7x higher for the NAND part (`results/cost_model.csv`).

## 0. The answer

**Not with NAND as it is built today, and not for $500 at long context. A redesigned analog 3D-NAND die gets close on everything except the price at long context.**

1. **Commodity NAND cannot do it, at any price.** Any architecture that keeps the commodity plane, digital (A0, A1) or analog (B-mp, E-mp), tops out at 0.2-25 tok/s. K3 has 698 dependent matrix-vector stages per token, and a commodity plane needs 20-50 µs per page read or ~10 µs of word-line setup per analog step. This is a geometry limit, not a tuning problem.
2. **A redesigned small-plane 3D-NAND compute die can reach the speed target in simulation, at ~$0.9-1.5K of silicon.** "Redesigned" means 256 × 2,048-cell planes, 256 planes per die, and analog bit-line summation over C = 32-128 cells, with die-level pools of 6-8-bit ADCs. Paired with a digital attention engine, the realistic scenario gives:
   - **100 tok/s at 128K:** B, C = 32, 2-bit cells, ~$880, 0.7 J/token, ~80 W.
   - **500 tok/s at 128K:** C encoding, C = 128, 2-bit cells, $1,477, 0.32 J/token, 164 W, 1,055 dies. The precision verdict is "marginal" (0.85× budget). Using 1-bit cells instead puts it within budget at $2,182.
   - **1,000 tok/s:** only with optimistic array physics (0.3 µs word-line setup): $1.45K marginal, $2.5K within budget.
   - **Pessimistic scenario:** ~100 tok/s for ~$2.9K; 500 tok/s is out of reach.
3. **Accuracy is reachable with 1-2-bit cells.** On real K3 tensors with SONOS-class measured device models, 1-2-bit cells summed over C ≤ 128 and read by an ADC whose step is one unit of the integer sum reproduce exact integer results (0.00-0.15× of the error budget). 4-bit cells exceed the budget (1.2-1.6×) unless programming gets ~4× tighter. Drift needs periodic re-programming. **No public measurement exists of summed currents in real 3D NAND strings.** Every analog result rests on a planar-SONOS proxy.
4. **$500 closes only at 32K context, and only with three unproven levers.** The levers are 4-bit cells with ~4× tighter programming, commodity cell density in small planes, and larger dies. Together they give $418-479 at ~550 tok/s.
   - At 128K the floor is ~$850. The attention engine alone, 1.5 PFLOP/s plus 2.3 GB of on-die FP8 KV and KDA state, costs ~$430.
   - 500 tok/s at 1M context is infeasible in every scenario. It needs ~2.6 PFLOP/s and 7-15 TB/s of KV bandwidth, a GPU-class problem that no weight-storage technology removes.
5. **What NAND uniquely gives is storage cost.** Holding the 1.50 TB of K3 weights costs $52 of QLC NAND silicon, against $4.5K of DRAM or $18K of HBM. Analog in-place compute needs 2.5-4× more cell capacity (11-17 cell bits per weight against 4.5 as released) and a CMOS-dominated periphery. Energy per token drops 50-100× versus measured GPUs (0.3-0.7 J against 28-34 J). Prefill is 20-50× slower than on GPUs (16 s vs 0.7 s for a 32K prompt), so long prompts need a GPU-class prefill partner.
6. **Nothing here is commercially viable yet.** The architecture does not close on accuracy evidence (no 3D-NAND measurement), on cost at ≥128K, or on packaging (66-111 packages of 16 small dies, at unknown cost).

The cheapest *physically defensible* path that meets the primary target (500 tok/s, 128K) in the realistic scenario is therefore: **a new small-plane analog 3D-NAND compute die**, using multi-bit time-encoded input steps (encoding C), 2-bit cells, C = 128, a calibrated-range 6-bit ADC pool per die, and periodic refresh. It is paired with a ~950 mm², 5 nm-class attention/orchestration chip that holds the FP8 KV cache in SRAM. Silicon is about $1.5K plus unknown packaging. The software-only alternative is ~330 tok/s on an existing 8x B300 node (~$320K) once per-layer synchronisation is removed.

## 1. What physics and the model fix (`results/first_principles.md`, `results/workload.md`)

| fixed quantity | value | consequence |
|---|---:|---|
| stored weights | 2.72 T MXFP4 experts + 56 G BF16 (1.50 TB at MXFP4/MXINT8) | only 3D-NAND-class density holds it under $500 ($52 QLC vs $4.5K DRAM, $18K HBM) |
| active weights per token | 48.6 G expert + 55.6 G always-active MACs | streaming them is 41.6 TB/s at 500 tok/s (8-bit dense) |
| dependent stages per token | 698 MVM stages (1,396 incl. reductions) | 2.9 µs per stage at 500 tok/s, 1.4 µs at 1,000: input, settle, convert, reduce, hop |
| routing decided | ~µs before use, 16 of 896 experts per layer | every expert must be µs-reachable: no cold tier on the path |
| MLA attention per context token | 5.0 MFLOP, 27.6 kB BF16 latent KV | 0.33 PFLOP/s + 1.8 TB/s at 128K; 2.6 PFLOP/s + 14.5 TB/s at 1M (500 tok/s) |
| KDA state | 449 MB FP32, read+written every token | on-die SRAM-class bandwidth (0.45 TB/s at 500 tok/s) |
| tolerated error | MXFP8 activation quantisation: 1.1 % (dense) / 2.7 % (expert) per MVM | analog error is budgeted against this, not against bit-exactness |

**Requirement audit.** These are conventions, not physics, and the models drop them: BF16 dense weights (MXINT8 adds only 0.12-0.29 %), exact digital arithmetic, ~84 µs of GPU per-layer synchronisation, and BF16 KV. FP8 KV is used in the SRAM engines, flagged as unvalidated for K3. These are model-fixed and kept: 8-bit activations (QAT), all experts resident, the 698-deep dependency chain, and full attention at 1M.

## 2. What would it take: the step functions (`results/step_ladder.csv`, `results/plots/step_ladder_128k.png`)

Each rung changes one physical thing (realistic parameters, 128K context):

| step | tok/s @128K | silicon $ | what changed physically |
|---|---:|---:|---|
| R0 commodity TLC, stream over ONFI (A0) | 0.23 | 252 | I/O pins bound |
| R1 near-plane compute, SLC mode (A1) | 1.2 | 415 | 20-50 µs page reads × too few planes |
| R2 small low-latency SLC planes, digital (A2) | 144 | 2,520 | 3 µs reads; sensing every weight bit costs 1 G sense amps at 500 tok/s |
| R3 analog bit-line sums on commodity planes (B-mp) | 5.2 | 700 | ~10 µs word-line setup per step |
| R4 small analog planes, C = 128, 2-bit cells, 1-bit input steps (B) | 117 | 1,169 | sensing work ÷ C; µs-class steps |
| R5 2 input bits per time-encoded step (C) | 136 | 1,169 | fewer steps per MVM |
| R6 4× die-level ADC pool | 147 | 1,223 | conversions stop queuing |
| R7a attention engine with 5 HBM3E stacks | 435 | 3,598 | KV bandwidth bought as capacity |
| **R7b instead: FP8 KV in on-die SRAM, 1.5 PFLOP/s** | **519** | **1,477** | KV bandwidth bought as SRAM; faster, at ~40 % of the cost |
| R8 optimistic array physics (0.3 µs WL setup) | 966 | 1,438 | the last ~2× is word-line RC |
| R9 speculative decoding (k = 1, dense ×2) | 1,080 | 1,466 | only +12 %: verification multiplies array ops on shared and hot arrays |

The quantitative thresholds that must hold (all from the models above):
- **Stage latency.** ≤ ~2.9 µs per dependent MVM stage, including links. That means word-line setup ≤ ~0.8 µs and per-step time ≤ ~64 ns. Commodity planes give ~10 µs and 2 µs.
- **Analog precision.** Per-cell programmed-current σ such that 1-2-bit cells, summed over C ≤ 128, stay under ½ LSB. SONOS-class σ (~1.25 % of Imax) suffices; 4-bit cells need ~0.3 %. ADC noise must be ≪ 0.5 LSB; 0.5 LSB rms alone costs 3.8× budget.
- **Calibration.** Trim the ADC reference against a replica cell to track temperature and global drift. Re-program roughly daily: ~16-33 s per full refresh, ~1,800 cycles in 5 years.
- **Conversion throughput.** ~2-6 T conversions/s at 500 tok/s, i.e. ~10^5 small SAR ADCs, ~50 mm² in total.
- **Attention.** ≥ 1.5 PFLOP/s peak (latency-bound: 24 sequential MLA layers) and ≥ 0.9-1.8 TB/s sustained KV reads (FP8-BF16) at 128K, with far higher peak bandwidth. On-die SRAM holding FP8 KV is the cheapest form, but its cost scales linearly with context.
- **No software synchronisation.** A hard-wired dataflow with ≤ ~0.1-1 µs per stage of control.

**Speculative decoding, the usual latency multiplier, mostly fails on weight-stationary arrays.** Each extra verified token is another array operation on the same dense arrays. Real K3 routing also reuses experts across neighbouring tokens: one expert serves 4-6 of 8 consecutive tokens (measured, layers 1-3). Replicating the dense weights (~3 % extra capacity per copy) recovers only part of the gain: +10-30 % versus +86 % on GPUs (101 → 188 tok/s measured).

## 3. Results by architecture (`results/architecture_comparison.csv`, `results/dse_summary.csv`)

The design-space sweep covered 22,008 configurations: encodings B-E × contributors C (32-256) × cell bits (1-4) × ADC bits (6-12) × ADC pool size × 9 attention engines, plus A0-A2, F, G and H, each in 3 scenarios. In the tables, a design counts only if its analog error is ≤ 1× the MXFP8 budget ("within" or "marginal").

**Fastest design within the precision budget, tok/s at 32K / 128K / 1M:**

| arch | what it is | pessimistic | realistic | optimistic |
|---|---|---|---|---|
| A0 | commodity NAND, stream weights over ONFI | 0.09 / 0.09 / 0.09 | 0.23 / 0.23 / 0.23 | 0.27 / 0.27 / 0.27 |
| A1 | near-plane digital MAC, commodity planes | 0.6 / 0.6 / 0.6 | 1.2 / 1.2 / 1.2 | 52 / 52 / 52 |
| A2 | small low-latency SLC planes, digital | 95 / 85 / 43 | 259 / 259 / 198 | 3,060 / 1,990 / 459 |
| B-mp, E-mp | analog sums on commodity planes | none within budget | none (5-25 tok/s at 1.2-1.9× budget) | none |
| B | redesigned analog, 1-bit input steps | 88 / 79 / 41 | 616 / 504 / 191 | 1,430 / 1,140 / 391 |
| C | 2-bit input steps | 121 / 105 / 47 | 875 / 666 / 210 | 2,140 / 1,540 / 430 |
| D | 4-bit input steps | 144 / 122 / 50 | 1,050 / 765 / 219 | 2,690 / 1,810 / 448 |
| E | one-pass 8-bit time-encoded | 148 / 124 / 51 | 883 / 670 / 210 | 2,170 / 1,560 / 431 |
| F | 3D RRAM crossbar | none within budget (RRAM Milo model); 1T1R density needs ~53,000 dies | none | none |
| G | 3D FeNAND (speculative) | none within budget for 2-4-bit cells with a generic 1 % device | none | none |
| H | 8x B300 GPU (calibrated to measured) | 78 / 77 / 70 | 101 / 100 / 91 | 163 / 160 / 139 |

**Cheapest design meeting 100 / 500 tok/s at 128K: silicon $ (J/token):**

| arch | pessimistic | realistic | optimistic |
|---|---|---|---|
| A2 | – / – | $2,520 (5.9) / – | $4,176 (1.2) / $4,424 (1.1) |
| B | – / – | $850 (0.67) / $2,022 (0.35) | $832 (0.38) / $1,106 (0.24) |
| C | $2,912 (1.8) / – | $884 (0.66) / **$1,477 (0.32)** | $842 (0.35) / $1,113 (0.24) |
| D | $3,569 (2.5) / – | $1,534 (0.86) / $2,270 (0.43) | $1,497 (0.44) / $1,806 (0.27) |
| E | $3,298 (2.3) / – | $1,534 (0.76) / $2,270 (0.40) | $1,497 (0.38) / $1,764 (0.27) |
| H | – / – | 99.9 tok/s at ~$320K system (34), just under / – | ~$320K system (23) / – |

What limits the fast designs (`results/plots/latency_breakdown_128k.png`):
- **Analog designs at 500 tok/s.** The 1.7-2.0 ms token splits into 0.8-1.4 ms of array operations along the 698-stage chain and 0.5-0.75 ms of MLA attention over the 128K cache.
- **A2.** Attention plus 3 µs digital reads.
- **GPU.** 7.8 of its 10 ms are per-layer synchronisation.

At 1M context the best designs are attention-bound at ~190-220 tok/s, against the GPU's 91.

## 4. Numerical accuracy: what the real K3 tensors say

All results below use real K3 weights and real activations from the re-implemented forward pass (layers 0-3, 16 tokens of text): an expert tile (`L1.expert.w1`, the most-routed expert, MXFP4 codes and E8M0 scales from the checkpoint) and a dense tile (`L0.kda.q_proj`, BF16 rendered as MXINT8). The yardstick is the error K3 already tolerates: the MVM error caused by MXFP8 activation quantisation alone (2.69 % expert, 1.10 % dense, relative RMS). Verdicts: <= 0.25x that budget "within", <= 1x "marginal", > 1x "exceeds". (`results/precision_sweep.csv`, 5,076 rows; `data/sim_outputs/crosssim/device_grid.json`.)

**What has to be preserved, and how it maps to cells.** E2M1 values are signed and nonuniform (±{0, 0.5, 1, 1.5, 2, 3, 4, 6}); in half-units they are integers 0..12, i.e. a 4-bit magnitude per weight plus sign, which needs two cells (differential) or an offset column. The shared E8M0 scale is per 32 weights. Summing C > 32 weights on one bit line means aligning up to C/32 scales; on real K3 rows the exponents inside a 128-weight group differ by at most one step in 99.3 % of rows (97.4 % for 256), so one extra magnitude bit (5 bits) folds the scales exactly into the weight integers for 99.3 % of rows at C <= 128 (two extra bits at C = 256, p99); the remaining rows lose low-order bits of their smallest blocks, and that loss is included in every error figure below. MXFP8 inputs become 8-bit magnitudes plus sign after aligning the block exponent (2 sign phases). Dense weights need 8 bits (MXINT8 adds only 0.12-0.29 % error; MXFP4 would add 4.8 %).

**Ideal devices (quantisation and ADC only).** With an ADC whose LSB equals one unit of the integer sum ("unit-LSB"), the analog result is bit-exact. Truncating the ADC below that is catastrophic for 1-bit input steps with a fixed full-scale range (e.g. 2-bit cells, C = 128, 8-bit ADC: 11-20x budget) but the ADC range can be calibrated: setting full scale from the observed partial-sum distribution on calibration tokens and testing on held-out tokens, 4-6 ADC bits suffice for SLC/MLC with 1-bit steps and 8 bits for QLC at C = 128. One-pass 8-bit time-encoded inputs (E) need 8-13 ADC bits for "within" and 7 bits for "marginal".

**Measured device models (CrossSim SONOS, RRAM; 1-bit steps, unit-LSB ADC).** Error / budget, expert tile, after 1 day of SONOS drift:

| cell bits | C = 32 | C = 128 |
|---|---:|---:|
| 1 (SLC) | 0.00 | 0.00 |
| 2 (MLC) | 0.01 | 0.15 |
| 3 (TLC) | 0.45 | 0.77 |
| 4 (QLC) | 1.61 | 1.20 |

SLC and MLC sums come back exact because the per-cell error is far below half an LSB even when 128 cells add; QLC cells (16 levels in the same current window) do not. After 5 days of SONOS drift MLC at C = 128 rises to 1.1x (C = 32 stays at 0.22): drift broadens the distribution rather than shifting it, so gain/offset calibration does not repair it and the cells must be re-programmed periodically (estimate: 32,768 pages per plane at 0.5-1 ms per verified MLC page is 16-33 s with all planes programming in parallel, minutes if power-limited; a daily refresh for 5 years is ~1,800 program cycles, within MLC endurance). RRAM (Milo model) is within budget only as SLC at C = 32.

**Robustness (QLC, C = 32, SONOS, 9-bit unit-LSB ADC; base 1.17x):**
- program-verify 2x / 4x tighter than the 40 nm SONOS data: 0.42x / 0.25x — QLC becomes viable only with ~4x tighter programming (sigma ~0.3 % of full-scale cell current);
- ADC noise 0.5 / 1 LSB rms: 3.8x / 6.3x — the restoring ADC must be quiet to well below half an LSB;
- uniform temperature gain of 2-10 %: corrected by trimming the ADC reference with a replica cell (1.13-1.22x), not by digital gain/offset correction after the ADC (1.5-2.0x); per-cell temperature-coefficient spread of 3 % costs +0.5x;
- aging drift -5 % mean / 2 % spread: 1.45x with reference trimming;
- bit-line compression up to 20 % of full scale: no measurable effect (bit-serial inputs keep bit-line sums far below full scale; speculative model);
- recomputing 10 % of outputs digitally ("spot checks") only reaches 1.10x: spot-checking detects but does not repair distributed analog error.

**Bottom line on accuracy.** With SONOS-class cells, 1-2 bits per cell, C <= 128, 1-bit input steps, unit-LSB conversion with a calibrated range and periodic refresh, the analog result is indistinguishable from exact integer arithmetic on real K3 tensors. Spending fewer conversions per MVM (2-bit input steps with a 6-bit calibrated ADC, as in the cheapest 500 tok/s design) costs precision: 0.85x of the budget, i.e. "marginal". 4-bit cells exceed the budget unless programming precision improves ~4x. These are proxy-device results: no public data exists for summed currents in real 3D NAND strings (§8).

### 4.1 End-to-end noise propagation

The per-MVM error budgets above are local. To see how analog-like error compounds, `scripts/noise_propagation.py` re-runs the real layers 0-3 on the same 16 tokens with zero-mean Gaussian error of relative size r added to every matrix-vector output, either on all linears or only on routed experts. It then measures the deviation of each layer's output from the BF16 reference and how many of the 16 routed experts per token stay the same. The comparison case puts MXFP8 quantisation on every linear input: that is what K3's quantisation-aware training is meant to absorb (`results/noise_propagation.csv`).

| case | layer-3 output error (non-BOS tokens) | experts kept, layers 1/2/3 | tokens with any routing change at layer 3 |
|---|---:|---|---:|
| **MXFP8 inputs on all linears (reference)** | **7.8 %** | 97.3 / 96.9 / 96.5 % | 56 % |
| noise r = 0.5 % on all linears | 4.5 % | 99.6 / 99.2 / 98.4 % | 19 % |
| r = 1 % on all linears | 5.6 % | 98.4 / 98.8 / 97.3 % | 38 % |
| r = 2 % on all linears | 6.0 % | 98.8 / 98.4 / 97.7 % | 31 % |
| r = 4 % on all linears | 8.8 % | 96.5 / 96.1 / 95.3 % | 62 % |
| r = 8 % on all linears | 14.9 % | 94.9 / 94.1 / 92.6 % | 81 % |
| r = 2 % / 4 % / 8 % on experts only | 2.9 / 4.4 / 7.9 % | ≥ 96 % | 6 / 19 / 56 % |

Uncorrelated error of up to ~2 % per MVM on every linear, or up to ~8 % on the routed experts alone, perturbs the first four layers no more than MXFP8 quantisation does. The "marginal" threshold (error ≤ 1.1 % dense / 2.7 % expert per MVM) sits inside that envelope, so on this evidence it is conservative rather than optimistic. Routing is the sensitive path: even the reference flips at least one of 16 experts for about half the tokens.

Caveats: 4 of 93 layers, 16 tokens, one noise seed. Hence the non-monotonic small-r rows, where discrete routing flips dominate. Analog error is also not purely uncorrelated (gain drift is correlated; this is why ADC-reference trimming matters, §4). And output deviation is not task accuracy: the GPU noise-injection run in §8 is what turns this into an accuracy statement.


## 5. Cost: where the money goes and what $500 takes (`results/cost_model.csv`, `results/first_principles.md` §3, §8)

- **Weights.** As plain storage, 1.50 TB of K3 is $52 of QLC silicon (normalized) or $376 at 2026 shortage prices. The analog designs need 11-17 effective bits of cell capacity per weight against 4.5 as released, because of differential pairs, slicing, alignment bits and spare columns. In small planes, the CMOS under the array (high-voltage word-line drivers, sample capacitors) is larger than the cell stack above it. The NAND part of the 500 tok/s design is therefore $1,044, not $52.
- **Attention and KV.** At 128K this costs $430 as on-die SRAM (FP8 KV), against ~$2,500 with HBM; HBM sells capacity, and K3 needs bandwidth. At 1M it is ~$2.2K. Context, not weight storage, decides whether $500 is reachable.
- **Levers toward $500** (`results/cost_ladder.csv`): at 32K, 4-bit cells (4× tighter programming) → $542, + commodity density in small planes → $479, + 4× larger dies → $418, all at ~550 tok/s. At 128K the same levers stop at $850.
- **Unknown, not estimated.** Packaging of 90-1,800 small dies into 6-111 packages, the board, power delivery (75-200 W), the custom NAND engineering lot, test and NRE. These can dominate a $500 bill of materials and have no manufacturing basis in this study.
- **Prototype.** The only priced item is a 28 nm MPW logic test chip (4 mm², ~$46K). A redesigned 3D-NAND array needs a NAND-fab partner; no public price exists.

## 6. Rankings (realistic scenario unless noted)

| criterion | ranking (best first) | basis |
|---|---|---|
| **Physical feasibility** | H > A0 > A1 > A2 > B-mp ≈ E-mp > B > C > D > E > G > F | H and A0 exist. A1-style multi-plane activation is demonstrated (Flash-Cosmos). A2 extrapolates shipped Z-NAND/XL-FLASH. Analog sums on 3D-NAND exist only in test chips; B needs only binary inputs, while E needs 8-bit time encoding with analog accumulation. FeNAND is research-stage. 3D RRAM crossbars at the needed density are not demonstrated. |
| **Single-user K3 performance** (128K, within budget) | D 765 > E 670 ≈ C 666 > B 504 > A2 259 > H 100 (188 with speculation, 258 measured with MTP on GB300) > E-mp/B-mp (over budget) > A1 1.2 > A0 0.23 | model; H measured |
| **Numerical accuracy** | H = A0 = A1 = A2 (exact) > B > C > D > E > G > F; B-mp/E-mp exceed with their 4-bit cells | Sweep A + device grid: fewer input bits per step need fewer ADC bits for exact restoration. |
| **Energy efficiency** (J/token, cheapest 100 tok/s design) | C 0.66 ≈ B 0.67 > E 0.76 > D 0.86 > A2 5.9 > A1 7.5* > A0 15* > H 34 (28 measured) | model; * at 0.2-1.2 tok/s. The 500 tok/s designs are 0.32-0.43 J/token. |
| **Eventual manufacturing cost** (100 / 500 tok/s at 128K) | B $850 ≈ C $884 / C $1,477 < B $2,022 < D, E $1,534 / $2,270 < A2 $2,520 / – ≪ H ~$320K | volume silicon, normalized; packaging unknown |
| **First-prototype cost** | A0 (~$190 SSD + host) < H (rent; $320K to buy) < A1 (vendor test mode / firmware) < B-mp, E-mp (periphery change on an existing array + ~$46K MPW) < A2 ≈ B-E (new array: NAND engineering lot, price unknown) < G (ferroelectric 3D-NAND process, research only) < F (vertical RRAM, no foundry offering) | only the MPW is priced; the rest is unknown |

## 7. Evidence classification

Every claim above falls into one of five classes. Nothing in classes 4-5 should be read as a demonstrated capability.

### 7.1 Experimentally demonstrated facts (measured, or read directly from the released artefacts)
- **K3 as released** (pinned HF revision f831ab6): 2,779.9 G parameters = 2,722.7 G MXFP4 routed-expert weights + 56.7 G BF16 + 11 M FP32; 1,560.86 GB on disk; 93 layers (69 KDA + 24 gated MLA), 896 experts top-16, latent MoE 3,584, dense layer 0. Verified from all 497,220 tensor headers (`data/k3/manifest_totals.json`).
- **K3 numerics on real weights and real text** (this repo, layers 0-3 re-implemented and run): MXFP4 block exponents differ by <=1 inside a 256-element contributor group in 97.4 % of rows (max 3); E2M1 magnitudes are 12 % zeros with rms/max 0.31; MXFP8 activation quantisation alone perturbs an MVM by 1.1 % (dense) to 2.7 % (expert) relative RMS; re-quantising BF16 dense weights to MXINT8 adds 0.12-0.29 %, to MXFP4 adds ~4.8 %.
- **Real K3 routing locality**: neighbouring tokens share 1.6-4.9 of their 16 experts (0.29 expected at random); in a window of 8 tokens one expert serves 4-6 of them (layers 1-3, one 16-token text — a small sample).
- **Commodity 3D NAND timing**: TLC tR 34-50 us, SLC-mode 22.5 us, low-latency SLC (Z-NAND 3 us, XL-FLASH 4 us at 0.6 Gb/mm2); QLC 28.5 Gb/mm2 (280-layer, ISSCC 2024).
- **Commodity NAND logic-in-array**: multi-block activation gives a latched 1-bit AND/OR per bit line (Flash-Cosmos, 160 real chips). No public commodity part exposes a summed analog bit-line current.
- **Analog charge-trap MVM**: 40 nm planar SONOS arrays, sigma ~1.25 % of Imax after program-verify, drift measured over days (the CrossSim SONOS model, built from 128K-device data, used here as the proxy). 3D NAND-based CIM test chips exist (Macronix 32-layer, ~2 nA strings) without public accuracy data at K3-like sizes.
- **GPUs on K3, single user**: 101 tok/s on 8x B300 without speculation, 188 tok/s with a 7-token DSpark draft, 258 tok/s on 8x GB300 with MTP at ~290K context; ~28 J/token single-stream.

### 7.2 Peer-reviewed or preprint simulation results (reproduced here where a simulator was available)
- 3D-FPIM (MICRO'22) NVSim: reproduced the shipped validation points within 7-20 % using literature geometry (authors' geometry unreleased). arXiv 2511.12860: ~2 us per 8-bit MVM only with shrunken 256 x 2048 x 128 planes and 512 ADCs per plane.
- CrossSim 3.2.1: tutorial results reproduced within 2 sigma of the seed spread; `k3cim.analog` agrees with CrossSim's AnalogCore to 0.2-0.4 %.
- NeuroSim V1.4 (built and run here). The manual's Table VII (VGG8/CIFAR-10) baseline reproduces **only partially**: chip area within 7-11 % (RRAM rows only on the original 2024-10-04 code; a later floorplan change shrinks area 77 %), TOPS 4-27 % high, TOPS/W 27-86 % high. Accuracy was not reproduced: the emulated inference took more than 2 h per configuration on this CPU host. A 660-configuration 22 nm 1T1R RRAM subarray sweep gives 97-194 ns and 0.14-5.1 nJ per 8-bit MVM (128x128 to 1024x1024), ADC energy 0.035-1.4 pJ at 4-8 bits, and ~3.4-3.6 M weights/mm2 including periphery. That density is why F needs ~53,000 dies. The model's RRAM timing (0.11-0.82 us per MVM) lies within and above that range (`data/sim_outputs/neurosim/README.md`, `results/simulator_baselines.csv`).
- LLM-on-the-Palm (ICCAD'25): one BF16 MAC unit per Z-NAND plane.

### 7.3 Independently derived bounds (this study; `results/first_principles.md`, `results/workload.md` §9)
- 698 dependent matrix-vector stages per token (1,396 with global reductions), so a 2.9 us stage budget at 500 tok/s.
- Storage floor: 1.50 TB at MXFP4/MXINT8 costs $52 of QLC NAND silicon (normalized) versus $4.5K of DRAM or $18K of HBM.
- Attention floors: 5.0 MFLOP and 27.6 kB (BF16) of MLA latent KV per context token; at 500 tok/s that is 0.33 PFLOP/s and 1.8 TB/s at 128K, and 2.6 PFLOP/s and 14.5 TB/s at 1M.
- Digital streaming needs ~1 G NAND sense amplifiers busy at 500 tok/s with tR = 3 us; analog summation cuts sensing work to ~5.8 G conversions per token (~115K 8-bit ADCs).
- GPU software ceiling: ~330 tok/s on the same 8x B300 node once per-layer synchronisation drops to ~10 us (HBM-bound).

### 7.4 Hypothetical architectures (modelled, not built)
- Redesigned small-plane analog 3D NAND (B-E) with die-level ADC pools and bit-line sample-and-hold; FeNAND (G, speculative parameters); crossbar-density 3D RRAM (F-opt); 0.5 us BLS-scan digital NAND (A2-opt); SRAM-resident FP8 KV attention engines (sram_a/b/c); speculative decoding with a one-layer K3 drafter on CIM (R9).

### 7.5 Unsupported assumptions (flagged in `results/physical_assumptions.csv`)
- Summed-current precision of real 3D NAND strings (poly-Si channels, back-pattern dependence, cell-to-cell coupling) — no public data; SONOS is the proxy.
- The error budget: the thresholds "within" (analog error <= 0.25x the MXFP8 activation error) and "marginal" (<= 1x) are engineering thresholds, not measured accuracy-loss limits (the end-to-end noise propagation through real layers 0-3 is in `results/noise_propagation.csv`; no benchmark-level evaluation was possible without a GPU cluster).
- Bit-line compression model; packaging/assembly/board costs; NAND engineering-lot cost; SRAM leakage; FP8 KV and FP8 attention accuracy for K3; drafter acceptance on non-GPU hardware.

## 8. The single most valuable experiment

**Measure the summed bit-line current of real 3D NAND strings programmed with real K3 weights.**

Every analog NAND design here (B-E, and through it the cheapest 500 tok/s points) rests on one unmeasured number: the error of a C-cell (32-128) bit-line sum in a vertical poly-Si string array, under realistic word-line pass bias, at microsecond settle times, across 0-85 C and over weeks of retention. The simulator results show that this number decides the design outright: with SONOS-class noise, 1- and 2-bit cells with unit-LSB conversion restore exact integer sums (error/budget ~0), while 4-bit cells land at 1.2-1.6x the budget. The cell bits in turn set the NAND silicon cost (~2x between MLC and QLC).

Protocol: a 3D NAND CIM test vehicle (vendor test mode or an academic 3D NAND CIM chip) with raw bit-line access; program-verify one real K3 expert tile (`L1.expert.w1`, 3584 x 3072, MXFP4 codes from the checkpoint) as differential MLC and QLC pairs; drive the recorded K3 activation traces (`data/k3/activations/k3_layers0-3.npz`) as time-encoded inputs; record per-conversion sums for C = 32/64/128 at 25/55/85 C and after 1 h/1 d/7 d/30 d; feed the measured distributions into `k3cim.analog` (device model slot) and `scripts/precision_sweep.py` to get the error/budget ratio. A cheap companion step, before any silicon: run the full K3 on a rented GPU node with the same per-MVM noise injected (the hook in `scripts/noise_propagation.py`) and measure benchmark accuracy versus noise level, which turns the assumed within/marginal thresholds into measured ones.

## 9. Blockers and unknowns (recorded, not guessed)
- **3D-FPIM geometry and Table II** are not public, so plane-level timing uses literature geometry (validated within 7-20 % on the shipped points).
- **No public measurement** of analog bit-line summation accuracy in commercial 3D NAND.
- **MXFP8 activation scope**: the model card says MXFP8 activation QAT, but the config's `input_activations` is null; which matmuls were trained with MXFP8 inputs is unverified, so the budget uses MXFP8 on every input.
- **Costs**: packaging, assembly, test, board, power delivery and the NRE of a custom NAND lot have no manufacturing basis here and are reported as unknown. NAND $/mm2 is market-implied (wafer-equivalent selling price), not fab cost.
- **Drafter**: no public K3 drafter checkpoint; speculative numbers use the DSpark acceptance measured on GPUs.
- **NeuroSim Table VII**: only partially reproduced (area within ~10 % on the original V1.4 code, TOPS/W 27-86 % high, accuracy rows not completed within the CPU budget). NeuroSim results are therefore used only for RRAM subarray latency, energy and area, never for accuracy.
- **Numerics beyond layer 3**: the real forward pass covers layers 0-3 (16 tokens); later-layer statistics are assumed similar.
- **Prefill**: weight-stationary CIM is 20-50x slower than GPUs at prefill (`results/gpu_comparison.md` §5); long prompts need a GPU/NPU prefill partner, which is outside the unit cost.

## 10. Deliverables and how they were produced

| file | content |
|---|---|
| `results/workload.md` | K3 reconstructed from the checkpoint: storage, per-layer matrix dimensions, active weights, KV/KDA state, prefill vs decode, communication, requirements |
| `results/first_principles.md`, `first_principles.csv`, `step_ladder.csv`, `cost_ladder.csv` | floors, requirement audit, step-function and cost ladders |
| `results/architecture_comparison.csv` | per architecture × scenario: cheapest at 100/500 tok/s (32K/128K/1M), fastest; tok/s, J/token, W, dies, ADCs, costs, precision |
| `results/dse_summary.csv`, `results/what_it_takes.csv`, `data/dse_results.csv` | the full sweep (22,008 points) and its summaries |
| `results/latency_breakdown.csv` | per-layer critical-path split for every selected design (32K/128K/1M) and bounds |
| `results/energy_breakdown.csv` | J/token by mechanism (ADC, word-line, bit-line, cell, drivers, links, attention, KV, static), pJ per op |
| `results/precision_sweep.csv` | real-tensor analog precision: cell bits × passes × contributors × ADC bits × devices × calibration × thermal/aging/nonlinearity/spot-check |
| `results/noise_propagation.csv` | per-MVM noise through real layers 0-3: output error and routing stability |
| `results/cost_model.csv` | area, dies, packages, effective bits/weight, ADC count, input drivers, volume cost (normalized/shortage, 128K/1M KV), prototype items |
| `results/physical_assumptions.csv` | every parameter with pessimistic/realistic/optimistic value, evidence class and source |
| `results/gpu_comparison.md` | measured GPU K3 decode, calibrated model, software ceiling, prefill |
| `results/simulator_baselines.csv` | CrossSim, 3D-FPIM, NeuroSim reproductions and the custom-simulator cross-check |
| `results/plots/` | tok/s vs cost (pareto, 3 scenarios, 3 contexts), tok/s vs context, J/token, capacity/area, precision heatmaps and device comparison, latency breakdown, step ladder |

Simulators used for what they model: CrossSim device models (SONOS, RRAM) drive the accuracy study; 3D-FPIM NVSim supplies the NAND plane timing and energy for the small-plane arrays; NeuroSim V1.4 supplies the RRAM subarray latency, energy and area. The K3 scheduler (`k3cim/scheduler.py`) is a deterministic op-level critical-path model calibrated to the measured GPU point (101 tok/s ± 5 %, 188 tok/s with speculation). Extensions beyond what the simulators provide are labelled in code and tested in `tests/`: the die-level ADC pool, time-encoded multi-bit steps with analog accumulation, the speculative-decoding model for CIM, the SRAM-KV engines and the cost model.
