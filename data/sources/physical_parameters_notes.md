# Physical-parameter notes for analog/digital CIM on NAND/RRAM (LLM inference)

Companion to `physical_parameters_sourced.csv` (145 rows) and `nand_geometry_for_3dfpim.csv`.
Compiled 2026-10-12.

Evidence classes in the CSV:

- `measured_silicon`: a fabricated chip or device.
- `peer_reviewed_simulation`: a simulation, model or analytical bound from a paper or arXiv preprint.
- `vendor_datasheet`: vendor or consortium claims.
- `industry_estimate`: teardowns, press tables and summary tables.
- `derived`: computed from sourced numbers; the formula is in the row.
- `unknown`: no credible number was found.

## Access caveats

IEEE Xplore and the ACM DL could not be reached, OpenAlex was rate-limited, and the FMS/AnandTech archives were blocked. Several numbers from ISSCC silicon papers therefore come through secondary pages: ComputerBase, TechInsights, Blocks & Files, vendor R&D pages, or other papers' reference lists. These rows keep `measured_silicon`, because the primary source is a chip measurement, and `source_short` names the intermediary. When precision matters, check them against the ISSCC digest.

---

## A. Commodity 3D NAND

### What commodity silicon shows

**Page read latency (tR):**

- **TLC, ISSCC dies 2021-2023:** 34-50 µs (ComputerBase table of the ISSCC papers).
  - SK hynix >300L: 34 µs. SK hynix 238L: 45 µs. Samsung V7: 40 µs. Kioxia/WD BiCS6: 50 µs.
  - Kioxia/WD 8-plane 1 Tb (VLSI 2023): 40 µs.
  - BiCS10 (ISSCC 2025): tR 4 µs (10 %) lower, so about 36 µs (derived).
- **QLC:** 110 µs on Samsung's ISSCC 2020 1 Tb QLC part. No later absolute QLC tR was found.
- **SLC mode of a 48L TLC chip:** 22.5 µs, measured on 160 real chips (Flash-Cosmos).
- **Low-latency SLC products:**
  - Samsung Z-NAND: tR 3 µs, tPROG 100 µs, 2-4 KB pages, 64 Gb die, 0.6 Gb/mm².
  - Kioxia XL-FLASH: tR 4 µs, tPROG 75 µs (ISSCC 2020 / JSSC 2021). The vendor states "<5 µs", 16 planes and 4 KB pages.
  - Low latency is bought with very low density: about 40x below 2024 QLC.

**tR breakdown (the most useful decomposition found).** Park et al. measured 160 chips (ASPLOS 2021):

- tR = N_sense × (tPRE + tEVAL + tDISCH), with tPRE, tEVAL, tDISCH = 24, 5, 10 µs.
- N_sense is 1 for SLC and up to 3 for a TLC page.
- **BL/sense-node precharge dominates.** Precharge can be cut 47 % within the ECC margin; evaluation can be cut only about 10 %.
- Flash-Cosmos confirms this: WL precharge stays hidden behind BL precharge until more than 8 blocks are activated.

**Program and erase:**

- tPROG: SLC 200 µs, MLC 500 µs, TLC 700 µs (48L, measured). Samsung 48L TLC: 660 µs. Samsung QLC: 2 ms.
- tBERS: 3.5-5 ms.
- TLC program throughput: 160-300 MB/s (ISSCC 2021-2024 titles). SK hynix 321L 2 Tb QLC: 75 MB/s.

**Density, layers and organisation:**

- Areal density 2022-2026: 14.6-15 Gb/mm² for 232/238L TLC (TechInsights), 20 Gb/mm² for SK hynix >300L TLC, 28-29 Gb/mm² for Samsung 280L QLC, Samsung 4XX-layer TLC and BiCS10 TLC, and above 37 Gb/mm² for BiCS10 QLC (2026 press).
- Implied 1 Tb die area: about 35-50 mm² (derived).
- WL layers: 218 to about 400 (Samsung "4XX", Kioxia 332).
- Planes: 4-6 for mainstream dies, 8 for Kioxia/WD VLSI 2023, 16 for XL-FLASH.
- Page size: 16 KB.

**I/O:** 2.4 Gb/s per pin (2022-2023), 3.2-3.6 Gb/s (Samsung V9, Micron G9 on ONFI 5.1), 4.8 Gb/s (Toggle DDR6.0, BiCS10) and 5.6 Gb/s per pin (Samsung ISSCC 2025). An x8 bus therefore carries 2.4-5.6 GB/s per channel.

**Endurance (industry and vendor figures, not per-part datasheets):**

- SLC: about 100k cycles.
- 3D TLC: 1k-3k cycles.
- QLC: about 100-1.5k cycles.
- Z-SSD: 30 DWPD at the drive level.

### Biggest constraints on sequential operation

- **Latency per sequential op:** about 3-4 µs on SLC low-latency parts, 20-25 µs in SLC mode on a standard array, 35-50 µs on TLC and around 100 µs on QLC. That 3-4 µs floor applies only to small-page, low-density parts.
- **Read energy:** no vendor ICC was retrieved.
  - One published assumption (LLM-on-the-Palm, ICCAD 2025, from Micron's power calculator) is ICC1 = 70 mA at 3.3 V, about 231 mW per die during a multi-plane read.
  - Derived example: at tR = 40 µs this is about 9 µJ per multi-plane read. For 4 × 16 KB pages that is about 18 pJ per sensed bit, before I/O.

### Gaps (`unknown` in the CSV)

- BL capacitance per BL, WL RC, BL precharge voltage and the actual read string current on commodity parts.
- Absolute tR for Samsung V9/V10, Micron G9, SK hynix 321L and YMTC 294L.
- Datasheet ICC values.
- Per-product P/E ratings.

### Geometry for 3D-FPIM

See `nand_geometry_for_3dfpim.csv`. The Samsung 64L dimensions that 3D-FPIM used come from a paywalled TechInsights report (3D-FPIM ref [46], K9AFGD8H0A).

**Public anchors:**

- Samsung 64L: 71 gates, 20 nm BL half-pitch, 9 holes between CSLs (TechInsights).
- Samsung 32L: 120 nm hole, 22 nm ONO, 11 nm poly channel, about 775 nm slit pitch, about 20 µm staircase.
- Samsung 128L/176L: WL pitch 44/43 nm.
- Generic TCAD stacks: Synopsys 2019, SISPAD 2019, and 3D-FPIM ref [47] (Micromachines 2021).

**Estimates and checks:**

- Estimates are labelled low or medium confidence, with ranges.
- The estimated set was run through `Calculate.py` in scratch only (a copy). It gives about 15 aF of gate-channel capacitance per cell.
- **`Calculate.py` constraint:** it requires `L_g - 2*Barrier_width` (its L_spacer) to be larger than `t_ox`. Otherwise the outer-fringe capacitance C_of_gex2 goes negative; L_g = 27.5 nm, Barrier = 3 nm, t_ox = 22 nm was verified to give -1.3e-19 F.

---

## B. NAND-based compute-in-memory

### Commodity silicon, unmodified arrays (digital in-flash ops only)

**Flash-Cosmos (MICRO 2022), 160 real 48L chips.** It uses vendor test/feature commands.

- Intra-block multi-WL sensing gives a bitwise AND of up to 48 WLs at 1.033 × tR.
- Inter-block sensing gives a bitwise OR across blocks that share BLs: 1.033 × tR for up to 4 blocks and 1.363 × tR for 32 blocks.
- Power is 1.34x a normal read at 2 blocks and about 1.8x at 4 blocks.
- RBER is below 2e-12 with ESP programming (tESP = 400 µs).
- **So commodity chips can activate several blocks/strings on the same BL at once.** Erase-verify and multi-block test modes already do this.
- **The result is still one latched bit per BL (wired AND/OR). The summed BL current cannot be read through the page buffer.**

**MCFlash (arXiv 2026):** AND/OR/XNOR/NOT on COTS Micron 64L FG and 176L CT chips using only user-mode read-offset commands. Each operation takes 40-90 µs (page-read bound), and BER stays below 0.015 % after 10k P/E cycles.

**ParaBit (MICRO 2021):** latch-sequencing for two-operand ops. It needs modified timing control logic; its numbers were not extracted.

### Modified arrays and dedicated silicon (analog summation)

**Macronix 32-layer 3D NAND nvCIM prototype (IEDM 2019, Lue et al.):**

- Modified, industry-grade array. Inputs go on the BLs and the current is summed on the block common source line.
- A 3 nm poly channel gives about 2 nA on-current and under 1 pA off-current, which allows thousands of strings to be summed.
- Precision and energy at chip level are not in the accessible text.

**Kim et al., JSSC 2022 (eNAND, 65 nm logic process):**

- Uses 16-cell strings of 3T eflash cells and sums 28 cell currents on one BL per cycle.
- Cells store 2 bits at 0/3/6/9 µA with σ < 0.6 µA. MNIST accuracy is 98.5 %, within 0.5 % of software.
- 4.95 µW per BL was measured. The 129 TOPS/W figure is estimated, assuming a 50 ns read; the measured read pulse was 2 µs.
- **Not a 3D CT NAND array, and its µA currents are 100-1000x higher than poly-Si strings.**

**SONOS analog (Xiao et al., TCAS-I 2022; IEDM 2022 companion):**

- 40 nm planar SONOS operated subthreshold. Programming error, read noise and retention were measured on arrays.
- ResNet50 is within 2.16 % of floating point. The 20 TOPS/W figure is a system simulation.

### Simulation only

- **3D-FPIM (MICRO 2022):** 2.09x performance per area and 13.18x energy efficiency against a 2D RRAM baseline. Cell current is 3.3-50 nA, input duration 1 ns per bit, 64 stacks, a 130 × 256 subarray and 5-bit inputs. The README states "no fabricated PIM unit available".
- **Shim & Yu (MEMSYS 2020):** WL setup 303 ns / 43.5 nJ, BL setup 12 ns, SL settle 530-750 ns (SL about 16 pF), 7-bit SAR ADC, 37 TOPS/W at 8b × 8b.
- **Jang et al. (arXiv 2025):** a 256 × 2048 × 128 array reaches about 2 µs per MVM with 9-bit SAR ADCs. Accumulation is limited to 256 cells per BL "due to reliability". Naive PIM on a conventional 16 KB-page plane takes 1.4 s per token for OPT-30B.
- **LLM-on-the-Palm (ICCAD 2025):** digital MAC per plane on Z-NAND (tR 3 µs, 1024 MACs in 2.5 µs). This is near-array and digital, not analog.

### Latency implications

- **Commodity silicon:** each "operation" is at least one tR (about 22-50 µs, or 3-4 µs on Z-NAND/XL-FLASH-class parts).
- **Analog PIM:** about 1-2 µs per MVM pass appears only in simulations with shrunk arrays (256 B-2 KB pages, ≤128 stacks). That shrinkage costs density, as shown in Jang et al.'s Fig. 6.

### Gaps

- No 2024-2026 NAND-CIM silicon from Samsung, SK hynix, Kioxia or Micron with summed-current MACs, precision or energy was found.
- Macronix IEDM 2021/2023 numbers could not be retrieved.
- No measured bits-per-MAC or error rate exists for analog summation over more than 28 strings in real 3D CT NAND.

---

## C. RRAM crossbars

### Measured silicon

**NeuRRAM (Nature 2022):**

- 48 cores of 256 × 256 1T1R HfOx in 130 nm, about 3 M devices.
- Conductance window 1-40 µS. Write-verify gives ±1 µS for 99 % of cells, takes 8.5 pulses and about 56 µs per cell.
- **Relaxation after programming has σ ≈ 2.8 µS (up to 3.9 µS).** That is about 7-10 % of g_max, so effective weight precision is about 3-4 bits. Accuracy matches 4-bit quantised software.
- MVM pulses are 10/10/240 ns.

**Other device and macro results:**

- **Rao et al. (Nature 2023):** 2048 conductance levels in 256 × 256 arrays on CMOS, achieved with slow denoising programming.
- **Macros (NTHU/TSMC):**
  - 22 nm 2 Mb: 121-28 TOPS/W.
  - 22 nm 4 Mb 8b-precision: 11.91 TOPS/W at 8b with 14.8 ns latency.
  - 22 nm 8 Mb: 21.6 TOPS/W at 8b.
- **3D vertical RRAM:** 2-8 layers demonstrated (4-layer with FinFET pillar selector at VLSI 2016; 8-layer at LED 2020). The 3D VRRAM CIM macro (Nature Electronics 2022) is 2 kb at 55 nm, reaching 8.32 TOPS/W and 58.2 bit/µm².
- **Embedded RRAM reliability:** 10k cycles and 10 years at 125 °C (TSMC 22 nm).
- **Temperature:** Tα ≈ -0.004 K⁻¹ in the low-G range, with cell-to-cell spread rising to a CV of 33 % in the high-G range. Accuracy drops from 94.5 % to 79.8 % between 300 K and 400 K.

### Gaps

- Cell area in F² for foundry RRAM.
- Density and cost per bit versus NAND: no VRRAM above 8 layers was found, against 200-400 layers for NAND, so RRAM is orders of magnitude less dense per mm².
- I-V nonlinearity numbers.
- Read noise in %: NeuRRAM shows that relaxation dominates.

---

## D. FeNAND (ferroelectric, HZO) 3D NAND

### Maturity

- Research only: devices, small planar arrays and short (4-layer) vertical strings.
- Device-level compilation (Kim et al., arXiv 2025 perspective with Samsung co-authors):
  - Memory window 4.5-14 V.
  - TLC/QLC on single stacks.
  - PGM 13-24 V with 100 ns-100 µs pulses.
  - Endurance about 10^4 (up to 10^6).
  - Retention ">10 yr", often extrapolated.
  - Weak to moderate disturb immunity.
- **Samsung's hafnia + oxide-semiconductor FeFET NAND (Nature 2025):**
  - Claims up to 96 % lower string-operation power with near-zero Vpass.
  - Up to 5 bits/cell on planar arrays (secondary report) and a 4-layer vertical string.
  - No product plans have been announced.

### Gaps

- No 3D FeNAND analog-CIM demonstration with accuracy or energy was found.
- No array-level read latency was found.

---

## E. ADCs

### State of the art (Murmann survey rev. 2026, 751 ISSCC/VLSI entries)

- **Best figures of merit:** Walden FoM 0.354 fJ/conv-step (10b SAR at 0.2 MS/s). Schreier FoM 189.2 dB (NS-SAR, 1 kHz bandwidth).
- **Best Walden FoM at fs ≥ 1 MS/s:** 20 fJ (ENOB 5-6), 3.7 fJ (6-7), 6 fJ (7-8), 4.4 fJ (8-9), 2.05 fJ (9-10).
- **Standalone SAR at 5-8 bits in ≤40 nm:** about 0.8-6 pJ per conversion (median about 1.3-3 pJ) and 0.0006-0.011 mm².
- **ISAAC assumption (Table I):** 8b at 1.2 GS/s, 2 mW and 0.0012 mm² in 32 nm, i.e. 1.67 pJ per conversion (derived). The paper says 1.2 GSps, not 1.28. ADCs are 58 % of tile power and 31 % of tile area.

### Thermal-noise bound (exact form)

P/f_s = 8 kT · SNR, with SNR as a power ratio. This is the "practical limit" for rail-to-rail class-B circuits (Murmann ISSCC 2022 Short Course, slide 66, citing Vittoz 1990).

At 300 K this gives 0.2, 3.2 and 51 fJ for ideal 6, 8 and 10-bit SNR (derived). **Real 8-bit ADCs sit at 0.3-2 pJ, 100-600x above the bound.**

### In CIM

- NeuRRAM neuron (integrate-and-compare ADC): 1270 µm² at 130 nm, 1-10b output, 240 ns integration.
- NAND-CIM simulations assume 7-9b SAR ADCs.
- 3D-FPIM's HSPICE ADC/integrator values (its Table II) were not accessible.

---

## F. Interconnect and I/O energy

- **On-die wire:** about 240 fJ/bit/mm at 40 nm, projected 115-150 at 10 nm (Keckler 2011). Wire energy per mm improved less than 2x from 45 nm to 7 nm (TPUv4i).
- **UCIe:** about 0.5 pJ/bit (2D) and 0.25 pJ/bit (2.5D). Shoreline density 28-224 GB/s/mm (2D) and 165-1317 GB/s/mm (2.5D).
- **Hybrid bonding PHY:** below 0.05 pJ/bit (Synopsys 3DIO, vendor claim).
- **Foveros gen1:** 0.15 pJ/bit.
- **Long-reach SerDes:** 1.4-4.3 pJ/bit (ISSCC 2019-2024 examples). PCIe-specific pJ/bit is unknown.
- **DRAM I/O per 64-bit access (TPUv4i, I/O only):** HBM2 250-450 pJ (3.9-7.0 pJ/bit), GDDR6 350-480 pJ (5.5-7.5 pJ/bit), DDR3/4 1300 pJ (about 20 pJ/bit). HBM3E is 5.74 pJ/bit including I/O (arXiv 2026 modelling).
- **NAND I/O:** 2.4-5.6 Gb/s per pin. **Absolute pJ/bit for ONFI/Toggle is unknown;** only relative figures exist (Kioxia PI-LTT: -10 % input, -34 % output power).

### Gaps

- LPDDR5X pJ/bit.
- PCIe Gen5/Gen6 pJ/bit.
- NAND interface pJ/bit.

---

## G. Digital logic (TPUv4i Table 2: 45 nm from Horowitz 2014, and 7 nm)

- **Integer ops:**
  - INT8 add: 0.03 / 0.007 pJ.
  - INT8 multiply: 0.2 / 0.07 pJ.
  - INT32 add: 0.1 / 0.03 pJ.
  - **INT8 MAC with 32-bit accumulate at 7 nm: about 0.10 pJ (derived).**
- **Floating-point ops:**
  - BF16 add / multiply (7 nm): 0.11 / 0.21 pJ.
  - FP16 add / multiply: 0.40 / 1.1 pJ (45 nm) and 0.16 / 0.34 pJ (7 nm).
  - FP32 add / multiply: 0.9 / 3.7 pJ (45 nm) and 0.38 / 1.31 pJ (7 nm).
- **SRAM per 64-bit read at 7 nm:** 8 KB 7.5 pJ, 32 KB 8.5 pJ, 1 MB 14 pJ.
- **DRAM:** 640 pJ per 32-bit (EIE/Horowitz, 45 nm era).

### Gaps

- FP8 MAC energy.
- 5 nm and 22 nm per-op tables. Scale from these two anchors with caution.

---

## H. Thermal and aging

### Charge-trap NAND

- Program/erase time and RBER depend strongly on temperature from -30 to 70 °C (64L TLC). Read disturb is worse when cold.
- Erase gets harder at low temperature (weaker GIDL).
- Vertical charge loss has widely distributed time constants and near-zero apparent activation energy when programming and retention happen at the same temperature.
- Retention testing uses 13 h at 85 °C ≈ 1 year at 30 °C.
- **Numeric Vth temperature coefficient (mV/°C) and retention slope (mV/decade): not found in open sources** (`unknown`).

### RRAM

Tα ≈ -0.004 K⁻¹, as described in C.

---

## Most decision-relevant takeaways

1. **Commodity NAND has no analog MAC path.** It can activate many WLs or blocks per BL, but each sensing still yields one bit per BL at roughly one tR. Analog summed-current CIM in true 3D CT NAND exists only in modified prototypes (Macronix 2019) or simulation.
2. **The sequential-op latency floor is set by BL precharge.** It is about 3-4 µs for low-density SLC parts and 20-50 µs for dense SLC-mode or TLC arrays. Simulated PIM reaches about 1-2 µs only with shrunk arrays.
3. **ADC energy is not a fundamental limit at 8 bits.** The bound is 3.2 fJ, while practical SAR ADCs need about 1-2 pJ. Digital INT8 MAC at 7 nm is about 0.1 pJ, so one 8-bit conversion costs roughly 10-20 digital MACs.
4. **RRAM analog weights are effectively 3-4 bit after relaxation.** Write-verify is about 56 µs per cell, and stacking is at most 8 layers, so RRAM is far less dense than NAND.
