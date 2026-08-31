# GO / NO-GO

## Verdict: **INCONCLUSIVE, leaning NO for the headline claim — with a real niche GO**

The mission's specific claim — a **structural >10× advantage in inference
economics for K3-on-NAND** — is **NO** for general/throughput serving
(falsified, robustly). A **conditional GO** stands only for low-concurrency,
capacity-bound, on-prem serving. The one path that could still change the
picture (firmware-only via an undiscovered NAND primitive) is **INCONCLUSIVE
until the physical BABOL E2 test** — Gate 4 predicts it fails.

## Five strongest pieces of evidence

1. **Simulator is trustworthy**: reproduces LLM-on-the-Palm's 24 published
   latency points within ±1.1% from first principles (sourced constants only),
   MQSim-cross-checked; K3 parameter model matches published 2.78T/104.2B to 0.02%.
2. **>10× falsified for serving**: GPU 8×B300 at batch 256 ≈ 1.9 J/token &
   $0.96/Mtok beats the best NAND build (5 J/token, $1.88/Mtok) by ~2–2.5×;
   holds across the full sensitivity range. Root cause is structural — comparable
   per-bit read energy + GPU batch amortization of K3's 1.8%-active MoE.
3. **Firmware-only is structurally impossible** for GEMV: stock/COTS primitives
   (MCFlash, Flash-Cosmos) give per-bitline booleans on pre-stored operands, not
   cross-bitline sums of stored×runtime products; even a hypothetical fail-bit
   counter loses to export by 25–2500× under MXFP4 block scales.
4. **The required silicon is genuinely tiny**: a multiplier-free MXFP4×MXFP8
   shift-add reducer, bit-exact over 40 M random cases, synthesizes to ~0.03% of
   die area — cheaper per lane than the paper's FP16 MAC.
5. **Sense bandwidth is the sole bottleneck** across a 14 568-point sweep;
   arithmetic and channel are secondary → the conclusion is about NAND array
   physics, not implementation detail.

## Five biggest risks / uncertainties

1. **NAND sense energy is a MODEL range** (87–183 nJ/2KB); the absolute J/token
   and part of the economics ride on it → BABOL E0.7 measurement.
2. **Real tR / SLC-mode availability** on the target part is unknown; the entire
   latency case assumes SLC-class tR → BABOL E0.2/E0.3.
3. **GPU kernel efficiency** (0.4–0.6) and 2026 GPU/NAND pricing are moving
   MODEL inputs; a NAND-price collapse would widen the low-batch GO.
4. **Read-disturb endurance** at ~8 full-array passes/s is assumed correctable
   (10^5–10^6 reads/refresh) → BABOL E3.2; if far lower, refresh overhead grows.
5. **MoE batch ceiling**: if Quantile-Balanced routing skews in production,
   expert-union batching degrades further, worsening the (already losing)
   high-batch case.

## Exact next physical experiment

**BABOL E0.2 + E0.3 + E2.2** on a few dies of MT29F1T08EELEEJ4-R:E: measure
per-page-type tR and any SLC-mode tR, then attempt an exposed, per-32-column-block
fail-bit **count** primitive and time it. PASS if a maskable count returns in
**≤ 1 µs**; FAIL confirms Gate 4's structural NO and locks in the tiny-reducer
silicon path. This single bench session both pins the tR the economics turn on
and settles whether firmware-only K3-on-NAND is alive. Full protocol, prepared
states, command sequences, and pass/fail bounds: `BABOL_TEST_SPEC.md`.

---

## Gate 9 update (physics-aware architecture invention)

The verdict is unchanged and reinforced. Gate 9 built a sense-event-level
simulator, audited the full NAND-compute literature from primary sources, proved
the native-K3 popcount datapath bit-exact, and searched 3,888 composed
architectures. **Best physically-credible native-K3 architecture (K3-FlashReduce):
$0.26/Mtok optimistic / $0.61 central, ~100 tok/s aggregate, ~25–67 tok/s/user,
1–2 J/token** — a genuine **10–40× win over naive/low-concurrency GPU serving**,
but it does **NOT** reach the aggressive Gate-9 targets ($0.10/Mtok + 500 tok/s +
25/user: 0 of 3,888 configs) and does not beat best at-scale GPU K3 serving
(refreshed measured baseline **$0.11–0.36/Mtok**).

New Gate-9 evidence: MCFlash tested our **exact part** (user-mode bitwise ops are
L1 but give no reduction); cr-read is measured on a fabricated array (worth ~2.3×,
F1); Ares-Flash (MICRO'24) independently corroborates the Gate-7 reducer as the
minimum silicon. The **updated highest-impact next experiment is BABOL_TEST_SPEC
E6** — trigger cr-read on the Micron part at ≈10 µs SLC tR (worth ~2.3× on $/Mtok);
E2 (cross-bitline count) remains decisive for the aggressive targets, which require
a new exact more-work-per-sense primitive that no audited mechanism provides.
