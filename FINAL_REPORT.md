# FINAL REPORT — Kimi K3 inference on commodity 3D NAND

Falsification-driven software feasibility study (Gates 0–8). Every number below
is FACT (sourced/measured), MODEL (derived by the calibrated simulator), or
HYPOTHESIS (needs the real-NAND BABOL test). Reproduce via `README.md`.

The simulator is trusted because it reproduces the LLM-on-the-Palm ICCAD'25
paper from first principles: **all 24 published latency points within ±1.1%**,
internal bandwidth +7%, energy −0.7%, using only sourced constants
(`reports/01_palm_reproduction.md`). K3 parameter accounting matches the
published model to **0.02%** (2.7795T total / 104.18B active vs 2.78T / 104.2B).

---

## The 18 questions

**1. Can K3 fit in the modeled NAND capacity?**
FACT/MODEL: Yes, easily. K3 weights = **1.56 TB** (1.45 TB MXFP4 routed experts
+ 0.11 TB higher-precision dense pool), matching the public MXFP4 checkpoint
size. Any ≥2 TB NAND build holds it; a single 132-VBGA package class is ~0.13 TB,
so ~12–16 packages suffice for capacity (bandwidth, not capacity, is the
constraint).

**2. Which exact K3 operations belong in NAND?**
MODEL: the fixed-weight GEMVs — routed-expert W_gate/W_up/W_down (MXFP4), the
LatentMoE W↓/W↑ and shared experts, KDA/MLA weight projections (Wq/Wk/Wv/Wo,
q_a/q_b/kv_a/kv_b, full-rank gates), the dense layer FFN, the router, and the
LM head. These are weight-resident and read every token.

**3. Which remain in conventional logic/DRAM?**
MODEL: all state-dependent work — the KDA recurrent state update (read‑modify‑write
of the 96×128×128 state), MLA attention over the compressed KV cache, Block
Attention Residuals, router top-k/softmax, RMSNorms, sampling, and the KV/state
caches themselves. (Consistent with LLM-on-the-Palm keeping attention on the NPU.)

**4. What is the minimum NAND primitive set required?**
MODEL (Gate 4): a per-plane **lateral SIMD shift+add reducer with retained
accumulators** (the "D_ACC" set): READ + internal SHIFT + internal ADD +
≥8 retained 32-bit accumulators + per-32-column-block scale application, plus a
multi-die broadcast read command (~290 ns/die). Shift-add suffices because E2M1
weights are k/2 (k∈{0,1,2,3,4,6,8,12}) → a product is a 4-term conditional
shift-add, no multiplier.

**5. Could MCFlash-like stock functionality alone plausibly do it?**
MODEL, structural: **No.** MCFlash/Flash-Cosmos give per-bitline **boolean** ops
on two **pre-stored** pages. K3 GEMV needs (a) products of stored weights ×
**runtime** activations and (b) a **sum across bitlines**. Stock page buffers
have no lateral datapath, so no firmware can carry a cross-bitline carry/sum;
and loading a runtime activation as an operand costs a page program (~100 µs +
wear) per use. Even a hypothetical exposed fail-bit counter loses to plain
export by 25×–2500× under MXFP4's per-32 block scales.

**6. If not, what EXACT physical primitive is missing?**
MODEL: a **lateral (inter-bitline) add/accumulate path** across the page-buffer
latches — equivalently any cross-bitline reduction or runtime-operand product.
Everything else needed already exists in stock silicon (sensing, latches, cache
register, multi-die addressing, I/O). This is the single BABOL target (Q0).

**7. How large/fast is the minimum added circuit?**
FACT (Gate 7, Verilator + Yosys/sky130): one lane = 423 cells / 3 372 µm²
(element path) → full lane with FP32 commit + 8 accumulators = 3 362 cells /
28 038 µm². A 4-lane per-plane reducer ≈ **~0.002 mm² at a 2x-nm periphery class
≈ ~0.03% of a die** — same "tiny" class as LLM-on-the-Palm's 0.05% FP16 MAC,
and smaller per lane. Element path runs ≥400 MHz in a modern periphery process.
Bit-exact vs the golden model over **40 M randomized element pairs**.

**8. How many such circuits are required?**
MODEL: one reducer (≥4 lanes) **per plane**. Practical builds: 768 planes
(16 ch × 8 die × 6 pl SLC-mode) to 4 096 planes (64 × 8 × 8). Total added silicon
stays ~0.03% of die area regardless.

**9. Predicted K3 tokens/sec.**
MODEL: single-stream **8–9 tok/s** on a 2 TB SLC-class / 768-plane SLC-mode-TLC
build (115–125 ms/token); **~50 tok/s** aggregate at batch 4 on a 22 TB
64-channel build (79 ms/token). Native TLC/QLC organizations: **0.08–0.14 tok/s**
(plane-count starved). Stock export (no reducer): **0.14–0.50 tok/s**.

**10. Predicted joules/token.**
MODEL: **~8–10 J/token** single-stream (best 2 TB build), **~5 J/token** at
batch 4–8, **~2.2 J/token** floor at batch 64 (unusable latency). Dominated by
cell-read energy (~90%). Range reflects the calibrated 87–183 nJ/2KB-page sense
coefficient; **the physical value is a BABOL E0.7 measurement** (currently MODEL).

**11. Predicted bandwidth inside/outside NAND.**
MODEL: internal weight sensing **~137 GB/token** (≈1.1 TB/s aggregate at 8 tok/s);
external, with the reducer, **~0.27–0.85 GB/token** leaving the die (partials
only) — a ~160–500× internal:external ratio. Without the reducer, 137 GB/token
must leave (the whole point).

**12. Main bottleneck.**
MODEL (Gate 5, robust across 14 568 points): **array sense bandwidth**
(planes × page ÷ tR), once the per-plane reducer keeps up with tR (≥4 lanes).
Arithmetic is cheap and solvable; the channel binds only at batch ≥16.

**13. Sensitivity to NAND tR.**
MODEL: tok/s ∝ 1/tR at fixed plane count (sense-bound). 3 µs→50 µs is the
difference between ~9 tok/s and ~0.1 tok/s at equal planes; the entire viability
case rests on SLC-mode/low-latency tR. (BABOL E0.2/E0.3 measure the real values.)

**14. Sensitivity to TLC/QLC + ECC.**
MODEL: TLC/QLC raise capacity/$ but multiply tR and cut usable plane
parallelism; ECC parity (10–25%) subtracts its share of page payload linearly.
Native TLC/QLC never reach useful latency at sane scale; SLC-mode-on-TLC (paying
~3× capacity) is the practical compromise.

**15. Does it clear the >10× threshold?**
MODEL — **the kill question:**
- **Throughput/datacenter serving: NO (falsified).** A GPU node (8×B300) at
  batch 256 reaches ~1.9 J/token and ~$0.96/Mtok; the best NAND build reaches
  ~5 J/token and ~$1.88/Mtok — **the GPU is ~2–2.5× better**, not NAND. Robust
  across the whole sensitivity range. Root cause: per-bit read energy is
  comparable (NAND 5–11 vs HBM 4–8 pJ/bit) and GPUs amortize bytes/token ~23×
  via large batch, which K3's 1.8%-active MoE + NAND's ~1 TB/s array cannot
  match at useful latency.
- **Low-concurrency / on-prem serving: YES.** Versus a GPU node at batch ≤8
  (dedicated single/few-user deployment), NAND builds clear **12–25× on tokens/$
  (rental basis)** and **~5–9× on J/token**. Plus a minimum-deployment
  granularity edge: ~$3k / 100 W vs ~$550k / 12 kW.

**16. What assumptions dominate the conclusion?**
MODEL: (a) GPU batch amortization — the >10× falsification is entirely about
GPUs reading fewer bytes/token at high batch; (b) NAND sense energy (87–183 nJ/2KB,
BABOL E0.7); (c) that MoE expert-union caps NAND batching at B≈4–8; (d) 2026
NAND $/GB ($0.28 central, shortage-inflated) — at 2024-era $0.10/GB the
low-batch edge roughly doubles but the high-batch verdict is unchanged.

**17. What must be tested on real NAND?**
HYPOTHESIS list → `BABOL_TEST_SPEC.md`: existence of any cross-bitline
reduction / runtime-operand primitive (Q0, decisive); real tR/SLC-mode/geometry/
read energy (E0); read-disturb endurance at ~8 passes/s (E3.2); and the reducer
interface (broadcast + partial drain, E4).

**18. What exact BABOL experiment should we perform next?**
`BABOL_TEST_SPEC.md` E0 (characterize geometry/tR/energy) then **E2 (the
primitive search)** — the single experiment that confirms or overturns the
firmware-only falsification. Detailed prepared states, command attempts,
latency bounds, and pass/fail rules are specified there.

---

## What worked, what didn't, confidence

| Result | Confidence | Basis |
|---|---|---|
| Simulator validity (Palm ±1.1%) | **High** | first-principles reproduction, MQSim cross-check |
| K3 param/traffic model (0.02%) | **High** | TR Table 1 + HF config + vLLM code |
| Firmware-only falsification | **High (structural)** | no lateral datapath argument; BABOL can still overturn |
| Minimum reducer + tiny area | **High** | RTL bit-exact 40 M cases + synthesis |
| Sense-BW bottleneck | **High** | 14.5k-point sweep, closed-form vs sim 4.2% |
| >10× falsified for serving | **Medium-High** | sourced GPU anchors; GPU eff. 0.4–0.6 is MODEL |
| >10× holds at low concurrency | **Medium-High** | same model; depends on NAND $/GB + sense energy |
| J/token absolute value | **Medium** | sense energy is a range until BABOL E0.7 |
| FEMU functional integration | **High** | bit-exact partials + modeled-time match, on real guest |

**Didn't work / limits**: KVM on this host (no `/dev/kvm`) — FEMU runs under TCG
instead (functional only, modeled time used, never wall clock). Native-TLC K3 is
a dead end (documented, not hidden). The M-NAND point in the paper (Fig 16b)
could not be reproduced (its tR is unpublished) — excluded from acceptance.

**Smallest next real-world experiment**: BABOL E0.2+E0.3+E2.2 on a handful of
this part's dies — measure tR and SLC-mode tR, then attempt an exposed
per-32-block fail-bit count in ≤1 µs. That one bench session decides whether the
firmware-only path is alive and pins the tR that the whole economics case turns on.

## Bottom line

Keeping K3's weights in NAND and reducing before they leave the die is
**architecturally sound and needs only ~0.03%-of-die of new silicon**, but it is
**not** a >10× structural win for general serving — GPUs' batch amortization of a
1.8%-active MoE wins there. Its defensible niche is **low-concurrency, capacity-$
-bound, on-prem/sovereign K3 serving**, where it is 12–25× cheaper per token than
idling a GPU node. The decisive open question is physical and narrow: does
commodity NAND have any cross-bitline reduction primitive? Gate 4 says no on
structural grounds; `BABOL_TEST_SPEC.md` E2 is the experiment that settles it.

---

## Gate 9 addendum — physics-aware architecture invention

A dedicated invention phase (reports/07a–07c, `BEST_PHYSICALLY_CREDIBLE_ARCHITECTURE.md`)
audited the primary NAND-compute literature (MCFlash, Flash-Cosmos, AiF, ParaBit,
BABOL, Ares-Flash, CrossBit — several read in full), built a **sense-event-level**
simulator (`sim/sense.py`) that models useful exact-K3 work per physical sense,
proved the **bit-serial popcount decomposition bit-exact** for native MXFP4×MXFP8
(`tests/test_gate9_exact.py`, `k3/validate_exact.py`: full GEMV rel err 0.00e+00),
generated 104 hypotheses in 22 families, and searched 3,888 composed architectures
× 3 cases against complete-appliance $/Mtok (calibrated to reproduce Gate 6 within
~10%).

**New physical facts that reshaped the evidence:**
- MCFlash tested our **exact part** (`MT29F1T08EELEEJ4`): user-mode read-offset
  bitwise AND/OR/XNOR/NOT are **L1**, RBER 0 fresh — but 2-operand, no reduction.
- SLC-mode tR **22.5 µs measured** (48-layer TLC); cr-read **28→9.7 µs, −72% energy**
  (measured on a fabricated 9×9 array + calibrated SPICE; die-internal F1).
- **Ares-Flash (MICRO'24)** independently corroborates the Gate-7 reducer: a
  page-buffer full-adder+shift with **32-bitline shift range = one MX block**.
- BABOL is a **real MICRO'24 controller** tested on a Micron part → the BABOL
  experiments are physically executable.

**Best physically-credible architecture (K3-FlashReduce):** cr-read streaming +
per-plane exact shift-add reducer + SLC many-small-dies + batch/expert-stationary +
optional MTP speculation. Native precision, ≥25 tok/s/user:
**$0.26/Mtok (opt) / $0.61 (central), 103 tok/s aggregate, 1.08–2.27 J/token.**

**Targets verdict (native, ≥25 tok/s/user):** the $0.10/Mtok + 500 tok/s + 25/user
targets are **NOT reached** (0 of 3,888 configs). First-principles: 500 tok/s needs
a 7–23× cut in effective sensed bytes/token; the only exact levers are batch
(latency-limited) and more-useful-work-per-sense (MWS gives **0 exact GEMV MACs**;
count loses at MXFP4 density) — no audited mechanism delivers the cut exactly, so
the **100×-per-sense claim is false for exact K3**. The refreshed GPU baseline
(measured at-scale K3 serving **$0.11–0.36/Mtok, 0.4–1.2 J/tok**) makes the >10×
throughput-serving claim MORE falsified. The step-function **is** real against
naive/low-concurrency GPU serving ($6–12/Mtok): ~10–40× cheaper.

**"10× again":** speculative decoding via K3's native MTP layer (exact, lossless)
buys large per-user speedup (single-user 60→67 tok/s) and the best energy
(0.19 J/tok) but does **not** move the $/Mtok floor — no further step-function
found. The dominant term (array sense bandwidth per native-K3 byte at interactive
latency) has a clear physical lower bound.

**Highest-impact next experiment (updated):** BABOL_TEST_SPEC **E6** — can cr-read
be triggered on `MT29F1T08EELEEJ4-R:E` at ≈10 µs SLC tR? It is worth ~2.3× on
$/Mtok and is the one L3 primitive K3-FlashReduce leans on.

### Final answer to the Gate-9 question

*Given everything physically demonstrated in commodity NAND today, everything
plausibly exposable through firmware/test-mode, and the smallest realistic
peripheral modifications — the cheapest, fastest physically-credible architecture
for unmodified native-accuracy Kimi K3 is **K3-FlashReduce** at **~$0.26–0.61/Mtok,
~100 tok/s aggregate, ~25–67 tok/s/user, ~1–2 J/token***. To reach **500/1000 tok/s,
$0.10/M, or a 10× advantage over the best GPU serving**, a **new physical capability
is required that does not exist today**: an **exact cross-bitline reduction that
resolves ≥5× more native-K3 MACs per physical sense than dense sensing, masks to
32-column MX blocks, and folds multiple bitplanes per sense** — i.e., a
maskable-popcount or exact digitally-corrected analog-sum primitive inside the
array. No audited commodity or near-commodity mechanism provides it. **So the honest
answer is: none yet for the aggressive targets** — but K3-FlashReduce is a genuine
10–40× win over low-concurrency GPU serving and needs only a ~0.03%-die reducer
(Ares-Flash-class, F2) plus cr-read exposure (F1), both physically credible.
