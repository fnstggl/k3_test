# Gate 4 — Minimum stock-NAND primitive search

Run: `python3 experiments/primitive_search.py` → `results/primitive_search.csv`.
Workload: exact K3 decode (Gate 3): 104.2 G MACs/token against 137.0 GB/token of
NAND-resident weights (25.8 GB MXFP4 experts + 111.1 GB BF16 dense-active pool).

## What stock NAND actually offers (classification, with sources)

**KNOWN STOCK** (datasheets/ONFI): page sense to data register (tR); cache
register; data-out through the column decoder onto the 1B-wide channel;
program; copyback (die-internal move via register); multi-plane ops; read-retry
reference-voltage adjustment (set-features / vendor sequences); suspend/resume;
per-bitline latch stacks (SLC: ~2–3 latches; TLC: ~5 incl. sense+cache+3 data —
used by program logic, not user-addressable as an ALU).

**LITERATURE-DEMONSTRATED ON COTS** (no silicon change, real chips):
- Flash-Cosmos (Park et al., MICRO 2022): multi-wordline activation in real 3D
  NAND → bulk AND (and OR via complements) of pages *stored in the same block*;
  reliability boosted by enhanced SLC programming.
- MCFlash (arXiv:2605.05119 / J. Supercomputing 2026): NOT/OR/AND/XNOR on COTS
  3D NAND via MLC encoding + tuned read-reference voltages; zero RBER over
  10 chips × 3 generations, user-mode commands only.
Both produce **per-bitline boolean results of pre-stored operands**.

**VENDOR/UNDOCUMENTED POSSIBILITY**: program-verify logic contains a fail-bit
counter (it counts bitline mismatches against a verify target each program
pulse). If some vendor command exposed an on-demand "XNOR-against-latch and
report count" (never publicly documented), it would be the only stock-adjacent
cross-bitline reduction. This is a primary BABOL probe target.

**REQUIRES NEW SILICON**: any lateral (inter-bitline) datapath — shift, add,
popcount tree, accumulators, MAC lanes. Stock page buffers have *no* horizontal
wiring except the column-decoder I/O mux.

## Why firmware-only fails for K3 GEMV (the impossibility argument)

A GEMV partial sum needs (1) products of **stored weights × runtime
activations**, and (2) a **sum across thousands of bitline positions**.

1. *Operand mismatch*: MCFlash/Flash-Cosmos boolean ops combine two **stored**
   pages. Getting a runtime activation vector into cells costs a page program
   (~100 µs + wear + block management) per operand per use — 4–5 orders of
   magnitude off the ~µs/page budget, and it still only yields booleans.
2. *No reduction*: every COTS-demonstrated primitive returns one bit **per
   bitline**. Summation requires lateral movement of information. The only
   stock lateral path is the column-decoder I/O bus — i.e. **exporting the
   data**, which is exactly what we are trying to avoid. Carry propagation
   (hence addition, hence any popcount/summation) is impossible without a
   lateral datapath. This is structural, not a command-set gap: **no firmware
   can sum across bitlines on stock silicon.**
3. *The one stock-adjacent counter is format-broken for K3*: even granting an
   exposed fail-bit counter (A2), MXFP4's per-32-element E8M0 scales mean a
   whole-page count is meaningless; counting must be masked per 32-column
   block → 4 096 masked count ops per 16 KB bitplane pair. At any plausible
   count-op latency (1–100 µs) this is 25×–2500× *slower than just exporting
   the weights* (table below).

## Results (K3, native precisions; full table in CSV)

| Primitive set | Class | SLC-2TB (2048 pl) tok/s | leaves NAND/token | TLC-2TB (64 pl) tok/s |
|---|---|---|---|---|
| A0_EXPORT (stock read-out, compute in controller) | KNOWN STOCK | 0.50 | 137 GB | 0.136 |
| A1_BOOL (+MCFlash/Flash-Cosmos) | COTS-DEMONSTRATED | 0.50 (no GEMV benefit) | 137 GB | 0.136 |
| A2_CMP_CNT (hypothetical count op, 1 µs) | VENDOR-POSSIBLE | 0.020 | 313 GB (counts) | 0.001 |
| B_SHIFT (shift only) | NEW SILICON | 0.50 (cannot sum) | 137 GB | 0.136 |
| C_ADD (SIMD shift+add @50 ns/pass) | NEW SILICON (tiny) | **5.76** | 2.1 GB | 0.136 |
| D_ACC (C + retained accumulators) | NEW SILICON (tiny) | **5.76** | **0.27 GB** | 0.136 |
| E_MAC (4×400 MHz lanes, Palm×4) | NEW SILICON (small) | 5.76 | 2.1 GB | 0.136 |

Reading the Pareto surface:
- **The minimum set that keeps K3 dot products inside NAND is C_ADD-class:
  a per-plane SIMD lateral shift+add over the page-buffer latches with
  per-32-block partials.** D_ACC (retained accumulators) adds an 8× cut in
  exported partials and removes per-page drain scheduling; its cost is ~8×32b
  registers/plane — take it. Neither more (E_MAC's FP16×FP32 multiplier) nor
  less (booleans, counts, shift-only) sits on the frontier.
- At 50 ns/pass, C/D matches the full MAC engine (both sense-bound): the
  compute primitive only needs to keep up with tR. On slow commodity TLC
  (tR≈50 µs) even a 200 ns-pass bit-serial engine hides completely — but there
  the *array organization* (64 planes) caps everything at 0.136 tok/s, so the
  TLC problem is plane count, not compute (→ Gate 5).
- E2M1 makes the multiplier degenerate: weight magnitudes are
  {0,.5,1,1.5,2,3,4,6} = (k·a)>>1 with k ∈ {0..4,6,8,12} → per activation bit
  ≤2 shift-adds. ~17 SIMD passes/page cover MXFP4×MXFP8 including the block
  scale chain; BF16 dense pool needs ~40 passes (bit-serial) — still under a
  3 µs tR at ≤75 ns/pass. Gate 7's RTL verifies pass counts and measures the
  actual area/frequency.

## The critical final statement (BABOL specification input)

To reach ≥5 tok/s single-stream K3 on a 2 TB / 2 048-plane SLC-class array
(and to beat plain export at all), commodity NAND would need at minimum:

1. **A lateral SIMD add/shift primitive across page-buffer latches**, operating
   on ≥17 passes per 2 KB page within tR (≤ ~175 ns/pass at tR=3 µs; ≤ ~2.9 µs/pass
   at tR=50 µs), with per-32-column-block partial boundaries (≥18-bit block
   accumulators) — **no such primitive is documented or COTS-demonstrated; it
   is structurally absent from stock page buffers.**
2. **≥8 retained 32-bit accumulators per plane** (row-chunk accumulation
   across a page sequence).
3. A multi-die broadcast read/PIM command (~290 ns/die/window, ONFI-class
   timing — mechanism exists: CE#-overlapped addressing, vendor opcode).
4. Input broadcast of ≤0.5–1 KB per window on the existing DQ bus (stock).

Falsifiable stock hypotheses for BABOL (what could still overturn the
impossibility): (a) an undocumented latch-to-latch op WITH lateral carry
(no public evidence; would be visible as an anomalous data transform under
vendor test-mode sweeps); (b) an exposed on-demand fail-bit count with
per-column masking at ≤1 µs (would still lose to export by ~25× for K3's MX
format — measurable, then dismissible); (c) analog multi-bitline current
summation readable via any status/register path (no known stock ADC on the
source line). Absent (a)–(c), **firmware-only K3-on-NAND is falsified, and the
fallback (Gate 7) — a tiny per-plane shift-add reducer — is the minimum
silicon addition.**
