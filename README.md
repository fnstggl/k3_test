# K3-on-NAND: can commodity 3D NAND serve Kimi K3 with a >10× economics edge?

A falsification-driven feasibility study of a Kimi K3 (2.78T-param MoE) inference
accelerator that keeps weights inside NAND flash and computes the weight-heavy
dot products before the weights leave the die. Two candidate architectures:
(A) stock NAND + firmware only (minimum-primitive search), and (B) NAND + a tiny
per-plane compute unit (LLM-on-the-Palm style, re-derived for K3's MXFP4/MXFP8).

**Headline results** — see `FINAL_REPORT.md` and `GO_NO_GO.md`:
- Firmware-only compute in stock NAND is structurally impossible for GEMV
  (no lateral reduction path in page buffers); quantified in Gate 4.
- The minimum silicon addition is a multiplier-free per-plane shift-add reducer
  (~0.03% of die area; RTL + synthesis in Gate 7).
- The >10× joules/token / tokens/$ claim is **falsified for throughput serving**
  (GPUs amortize weight reads via batch; K3's MoE blocks NAND from doing the
  same) and **holds only for low-concurrency/on-prem serving** (12–25× vs a
  GPU node at batch ≤ 8). Gate 6.
- Next physical step: `BABOL_TEST_SPEC.md` (real-NAND probe plan for the
  Micron MT29F1T08EELEEJ4-R:E).

## Reproduce everything

```bash
make setup            # pip deps + pinned third-party clones + MQSim build
make test             # 21 unit tests for the simulator core
make reproduce-palm   # Gate 2: LLM-on-the-Palm reproduction (±1.1%)
make k3               # Gate 3: exact K3 workload baselines
make primitive        # Gate 4: minimum-primitive search
make sweep            # Gate 5: 14.5k-point design-space sweep + plots
make economics        # Gate 6: cost/power vs GPU reference
make rtl              # Gate 7: Verilator equivalence (1.2M blocks) + yosys synth
make femu-build       # Gate 8: build patched FEMU (QEMU fork; takes a while)
make femu-guest       # Gate 8: TCG guest run of the PIM_GEMV command
```

Python ≥3.11; pinned deps in `requirements.txt`. Gate 7 needs
`verilator yosys`; Gate 8 additionally `busybox-static nvme-cli zstd
linux-image-virtual` (guest build) — all Ubuntu 24.04 packages.

## Repository map

| Path | Content |
|---|---|
| `CLAUDE.md`, `RUN_STATE.md` | mission rules + persistent run state |
| `references/` | LLM-on-the-Palm paper + extracted parameters (cited); K3 tech report |
| `configs/` | validated K3 architecture; Micron target part (unknowns explicit) |
| `sim/` | transparent unit-explicit NAND-PIM simulator (calibrated in Gate 2) |
| `k3/` | exact K3 workload/param accounting + MX format reference model |
| `experiments/` | one runnable script per gate (provenance embedded in outputs) |
| `results/` | machine-readable outputs (JSON/CSV) + plots + RTL synth artifacts |
| `reports/` | per-gate reports 00–06 with FACT/MODEL/HYPOTHESIS labeling |
| `rtl/` | k3_nand_reducer.sv + golden model + Verilator TB + yosys flow |
| `patches/` | FEMU PIM_GEMV patch (also applied in-tree to the pinned clone) |
| `third_party/` | pinned external repos (`LOCK.md`; cloned by script, never vendored) |
| `FINAL_REPORT.md`, `GO_NO_GO.md`, `BABOL_TEST_SPEC.md` | final deliverables |

## Method in one paragraph

A transparent analytic simulator (Gate 1) is calibrated by reproducing the
LLM-on-the-Palm ICCAD'25 paper from first principles — all 24 published latency
points land within ±1.1% using only sourced constants (Gate 2; MQSim
cross-checks). The exact K3 decode workload (2.7795T/104.18B derived vs
2.78T/104.2B published) then replaces GPT-3 (Gate 3). A capability-ladder
search over NAND-internal primitive sets (Gate 4), a 14.5k-point design-space
sweep (Gate 5), and a sourced economics comparison vs GPU serving (Gate 6)
produce the verdict; a synthesized minimal reducer (Gate 7) and a patched-FEMU
functional run (Gate 8) close the loop. Every number is labeled FACT (sourced),
MODEL (derived), or HYPOTHESIS (needs real-NAND test).
