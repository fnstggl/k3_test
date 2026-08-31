# Gate 7 — Fallback RTL: minimal K3 MXFP4×MXFP8 reducer

Gate 4 concluded stock NAND structurally lacks any cross-bitline reduction, so
the fallback is mandatory. This gate derives the smallest circuit K3's actual
arithmetic needs — NOT the Palm paper's FP16×FP32 MAC.

## Design (`rtl/k3_nand_reducer.sv`)

One lane consumes one (E2M1 weight, E4M3 activation) pair/cycle from the page
buffer + broadcast register:

- **No multiplier array.** E2M1 magnitudes {0,.5,1,1.5,2,3,4,6} = k/2,
  k ∈ {0,1,2,3,4,6,8,12} → the product is a 4-term conditional shift-add of
  the 4-bit E4M3 significand (max 12×15=180, 8 bits).
- E4M3 exponent applied as a ≤15-position shift into an exact 30-bit
  per-32-block fixed-point accumulator (the microscaling block boundary the
  Gate 4 analysis proved necessary).
- At block end: E8M0 scales applied as exponent adds; truncating convert to
  FP32; truncating FP32 add into one of **8 retained row accumulators**
  (the D_ACC primitive). The FP32 commit path runs once per 32 elements → can
  be multi-cycled and **shared across 4 lanes**.
- Rounding (truncate-toward-zero at two points) is documented and mirrored
  bit-exactly by `rtl/golden_model.py`.

## Verification (Verilator 5.020, lint clean with -Wall)

- **40 M randomized element pairs** (1.25 M blocks over 4 seeds, full E4M3
  code space incl. subnormals and e=15, all E2M1 codes, E8M0 scales 100–154):
  all 8 row accumulators **bit-exact** vs the Python golden model.
- The randomized suite caught a real bug (22-bit product-shift truncation for
  E4M3 e=15 values 256–448) — fixed; documented as evidence the harness bites.
- Numerical fidelity vs exact double math: ≤6.5e-3 relative after 50 000
  blocks/row (torture case); real K3 rows accumulate 112–224 blocks → ~1e-5
  class, far below MXFP4 quantization noise (~1e-2).

## Synthesis (Yosys 0.33 → sky130_fd_sc_hd tt, ABC mapping)

| Block | Cells | DFFs | Area (µm², sky130 HD) | AIG depth |
|---|---|---|---|---|
| Full lane (element path + FP32 commit + 8 rows) | 3 362 | 336 | 28 038 | 1 156* |
| Element-rate path only (decode + shift-add + 30 b acc) | 423 | 30 | 3 372 | 209 |

*Depth sits in the once-per-32-cycles FP32 commit → multi-cycle by design;
the per-cycle element path (209 AIG ≈ ~35–50 cell levels) supports
~140–280 MHz in sky130's 130 nm class and comfortably 400 MHz+ in the 2x-nm
CMOS used for modern NAND periphery (order-of-magnitude scaling only).

**Per-plane 4-lane reducer** (4 element paths + shared FP32 commit + rows):
~4 600–5 600 cells ≈ 0.04 mm² sky130 ≈ **~0.002 mm² scaled to 2x-nm class** →
~0.016 mm²/die (8 planes) ≈ **~0.03% of a ~50 mm² die** — same size class as
LLM-on-the-Palm's reported 0.05% (their FP16 MAC, 28 nm synthesis), i.e.
**"tiny" is confirmed, with K3's native formats needing even less than an FP16
multiplier per lane.**

> Caveat (per project rules): Sky130/open-PDK results are NOT predictions of
> any NAND vendor's periphery process (different device menu, metal stack,
> under-array constraints). They establish scale class and feasibility only.
> Dynamic power is not reported: Yosys has no power engine; a switching-based
> estimate would not add decision-relevant information at this stage.

## Feedback into the system model

The Gate 3/5 system assumption (4 lanes/plane @ 400 MHz) is exactly what the
synthesized element path supports in a modern periphery process; no system
numbers change. If a vendor process held the lane to 200 MHz, doubling lanes
(8×423 cells — still tiny) restores the rate: the sense-bound conclusion of
Gate 5 is robust to ±2× on lane frequency.

## Reproduce

```
make rtl           # lint + build TB + 3x400k-block equivalence + synthesis
```
Artifacts: `results/rtl/synthesis_summary.json`, `lane_stat_sky130.txt`,
`element_path_stat_sky130.txt`.
