# BABOL_TEST_SPEC — real-NAND experiment specification

Target: **Micron MT29F1T08EELEEJ4-R:E** (3D TLC, 1 Tb, x8, 132-VBGA DDP, EOL;
all internal geometry/timing publicly unknown — see
`configs/nand/mt29f1t08eeleej4_r_e.yaml`). Platform: BABOL-class raw-NAND
controller with direct ONFI bus mastery — arbitrary command/address/data
cycles, independent CE#/R‑B# per die, ≤10 ns-resolution R/B# timing capture,
and Vcc/Icc instrumentation on the NAND supply rails.

This spec converts the Gates 0–7 simulation campaign into falsifiable hardware
questions. The headline question:

> **Q0. Does ANY user- or vendor-mode command sequence give commodity NAND a
> cross-bitline arithmetic/counting primitive (a sum/count across a page's
> bitlines, or a runtime-operand product), at a latency that beats exporting
> the weights?** Gate 4 concluded structurally NO for documented and
> COTS-literature-demonstrated capabilities. These experiments either overturn
> that (→ firmware-only K3-on-NAND lives) or close it (→ the tiny per-plane
> reducer of Gate 7 is the minimum required silicon).

Performance context the answers plug into (calibrated model, Gates 3–5):
- Plain read-and-export of K3 weights caps at **0.50 tok/s** (hypothetical
  SLC-class 2 TB / 2048-plane array) or **0.136 tok/s** (this part's TLC-class
  64-plane organization), with **137 GB/token** leaving the package.
- An internal reducer that keeps up with tR yields **5.8 / 0.14 tok/s** with
  **0.27 GB/token** leaving — worth ~11.6× on the SLC-class organization and
  ~nothing on native 64-plane TLC (there the array, not compute, binds, so the
  organization must also change — see E5).

Every quantity this part needs but does not publish is a sweep variable in the
model; E0 replaces those sweeps with measured values.

---

## E0 — Baseline characterization (prerequisite)

Prepare: fresh/erased blocks, room temperature, nominal Vcc.

| # | Measure | Method | Feeds |
|---|---|---|---|
| E0.1 | Geometry: dies, planes/die, page + spare bytes, pages/block, blocks/plane | READ ID (90h) + Read Parameter Page (ECh) | fills `configs/nand/…yaml` unknowns |
| E0.2 | tR by page type (LSB/CSB/MSB), 1000 pages × 10 reads | issue 00h‑…‑30h, time CE‑low→R‑B‑high | real tR for the sweep (replaces MODEL 40–90 µs) |
| E0.3 | SLC-mode availability + tR_slc | vendor Set-Feature / one-shot-program-mode sequences | decides the SLC-mode-on-TLC frontier (Gate 5 build A/B) |
| E0.4 | Multi-plane read support + effective per-plane concurrency | two-plane 00h‑32h‑…‑30h; compare aggregate vs single-plane tR | plane-parallelism realism |
| E0.5 | Cache-read / read-look-ahead (31h/3Fh) presence | issue cache-read chain; check pipelined data-out | validates the "cache register overlaps sense" model assumption |
| E0.6 | ONFI I/O rate (data-out MT/s) | timed page data-out | channel-bound axis |
| E0.7 | Read energy: Icc·Vcc·tR per page sense | integrate supply current across a sensed read | **resolves the Gate-2 energy range** (87–183 nJ/2KB is MODEL) |

Pass/continue: E0.1–E0.2 succeed (they must; standard ONFI). E0.3/E0.5 outcomes
are inputs, not gates.

---

## E1 — Bit-exact export baseline (control)

Establish the honest floor every "in-NAND" result must beat.

- **Prepare**: program a known K3 MXFP4 weight tile (one 92-layer expert's
  W_gate, ≤ 8 pages) into a block, bit-packed per the layout in `k3/mapping.py`.
- **Sequence**: ordinary page reads → export all bytes → host computes the dot
  product against a fixed MXFP8 activation vector.
- **Measure**: wall time and Joules for the read+export of N pages; bytes off-die.
- **Expected** (model): sense-bound at measured tR; ≈ full page bytes/token
  leave the die. This is A0_EXPORT.
- **Record** as the reference point for every E2–E4 speedup/energy claim.

---

## E2 — Firmware-only cross-bitline primitive search (the decisive experiment)

Goal: find, or rule out, a command sequence that produces a **sum or count
across bitlines** (or a runtime-operand product) without exporting per-bitline
data. Each probe is declared FALSIFIED-NEGATIVE if it does not, within the
latency bound, yield a value that depends on more than one bitline's content.

| # | Probe | Prepared NAND state | Command attempt | PASS (firmware-only lives) | FAIL |
|---|---|---|---|---|---|
| E2.1 | **Bulk bitwise** (MCFlash/Flash-Cosmos class) | two pages A,B in same block, known bit patterns | multi-wordline activation / tuned‑Vref read (per MCFlash arXiv:2605.05119) | data-out = A AND/OR/XNOR B, RBER≈0 | not reproducible on this part |
| E2.2 | **Exposed fail-bit count** | page vs a programmed "expected" latch value differing in K known bitlines | program-verify status / vendor read-status that returns a mismatch count | status returns K (±ECC) in ≤ **1 µs** | no count field, or count > **1 µs**, or masked-per-32-block impossible |
| E2.3 | **Analog bitline-current sum** | page with W set bits on a wordline | any status/register/ADC path reflecting summed source-line current | a readable value monotone in W | none exists |
| E2.4 | **Latch-to-latch lateral op** | data in cache + data register | copyback / internal-move / vendor latch ops, checked for any lateral (inter-column) mixing | output column j depends on input column ≠ j | outputs are per-column identity (no lateral path) |
| E2.5 | **Runtime-operand product** | weight page in array; activation shipped as the "verify"/program-data operand | any read-mode that combines shipped data with stored cells arithmetically | output = f(stored·shipped) beyond bitwise | only bitwise or none |

**Latency bounds that make a positive result useful** (from the model, so a
"yes but slow" is scored correctly):
- A per-page reduction primitive must complete in **≤ tR** (measured E0.2) to be
  sense-bound; concretely **≤ ~3 µs** if this part supports an SLC mode near
  Z-NAND, else **≤ measured tR_tlc** (~40–90 µs).
- For E2.2 specifically: MXFP4's E8M0 scale is shared per 32 elements, so a
  usable count must be **maskable to a 32-column block**; a whole-page-only
  count is scored FAIL for K3 even if fast. Budget: **≤ 1 µs per 32-block masked
  count** (above this, counting loses to export by >25× — Gate 4).

**Decision rule.** If every E2 probe is FAIL: Q0 = NO is confirmed on real
silicon → firmware-only K3-on-NAND is falsified; proceed to treat Gate 7's
reducer as the minimum silicon. If any probe PASSES within its bound: re-open
the Gate 4 primitive search with the measured primitive and re-price.

---

## E3 — Read-path viability for weight-resident inference

Independent of E2, confirm the array can be driven as an inference weight store.

- **E3.1 Sustained sequential read bandwidth** per die and per channel
  (streaming reads across a block): compare to E0.6 × plane count. Feeds the
  real aggregate internal-bandwidth ceiling.
- **E3.2 Read-disturb budget**: re-read one page/block 10^4–10^7 times without
  intervening program; record RBER onset. **This sets the refresh cadence** the
  Gate 6 endurance argument assumed (10^5–10^6 reads MODEL). PASS if RBER stays
  ECC-correctable for ≥10^5 reads between refreshes at the intended read rate
  (~8 full-array passes/s).
- **E3.3 SLC-mode retention/BER** (if E0.3 positive): does SLC mode give the
  low-BER/no-heavy-ECC regime the LLM-on-the-Palm calibration relies on?

---

## E4 — Fallback-reducer emulation contract (if E2 = all FAIL)

If new silicon is required (expected), BABOL still validates the *interface* the
Gate-7 reducer needs, using the host to stand in for the not-yet-fabricated lane:

- **E4.1** Broadcast an MXFP8 activation vector to K dies via CE#-multiplexed
  writes on the shared DQ bus; confirm one broadcast serves K dies (the
  channel-scope input model, Gate 2). Measure per-window command overhead;
  **target ≤ ~290 ns/die** (the ONFI sequence the model uses).
- **E4.2** Read one weight page, compute the Gate-7 reducer's exact
  shift-add+block-scale datapath **on the host**, and confirm the 8×4B partials
  match `rtl/golden_model.py` bit-for-bit for real programmed K3 weights
  (closes RTL↔real-data loop; the RTL is already bit-exact vs the model over
  40 M random pairs).
- **E4.3** Confirm ≥8 retained accumulators' worth of partials per plane can be
  drained per column sweep within the channel budget (Gate 4 D_ACC assumption).

---

## E5 — Organization decision (this specific part)

The model says native 64-plane TLC binds on the array, not compute. Measure to
confirm the required change:
- With E0.1/E0.4 real plane count P and E0.2 real tR, compute this part's
  achievable tok/s = (P·page/tR)/137 GB. **If < ~1 tok/s** (expected for a
  2-die-package part), the conclusion is: **this EOL part is a
  characterization vehicle for E0–E4 primitives, NOT a deployment target**;
  a deployable build needs the Gate-5 organization (many SLC-mode dies,
  ≥768 planes). State this explicitly in the BABOL write-up.

---

## Minimum real-NAND capabilities the design requires (summary)

For firmware-only K3-on-NAND to be viable, ALL of the following must be found on
real silicon (Gate 4 predicts they are NOT):
1. A cross-bitline reduction (sum/count) OR runtime-operand product primitive
   (E2), maskable per 32-column block, latency ≤ tR (≤~3 µs SLC / ≤ tR_tlc).
2. A way to load runtime activations as an operand without a per-use page
   program (E2.5) — else even a bitwise primitive is unusable for GEMV.
3. Read-disturb endurance ≥10^5 reads/refresh at ~8 passes/s (E3.2).

If (1) or (2) fails (expected), the minimum **added silicon** is the Gate-7
per-plane reducer: a multiplier-free MXFP4×MXFP8 shift-add datapath + 8×32-bit
retained accumulators + per-32-block scaling, ~0.03% of die area, running one
element/cycle at ≥400 MHz (equivalently ≥17 SIMD passes within tR). BABOL then
validates its interface via E4, and fabrication is the next hardware step beyond
BABOL.

## What is proven physically vs what remains modeled

- BABOL **can** settle Q0 (primitive existence), real tR/energy/geometry
  (E0), the export baseline (E1), read-path viability + read-disturb (E3), and
  the reducer's data/command interface (E4) — all on this exact part.
- BABOL **cannot** produce a fabricated in-NAND reducer; E4 emulates its
  interface with the host. Full silicon validation is a separate tape-out.
- Nothing in FEMU (Gate 8) or the open-PDK synthesis (Gate 7) substitutes for
  E0/E2/E3 — those are the irreducibly physical measurements.
