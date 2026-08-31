# Gate 5 — NAND system design-space sweep

Run: `python3 experiments/sweep.py` → `results/sweep.csv` (14 568 feasible
points), `results/sweep_summary.json`, `results/plots/*.png`.
Evaluator: closed-form steady-state using the Gate-2-calibrated window model;
cross-checked against the step-level simulator on the Gate-3 reference config
(186.5 vs 179.1 ms → 4.2% gap, applied as a fill factor to every point).

## The bottleneck question (required output)

Among top-decile-throughput points per profile:
- **Dense pool (BF16/FP8, 81% of bytes): sense-bound** almost everywhere
  (e.g. TLC 351/384 points). The physical read bandwidth `planes × page/tR`
  is the fundamental limit.
- **Expert pool (MXFP4): compute-bound whenever lanes are skimped** (packed
  4-bit pages carry 3.8× more weights); with ≥4–8 lanes/plane it re-joins
  sense-bound. Arithmetic is a *cheap, solvable* secondary constraint — which
  is exactly why the Gate-4 minimum primitive (slow SIMD shift+add) suffices.
- **Channel binds only at high batch** (input broadcast ×B): 'channel'
  bottleneck appears in 16/54 slc-z top-decile points at B≥16; ONFI 4.8 GB/s
  relieves it (addendum axis in CSV).

**Answer: the physical sense bandwidth of the array is the bottleneck at every
frontier point once the per-plane reducer keeps up with tR; adding silicon
beyond that (more/faster lanes) buys nothing.**

## Frontier highlights (full tables in sweep_summary.json)

Latency-constrained (TPOT ≤ 150 ms), best per capacity class:

| Raw capacity | Profile (all dense-FP8) | Org (ch×die×pl) | B | tok/s | J/token |
|---|---|---|---|---|---|
| 2 TB | slc-z tR=1 µs (hypothetical) | 32×8×8 = 2 048 pl | 1 | 13.5 | 10.4 |
| 4 TB | slc-z tR=1 µs | 64×8×8 = 4 096 pl | 4 | 44.5 | 5.0 |
| **5.5 TB** | **slc-mode-on-TLC tR=15 µs, 6 pl/die** | **16×8×6 = 768 pl** | 1 | **8.0** | 10.4 |
| 22 TB | slc-mode-on-TLC | 64×8×6 = 3 072 pl | 4 | 50.7 | 5.0 |
| 66 TB | tlc-8pl tR=40 µs | 64×8×8 = 4 096 pl | 4 | 29.1 | 5.4 |

Unconstrained-throughput winners per profile are 64-channel, max-die builds —
meaningful only after cost normalization (Gate 6). J/token floor across the
sweep: **2.2 J (B=64, unusable latency); ~5 J at B=4–8 practical; ~8–10 J at B=1.**

## Structural findings

1. **Batch B=4–8 is the sweet spot**: the dense pool (81% of traffic) amortizes
   ÷B while K3's expert union barely grows (D(B)=896(1−(1−16/896)^B): 62 experts
   at B=4 vs 64 drawn). Beyond B≈16, expert reads + ×B input broadcast +
   per-token dynamic traffic erase the gains. MoE sparsity fundamentally caps
   batch-amortization of a weight-streaming design — a structural difference
   from GPU serving (which batches into the hundreds).
2. **SLC-mode-on-commodity-TLC is the practical frontier**: ordinary 1Tb TLC
   dies operated 1-bit-per-cell (a standard vendor mode) give ~3× capacity cost
   but tR ~15–25 µs and no-ECC-class reliability. 128 such dies (16 ch × 8) =
   768 planes → 8 tok/s at 125 ms single-stream. True Z-NAND-class SLC (2 048
   planes/2 TB) doubles that but is a niche part.
3. **Native TLC/QLC never reach useful latency** at sane scale: TPOT ≥ 400 ms
   even at 65–131 TB raw. Density and $/GB advantages die on plane count + tR.
4. **planes × page/tR is the whole game**: tok/s at B=1 tracks aggregate sense
   bandwidth to within the command overhead; see plots
   (`tok_s_vs_planes.png`, `tok_s_vs_tR.png`).
5. ECC parity (10–25%) costs exactly its payload share; read-retry
   (`retry_extra`) multiplies tR — both linear, no cliffs (columns in CSV).
6. tR=1 µs rows are a hypothetical bound (no published SLC part below ~3 µs
   Z-NAND); flagged in profile_space() as MODEL ranges.

## Carried to Gate 6

The economics gate prices three representative builds: (a) 5.5 TB SLC-mode-TLC
16×8×6 (commodity dies), (b) 22 TB SLC-mode-TLC 64×8×6, (c) 2 TB SLC-Z 32×8×8;
against GPU K3 serving. J/token here uses the calibrated 89.4 nJ/KB sense
energy (range 42–89 from the ICC tension, Gate 2) — Gate 6 carries the range.
