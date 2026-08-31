# Gate 9D/F/G — Physics-aware architecture search results

Run: `python3 experiments/gate9_run.py` (search) + `gate9_useful_work.py`
(bounds) → `results/gate9_all_candidates.csv` (10,368 points),
`gate9_pareto.csv`, `gate9_sensitivity.json`, `gate9_useful_work.json`.
Evaluator (`gate9_architecture_search.py`) reproduces the frozen Gate-6 builds
within ~10% (build B: 54 vs 50.7 tok/s, $2.09 vs $1.88/Mtok) — it is calibrated,
not tuned to win. Every candidate scored optimistic / central / adversarial.
Primary KPI: complete-appliance $/million output tokens at ≥25 tok/s/user, native
K3 precision. Exactness of the in-array datapath is proven bit-exact
(`k3/validate_exact.py`: full 3584-dim latent-expert GEMV, rel err 0.00e+00).

## Target audit (native precision)

| Target | Result |
|---|---|
| T1: ≥500 agg tok/s AND ≥25/user AND ≤$0.10/Mtok | **0 configs** (not reached) |
| T2: ≥1000 agg AND ≥50/user AND ≤$0.05/Mtok | **0 configs** (not reached) |
| Step-function vs best at-scale GPU K3 serving ($0.11–0.36/Mtok) | **NOT achieved** |
| Step-function vs naive single-node GPU serving ($6–12/Mtok) | **ACHIEVED (~10–40×)** |

## Best qualifying architecture (central case, ≥25 tok/s/user, native)

**$0.614/Mtok, 103 tok/s aggregate, 25.8 tok/s/user, 2.27 J/token**
— org `manySmall-8TB` (128 ch × 16 die × 4 planes = 8,192 planes of small 4 GB
SLC-mode dies, 4 KB pages, tR 6 µs) + cr-read + Gate-7 shift-add reducer +
batch 4. Optimistic case: **$0.257/Mtok, 1.08 J/token**. Adversarial: $1.79/Mtok.

Aggregate throughput **saturates at ~105 tok/s** beyond B=4: the array is
sense-bandwidth-bound, so more batch only trades per-user latency for a already-
maxed aggregate. This is the structural ceiling.

## Top-10 (central; native unless flagged NON-QUALIFYING)

| # | $/Mtok | agg tok/s | /user | J/tok | mod | ev | mechanism |
|---|---|---|---|---|---|---|---|
| 1 | 0.61 | 103 | 26 | 2.3 | F2 | L3(cr) | manySmall + cr-read + shift-add + B4 |
| 2 | 0.61 | 103 | 26 | 2.3 | F2 | L3 | same, expert-stationary (ties — reuse already in union) |
| 3 | 0.79 | 83 | 42 | — | F2 | L3 | manySmall + cr-read + B2 (faster/user, dearer) |
| 4 | 1.14 | 60 | 60 | — | F2 | L3 | manySmall + cr-read + B1 (fastest/user) |
| 5 | 1.40 | 50 | 25 | 7.7 | F2 | **L2** | manySmall + shift-add + B2 (**no cr-read — fully commodity-evidenced**) |
| 6 | ~1.9 | 54 | 13 | 3.8 | F2 | L2 | slcTLC-22TB + shift-add + B4 (Gate-6 build B class) |
| 7 | 0.25 | 136 | **0.5** | 0.33 | F2 | L3 | znand-4TB + cr + B256 — NON-INTERACTIVE (fails /user) |
| 8 | 1.97 | 27 | 0.1 | 0.33 | F1 | L3 | failbit-count + B256 — count reducer LOSES (Gate-4 confirmed) |
| 9 | — | — | — | — | F0 | L1 | export baseline — 0.14–0.50 tok/s (Gate-4 floor) |
| 10 | — | — | — | — | — | — | fp8-dense variants: cheaper but **NON-QUALIFYING** (not native) |

## Category winners

- **Best $/Mtok qualifying + interactive**: $0.614/M (config #1). Optimistic $0.257/M.
- **Best $/Mtok any latency**: $0.248/M (znand-4TB, B256) — but 0.5 tok/s/user, useless.
- **Best firmware-only (F0)**: export/MCFlash-bitwise only → 0.14–0.50 tok/s, ~$30+/Mtok.
  Firmware-only remains falsified (no cross-bitline sum on COTS).
- **Best F1 (control-exposure)**: cr-read configs (#1) — cr-read is F1 (die-internal
  control), so the headline architecture is F1/F2, not commodity-firmware.
- **Best F2 (tiny periphery)**: the Gate-7 shift-add reducer configs. Independently
  corroborated by Ares-Flash (MICRO'24): a page-buffer full-adder+shift with 32-BL
  shift range = one MX block.
- **Best energy**: 0.33 J/token (B256, non-interactive); ~1.08–2.27 J/token interactive.
- **Best true in-array compute**: failbit-count / analog-SL — both LOSE (count at
  MXFP4 density; analog is non-exact → NON-QUALIFYING).

## Why the targets are missed (first-principles, `gate9_useful_work.json`)

To hit 500 tok/s the effective sensed bytes/token must fall to ≤6 GB (3 TB/s array)
or ≤20 GB (10 TB/s array) — a **7–23× cut** from native 137 GB. The only exact
levers for that cut are:
1. **Batch** (dense pool ÷B): reaches the cut only at B≈7–23, where per-user latency
   collapses below 25 tok/s. Fundamental tension.
2. **More useful MACs per sense**: MWS AND/OR gives **0 exact GEMV MACs** (can't
   sum); the exposed fail-bit count LOSES at MXFP4 density (needs 32 senses/block,
   below conventional dense sensing). No audited mechanism delivers the cut exactly.

So at ≥25 tok/s/user, native precision, the array's fixed sense bandwidth caps
aggregate throughput, and $/Mtok bottoms out at ~$0.25 (opt) / ~$0.6 (central) —
above the $0.10 absolute target and above best at-scale GPU serving ($0.11).

## Adversarial review (Gate 9G)

- **cr-read dependency**: removing cr-read (pure L2 commodity, no unproven
  primitives) moves the best interactive config to **$1.4/M central / $0.448 opt**
  (50 tok/s agg) — cr-read is worth ~2.3×. Even without it, the architecture beats
  naive-GPU serving by ~5–20× and beats the frozen Gate-6 baseline.
- **Numerical exactness**: the in-array datapath is the Gate-7 shift-add reducer;
  bit-exact over 40 M random cases (Gate 7) + full-GEMV bit-exact (Gate 9E). No
  approximation. fp8-dense and analog branches are labeled NON-QUALIFYING and
  excluded from headline numbers.
- **Economics red-team**: complete-appliance model (NAND dies + SLC 2× capacity
  penalty + F2 periphery markup + controller + DRAM + chassis + power + 3-yr
  amortization + utilization). NRE is separate (below). No component-proxy wins.
- **Source red-team**: cr-read is L3 on our part (measured on a 9×9 array + calibrated
  sim, not MT29F1T08EELEEJ4); failbit-count is L3 hypothesis; every unproven
  primitive is flagged and the no-cr-read delta is reported.

## Prototype vs volume vs marginal economics (NRE separated)

- **Marginal token economics** (structural, above): $0.26–1.4/Mtok interactive.
- **High-volume unit**: the F2 reducer adds ~0.2% die area (AiF: 0.209 mm², 0.2%;
  Ares-Flash: peripheral) → negligible marginal silicon cost; dominated by NAND $/GB.
- **Prototype NRE** (one-time, NOT in $/Mtok): custom periphery mask set +
  controller ASIC ≈ $2–10 M class (typical for a peripheral-metal change on an
  existing NAND process); amortized over volume it vanishes, but it is the real
  barrier to a first appliance and is stated separately, not hidden in unit cost.
