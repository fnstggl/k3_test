# BABOL_TEST_SPEC — real-NAND experiment specification

Target: **Micron MT29F1T08EELEEJ4-R:E** (3D TLC, 1 Tb, x8, 132-VBGA DDP, EOL;
all internal geometry/timing publicly unknown — see
`configs/nand/mt29f1t08eeleej4_r_e.yaml`). Platform: BABOL-class raw-NAND
controller (direct ONFI bus mastery: arbitrary command/address/data cycles,
CE#/R/B# per die, µs-resolution timing capture, Vcc/Icc instrumentation).

This spec converts the simulation campaign (Gates 0–7) into falsifiable
hardware questions. The headline question it must settle:

> **Q: Does ANY user- or vendor-mode command sequence give commodity NAND a
> cross-bitline arithmetic/counting primitive?** Gate 4 concluded structurally
> NO for documented + literature-demonstrated capabilities; the experiments
> below either overturn that (→ firmware-only lives) or close it (→ the tiny
> per-plane reducer of Gate 7 is the minimum silicon).

The performance context the answers plug into (from the calibrated model):
- Plain read-and-export of K3 weights caps at **0.50 tok/s** (SLC-class 2 TB
  array) / **0.136 tok/s** (this part's TLC class organization) with
  137 GB/token leaving the package.
- An internal reducer that keeps up with tR turns the same arrays into
  **5.8 / 0.14 tok/s** with 0.27 GB/token leaving — i.e. the primitive is
  worth ~11.6× on the SLC-class organization, and nothing on 64-plane TLC
  (there the array, not compute, binds — capacity/organization must change too).

---

## E0 — Baseline characterization (prerequisite; 1–2 days bench time)

Prepare: fresh blocks; room temp; nominal Vcc.

| # | Measure | Method | Feeds |
|---|---|---|---|
| E0.1 | READ ID / parameter page (geometry: dies, planes, page+spare size, blocks) | ONFI 90h/ECh | configs/nand yaml unknowns |
| E0.2 | tR distribution: TLC lower/middle/upper page; 1000 pages × 10 reads | R/B# timing capture | sweep tR axis (real values) |
| E0.3 | SLC-mode availability + tR_slc (vendor set-feature / block-mode) | try ONFI Set Feature + known vendor sequences (A2h class) | the SLC-mode-on-TLC frontier config |
| E0.4 |