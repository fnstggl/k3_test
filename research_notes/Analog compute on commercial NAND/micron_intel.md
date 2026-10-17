# Micron and Intel/Solidigm: NAND compute-in-memory patents, publications and public raw-NAND documentation

Scope: the four Micron applications/patents the user named, related Micron families, Micron's public raw-NAND documents (Set/Get Features), Micron and Intel NAND sensing publications, Intel/Solidigm CIM work, and ways to get access. Research date: 2026-10-17.

Method note: I downloaded the full text of the four core patents from Google Patents and parsed it locally, so paragraph numbers ([0xxx]) are exact. I downloaded datasheets from distributor or university mirrors and converted them with pdftotext, so page numbers are the datasheet's own printed page numbers. Google Patents rate-limited several follow-up lookups. Items marked "(per search snippet)" were not opened in full.

Terms used throughout:
- **Simultaneous**: several strings conduct at the same moment into one node.
- **Sequential**: separate sense operations whose results are added digitally.
- **Series / multi-WL**: several cells in one string. This is not parallel summation.

---

## Q1. The four named Micron patents/applications: bibliographic data, topology, input method, summation, readout, and new versus existing circuitry

### Takeaway
All four filings are Micron patent documents. None reports measured silicon, and every one depends on circuitry or operating modes that public Micron NAND documentation does not describe.
- **Only US20260031152A1 matches the user's topology.** Several pillars (strings) of one WL block share a bitline, each has its own SGD input, one tier is held at a fixed gate bias, and their currents add on the bitline at the same time. Readout uses an ADC or integrator on each bitline.
- **US12437810B2** also uses SGD/select-line inputs with summation on the bitline or digit line. It adds digitizers, shifters, adders, and (for PWM inputs) capacitor integrators.
- **US20250124102A1 sums on the common source, not on a shared bitline.** The strings sit on different bitlines and each is driven with a multiplier-digit voltage. An added ADC on each isolated source does the conversion. The sibling filing US20260031152A1 says source-side summation "requires unique source routes, which are not part of a traditional 3D NAND architecture."
- **US20260120774A1** (Tomoharu Tanaka) adds a new per-sub-block circuit: a local bitline, boost transistors, a sense transistor and read/write transistor chains. Currents from several sub-blocks are summed at the same time on a read source line and read by the page buffer or other circuitry.

### Cited Findings

#### A. US20260031152A1 — "NAND memory array biasing for matrix vector multiplication" (Micron)
- **Bibliographic data:**
  - Inventors: Hernan Castro and Huai-Yuan Tseng. Assignee: Micron Technology Inc.
  - Priority: provisional 63/674,726, filed 2024-07-23. US application 19/245,100, filed 2025-06-20, published 2026-01-29. Status: pending.
  - Family: CN121412503A (CN202511000166.8A, filed 2025-07-21, published 2026-01-27).
  - [Google Patents](https://patents.google.com/patent/US20260031152A1/en)
- **Document type:** patent application. No measured data appears; the text never uses "measured data", "experimental" or "simulation" for results. [Google Patents](https://patents.google.com/patent/US20260031152A1/en)
- **Abstract / claim 1:** the controller programs a cell, measures its output current with "a fixed bias to a gate of the memory cell," and keeps programming until that current "corresponds to a stored weight." Claim 3 adds MVM: output currents are summed while the same fixed bias is applied. Claim 5: "select transistors that couple each memory cell to a common line that accumulates third output currents… wherein an input signal for the multiplication is provided to gates of the select transistors." [Google Patents](https://patents.google.com/patent/US20260031152A1/en)
- **Topology: strings sharing a bitline are decoded by SGD.**
  - [0296]: "The SGD transistors 1808 are used to decode pillars when multiple pillars on a bitline BL share the same wordline WL (often referred to as a 'WL block')."
  - [0297]: "The SGD transistors 1808 are used for inputs… The SGD transistors permit selecting an individual cell (since the wordlines are shorted together)."
  - [0292]: "Typically, the selector 1712 at the bottom (SGS) is simply biased on. The selector 1710 at the top (SGD) is used for providing inputs to the active cells during multiplication."
  - [Google Patents](https://patents.google.com/patent/US20260031152A1/en)
- **Inputs are applied on SGD, digitally or as time-sliced pulses.**
  - [0132]: "An input is applied on a select gate drain (SGD) line 502, 504 (e.g., as a digital time-sliced pulse stream). Select transistors 530, 532 connect each pillar to a bitline 506, 508. Output currents are summed on bitlines 506, 508. Bypass voltages are applied to non-selected cells."
  - [0130] lists alternatives: the input as the gate voltage of another fixed-VT cell, as a select-gate pulse stream, or "applied on a bitline".
  - [0142]: "each bit position of an input feature vector (X0, X1, X2, etc.) is run serially." Multi-bit inputs are therefore bit-serial in time.
  - [Google Patents](https://patents.google.com/patent/US20260031152A1/en)
- **Wordline bias: one fixed-Vg active tier, Vpass on the rest.**
  - [0282]: "for any given pillar, a controller selects only one active tier… The other cells receive a pass voltage."
  - [0305]–[0306]: the example fixed gate bias is 1 V. "cell thresholds can be set to provide output currents from 0 nA to 245 nA in 35 nA steps," and the 111 state gives about 250 nA.
  - [0308]: "VPASS is 5 V," compared with 8 V for standard NAND in FIG. 15 ([0276]).
  - [Google Patents](https://patents.google.com/patent/US20260031152A1/en)
- **Summation is simultaneous on the bitline.** [0283]: "multiple pillars are connected to a bitline and are conducting at the same time… multiple cells of the different multiple pillars are conducting at the same time… the average current is higher as compared to standard NAND memory devices." [0280]: "Output currents from multiple pillars 1602 are accumulated on a single bitline 1604." [Google Patents](https://patents.google.com/patent/US20260031152A1/en)
- **Readout uses an ADC or integrator per bitline.**
  - [0147]: "each bitline is connected to an analog-to-digital converter (ADC). Each ADC will be charged and used during the multiplication operation."
  - [0301]: "there is an integrating circuit (e.g., analog-to-digital conversion circuit) located at and electrically connected to the bottom of each digit line."
  - [0127] (FIG. 4): "integrators 410, 412 accumulate currents… and provide the accumulated currents as inputs to ADC 420, 422."
  - [0126]: "Digital-to-analog converters (DAC) 402, 404 convert digital inputs into magnitudes for analog voltages used to drive electrodes 408 (e.g., … a select gate drain line)."
  - [0148]–[0150] (FIG. 7): "sensing circuitry (e.g., using a sensing amplifier or other sensing circuit)… may include an ADC"; a current source 718 pre-charges the bitline, and a sense node 712 has capacitance 714.
  - [0069]: the memory die "further includes voltage drivers 115 and current digitizers 117."
  - [0070]: sensing circuitry 150 "includes ADCs or other digitizers" and is configured through "read registers 160".
  - [Google Patents](https://patents.google.com/patent/US20260031152A1/en)
- **The patent contrasts this with standard NAND sensing.**
  - [0276]: standard NAND uses "a constant sense current level… (e.g., 20 nA)," and the gate voltage is swept to find VT.
  - [0309]: "The larger current variation… of standard NAND generally prevents MVM operation with sufficient accuracy for AI applications," while MVM uses about 150 nA at a fixed gate bias.
  - [0272]: "Various embodiments… change the bias of the cells to a higher current regime of operation as compared to standard NAND memory operation."
  - [Google Patents](https://patents.google.com/patent/US20260031152A1/en)
- **Physical or process changes the patent proposes:**
  - Bitline segments shorted by shunts in the top metal, and multi-pillar cells ([0180]–[0186]).
  - Copper instead of tungsten bitlines ([0284]–[0285]).
  - Array folding into sub-arrays with a shunting network, and "number of tiers reduced to 64 or less" ([0314]).
  - Vstring of about 300 mV ([0315]).
  - IR-drop-aware placement, refresh "once per week", and constant-temperature operation ([0316]).
  - The system is a bonded multi-die device: sensor die 103, logic die 109 and memory die 105 ([0067]).
  - [0131]: "summing currents at the source… requires unique source routes, which are not part of a traditional 3D NAND architecture."
  - [Google Patents](https://patents.google.com/patent/US20260031152A1/en)
- **Related Castro filing:** US20260038539A1, "Shunting networks for access lines in a memory array" (Hernan Castro, Micron; priority 2024-07-30, published 2026-02-05). Abstract: "bitlines are coupled to a shunting network that reduces the effective resistance… when performing matrix vector multiplication." [Google Patents](https://patents.google.com/patent/US20260038539A1/en)

#### B. US12437810B2 — "Memory device performing multiplication using logical states of memory cells" (Micron)
- **Bibliographic data:**
  - Inventor: Hernan Castro. Assignee: Micron.
  - Priority: provisional 63/385,242, filed 2022-11-29. Application 18/494,652, filed 2023-10-25. Pre-grant publication US20240177772A1, 2024-05-30. Granted 2025-10-07. Adjusted expiration 2044-01-10.
  - Family: CN118116420A (filed 2023-11-28, published 2024-05-31). Continuation US20250391472A1 (US19/306,291, filed 2025-08-21, published 2025-12-25).
  - [Google Patents](https://patents.google.com/patent/US12437810B2/en)
- **Abstract:** "Output currents from the memory cells are accumulated in a common bitline. A sum of the output currents is digitized… The digital results from several bitlines can be shifted based on bit significance and added." Claim 1 needs a first line and a second line, one per bit significance, plus "a logic circuit configured to provide an accumulation result," with voltages applied "so that the memory cells do not threshold." [Google Patents](https://patents.google.com/patent/US12437810B2/en)
- **3D NAND embodiment (FIG. 10):**
  - [0181]: cells in "horizontal tiers… (e.g., 64 tiers)… Each string 1002, 1004 is connected to a common source (SRC) line… and to a digit line 1016, 1018."
  - [0185]: one tier is selected and the others are held at bypass, so "overall resistance in each string is dominated by the one selected memory cell."
  - [0187]: "The voltages are applied to gates of select transistors 1012, 1014 using select lines (SL). Output currents from the memory cells are then summed on digit lines 1016, 1018, and a digital result provided."
  - [Google Patents](https://patents.google.com/patent/US12437810B2/en)
- **Inputs, both time-sliced options:**
  - Bit-serial over clock cycles ([0046]–[0047], [0093]–[0098]: "applied one bit at a time through the same predetermined number of clock cycles", then a digital left shift and add).
  - PWM ([0111]): "The width of the voltage pulse (e.g., a length of time between 5 to 100 nanoseconds) is proportional to the respective multi-bit input. The input voltage pulse is a constant voltage (e.g., 2-4 V across each memory cell)."
  - [Google Patents](https://patents.google.com/patent/US12437810B2/en)
- **Readout is added circuitry.**
  - [0115]: "a memory chip… includes circuits of voltage drivers, digitizers, shifters, and adders to perform the operations of multiplication and accumulation."
  - [0110]: "each of lines 241, 242, 243 is coupled to a respective capacitor to accumulate the charge."
  - [0113]: "each integrator includes a capacitor to collect charge from a common line."
  - [0137]: "the digitizer is configured in an analog-to-digital converter."
  - The text never mentions a "page buffer" or "sense amplifier".
  - [Google Patents](https://patents.google.com/patent/US12437810B2/en)
- **Cell operating regime:** [0109] says NAND cells may be operated "in a sub-threshold mode." [0030] notes that NAND current "typically increases rapidly near its threshold voltage region." [Google Patents](https://patents.google.com/patent/US12437810B2/en)
- **Related Castro family** (all Micron, application numbers 18/423,1xx, filed 2024-01-25):
  - US20240303037A1, "Memory device having bonded integrated circuit dies used for multiplication"
  - US20240303038A1, "…signed multiplication using sets of four memory cells"
  - US20240303039A1, "…different bias levels based on bit significance"
  - US20240303296A1, "…sets of two memory cells"
  - US20240304252A1, "…signed multiplication using logical states"
  - US20240304253A1, "…summation of outputs of signed multiplications"
  - US20240304254A1, "…signed multi-bit to multi-bit multiplications"
  - US20240304255A1, "…different thresholds based on bit significance"
  - These are listed as Micron Technology in the references table of [US12437810B2](https://patents.google.com/patent/US12437810B2/en).

#### C. US20250124102A1 — "Vector element multiplication in NAND memory" (Micron)
- **Bibliographic data:**
  - Inventors: Dmitri Yudanov, Lawrence Celso Miranda, Sheyang Ning and Aliasger Zaidy.
  - Priority: provisional 63/590,860, filed 2023-10-17. Application 18/757,909, filed 2024-06-28, published 2025-04-17. Status: pending.
  - Family: CN119851703A (CN202411026966.2A, filed 2024-07-30, published 2025-04-18).
  - [Google Patents](https://patents.google.com/patent/US20250124102A1/en)
- **Topology (FIG. 7, [0095]–[0098]):**
  - Three sub-blocks (drain select lines 215_0, 215_1, 215_2) share data lines 204_0–204_6 and one common source 216.
  - The multiplicand is stored in cells on access line 202_3 under drain select line 215_0. Each string (on a different bitline) holds one digit.
  - [0133]: SGD 215_0 is activated and SGDs 215_1 and 215_2 are deactivated, so only one sub-block conducts.
  - [Google Patents](https://patents.google.com/patent/US20250124102A1/en)
- **Inputs go on the bitlines (data lines), not on SGD.**
  - [0088]: "Respective digits of the multiplier might be applied to the respective data lines of the set of memory cells sequentially… the collective current flow… from its respective data lines to the common source might be indicative of the value of the multiplicand multiplied by one digit of the multiplier."
  - [0089]: alternatively, binary-weighted bitline voltages (V1, V2 = 2×, V4 = 4×) encode digit significance through Vds.
  - [Google Patents](https://patents.google.com/patent/US20250124102A1/en)
- **Summation happens at the common source, with one ADC per source.**
  - [0096]: "The common source 216 might be connected to an input 732 of an analog-to-digital converter (ADC) 730… configured to receive an analog signal (e.g., an electric current) from the common source 216… if D=8…"
  - [0049]: a new "Multiply-Accumulate (MAC) register 136… in communication with one or more analog-to-digital converters."
  - The page buffer appears only in the generic background ([0048]).
  - [Google Patents](https://patents.google.com/patent/US20250124102A1/en)
- **Parallelism needs separate sources per block.**
  - [0159]: concurrency works where elements are stored in different blocks "selectively connected to a second common source isolated from the first common source."
  - [0162] (FIG. 17): "The common source 216_1 might be connected to an input 732_1 of an analog-to-digital converter (ADC) 730_1… additional blocks… could have their respective sources 216 connected to respective ADCs 730."
  - [Google Patents](https://patents.google.com/patent/US20250124102A1/en)
- **Multiplier digits are processed one after another.** FIGS. 15–16 loop over digits d=1..D, and the partial products are summed digitally in registers ([0149]–[0150], [0138]). [0158] skips zero digits. [Google Patents](https://patents.google.com/patent/US20250124102A1/en)
- **Series versus parallel within the multiplicand:**
  - [0087]: a digit's subset "might contain one or more memory cells… of a single string… or of multiple strings," programmed "in an analog fashion, e.g., different memory cells exhibiting different levels of resistance (e.g., R, R/2, R/4, R/8…)."
  - FIG. 6B and [0094]: thermometric encoding with 1, 2 or 4 strings per digit.
  - [0139]: "Desired voltage levels… might be determined experimentally, empirically or through simulation." No data is given.
  - [Google Patents](https://patents.google.com/patent/US20250124102A1/en)

#### D. US20260120774A1 — "Analog multiply and accumulate architecture for compute-in-memory machine learning" (Micron)
- **Bibliographic data:**
  - Inventor: Tomoharu Tanaka. Assignee: Micron.
  - Priority: provisional 63/713,681, filed 2024-10-30. Application 19/353,955, filed 2025-10-09, published 2026-04-30. Status: pending.
  - Family: PCT/US2025/053187, published as WO2026096681A1 on 2026-05-07.
  - [Google Patents](https://patents.google.com/patent/US20260120774A1/en); [WO2026096681A1](https://patents.google.com/patent/WO2026096681A1/en)
- **Topology (FIG. 4):**
  - [0064]–[0065]: each sub-block has NAND strings 406_0–406_3 joined by drain select transistors (SGD0–SGD3) to a local bitline 405. Source select transistors connect to a common source 416.
  - [0066]: "a set of boost transistors 414, each coupled between the local bitline 405 and a respective string."
  - [0067]: "a sense transistor 407 (or STr) having a gate terminal coupled with the local bitline 405 and a series of transistors 420 that includes a data read path between a read source line 415 and the sense transistor 407 and between the sense transistor 407 and a global bitline 401… the global bitline 401 is also coupled with a page buffer 452… current over the read source line 415 can be read out by the page buffer 452 or other read circuitry that is outside of the page buffer 452."
  - [0068]–[0069]: enhancement and depletion transistors gated by read-enable (RE) and write-enable (WE) control lines. These are internal array control lines, not the ONFI RE# pin.
  - [Google Patents](https://patents.google.com/patent/US20260120774A1/en)
- **The patent presents this circuit as its contribution.**
  - [0020]: "Aspects of the present disclosure address the above and other deficiencies through integrating boost transistors and control transistors within the string-based CIM architecture… 'the multiply' is performed in a given sub-block and the accumulate (of the MAC) is performed across sub-blocks."
  - The same paragraph says "In some memory devices, the sense transistor transfers data from the memory cell to a page buffer through a global bitline using an all bitline (ABL) scheme."
  - [Google Patents](https://patents.google.com/patent/US20260120774A1/en)
- **Inputs and biasing:**
  - [0070]: one wordline (WL1) and the boost wordline get a "particular voltage", and the local bitline is pulled to it "in a source-follower manner". Unselected WLs and select lines get at least twice that voltage. The common source gets a medium voltage. Cell VT lies in "0-1V or 1-1.2V".
  - [0071]: the input is the global bitline voltage, "0-1V or 0-1.2V". Equation (1) gives I_read ∝ (Vboost + VWL1 − Vt − Vtn)·VBL − ½VBL².
  - [0083]–[0085] give alternatives. The RE line level can carry the input (3-bit example: 1.000–1.875 V in 0.125 V steps). Or the RE pulse time tREH can carry it ("0 μsec… 7 μsec") with charge integrated, per Equation (10).
  - [Google Patents](https://patents.google.com/patent/US20260120774A1/en)
- **Summation is concurrent across sub-blocks on the read source line.** [0072]: "the control logic causes the I_read current of Equation (1) to be concurrently combined with currents read out from other sub-blocks of the memory array to obtain the total current." [Google Patents](https://patents.google.com/patent/US20260120774A1/en)
- **Compensation uses extra sequential reads.** [0076]–[0082]: a background current I_str is read with the local bitline floating, and a reference-cell current I_ref is read from a neighbouring higher-VT cell on the same WL, "performing another read operation." The compensated I_diff = I_read − I_str (or − I_ref). [0074] adds WL-voltage temperature compensation, read-level calibration and corrective read. [Google Patents](https://patents.google.com/patent/US20260120774A1/en)
- **No ADC is named.** The term "analog-to-digital" does not occur in the text. Readout is attributed to the page buffer or "other read circuitry." No measured or simulated results are given; the analysis is Equations (1)–(10). [Google Patents](https://patents.google.com/patent/US20260120774A1/en)
- **Inventor background:** Tomoharu Tanaka was lead author of Micron's ISSCC 2016 paper 7.7, "A 768Gb 3b/cell 3D-floating-gate NAND flash memory" (pp. 142–144). [dblp](https://dblp.org/pid/176/6247); [EE Times Japan](https://eetimes.itmedia.co.jp/ee/spv/1602/09/news079.html)

### Inferences

#### Capability mapping: user's five capabilities against the four Micron filings
This is my synthesis from the paragraphs cited above.

| Capability | What the patents describe | Already in commercial Micron NAND? |
|---|---|---|
| (1) Wordline bias control | One active tier at a fixed Vg (about 1 V) with Vpass about 5 V (152 [0305]–[0308]). In 774, the WL and boost-WL voltages are set to a "particular voltage". | WL drivers and read-level shifting exist physically. No public datasheet I found lets the user set an arbitrary analog WL voltage. The closest public control is opaque read-retry mode selection (feature 89h) on certain MLC parts (see Q3). |
| (2) Independent string / sub-block selection on a shared bitline | Multiple SGD-decoded pillars per bitline is the standard 3D NAND structure (152 [0296]; 774 [0061]). | The structure exists. The operating mode the patents need does not appear in any public document I found: several SGDs asserted at once with per-SGD data-dependent patterns or pulse trains. Public commands address one page (one sub-block/WL) per plane per read. |
| (3) Parallel summation of 2..N strings on one sense node | Simultaneous in 152 ([0283]) and in 774 (read source line, [0072]). In 102 the summation is on the source, across different bitlines, and needs isolated per-block sources and an ADC per source ([0159], [0162]). | — |
| (4) Access to the summed analog signal | Every filing adds a digitizer path: ADC or integrator per bitline (152, 810), ADC on the source (102), or a page-buffer read of the read-source-line current (774). | Public documents expose only latched digital page data and status. |
| (5) Numerical conversion with existing sense amps, references or timing | Only 152 FIG. 7 ("sensing amplifier or other sensing circuit… may include an ADC") and 774 ("page buffer") gesture at the existing sense path. None says a stock page buffer delivers 6–10-bit current values. | Separately, Micron's trim patents show sensing time exists as an internal read-trim parameter (Q2). |

#### Other inferences
- The design changes in US20260031152A1 point to purpose-built or modified silicon rather than stock product: ≤64 tiers, copper bitlines, shunts, sub-array folding, Vstring of about 300 mV, Vpass of 5 V, a bonded sensor/logic/memory stack, weekly refresh, and "current measurement" programming. Its own contrast with "standard NAND" sensing at about 20 nA ([0309]) suggests that stock sense conditions are not what Micron has in mind.
- US20250124102A1 sums currents from strings on different bitlines at the source. That is a different topology from the user's "strings sharing one bitline." It also needs block-isolated sources, which 152 [0131] says are not traditional.
- In US20260120774A1, "RE" is an internal read-enable gate line in a new transistor chain, not the ONFI RE# pin. The user should not read it as an interface-level timing knob.

### Gaps
- I did not inspect the figure images (only the text). Figure-only details, such as exact transistor counts per tile, were not verified.
- No continuation or foreign (KR/JP/EP) family members were visible for these four documents. Google listed only the CN and WO members above. EP or KR equivalents may be published later.
- None of the four documents cites a Micron silicon demonstration.

---

## Q2. Other Micron patents: multi-block / multi-sub-block simultaneous read, adjustable sense time or reference, trim registers, analog/neuromorphic and CIM

### Takeaway
- **Micron has a large CIM family, mostly Hernan Castro's 2023–2026 MVM filings plus an "analog inference" image-sensor family.** All rely on added digitizers or drivers.
- **Micron sense-time patents treat sensing time as an internal read-trim value** chosen by the memory sub-system or local media controller. None exposes it through a documented raw-NAND command.
- **I found no Micron patent describing a stock multi-sub-block simultaneous read for MAC.**
- The closest third-party NAND CIM filings that reuse sense amplifiers are SanDisk's, not Micron's.

### Cited Findings
- **Castro MVM family (Micron).** Besides those in Q1:
  - US20240331762A1, "Memory device using wordline calibration for matrix vector multiplication" (CN118737230A)
  - US20250013716A1, "…memory cell pre-compensation for matrix vector multiplication"
  - US20250014648A1, "…multi-pillar memory cells for matrix vector multiplication" (CN119252308A)
  - US20260038582A1, "Programming memory cells based on context in a memory array"
  - US20250029659A1, "Three-dimensional NOR memory device for multiply-accumulate operations"
  - US20260033252A1, "Three-dimensional ferroelectric tunnel junction device for multiply-accumulate operations"
  - These appear as similar documents on the Castro pages. Their assignee was not individually confirmed in this session (Google rate-limited), but the titles track the 152 and 810 texts. [Google Patents US20260031152A1](https://patents.google.com/patent/US20260031152A1/en); [Google Patents US12437810B2](https://patents.google.com/patent/US12437810B2/en)
- **Micron "analog inference capability" family** (image-sensor / CIM system level), listed in the references of US12437810B2, two of them as Micron:
  - US20240089632A1, "Image Sensor with Analog Inference Capability" (Micron; granted as US12538048B2)
  - US12100455B2, "Weight calibration check…"
  - US20240086696A1, "Redundant Computations…"
  - US20240087306A1, "Balance Accuracy and Power Consumption…"
  - US20240249130A1, "Artificial Neural Network Computation…"
  - US20240267646A1, "Image Enhancement…"
  - US20260120731A1, "Model Inversion in Integrated Circuit Devices having Analog Inference Capability" (2026-04-30)
  - Also US20240020048A1, "Network-Ready Storage Products with Artificial Intelligence Accelerators" (Micron)
  - [Google Patents US12437810B2](https://patents.google.com/patent/US12437810B2/en)
- **Sensing time as a trim: US12014049B2, "Adaptive sensing time for memory operations" (Micron).**
  - Inventors: Yu-Chung Lien, Zhenming Zhou, Murong Lang and Ching-Huang Lu. Filed 2022-08-15, granted 2024-06-18.
  - [0036]: "adaptive sensing time component 113 loads a sensing time to be used as a part of the read trim settings during the read operation… the read operation sensing time is an amount of time threshold voltages are applied during a read operation."
  - [0046]: the sensing time is chosen from "a look-up table indicating different sensing times for different combinations of wordlines and program erase cycles."
  - The component sits in the memory sub-system (controller or local media controller; [0030]).
  - [Google Patents](https://patents.google.com/patent/US12014049B2/en)
- **Other trim patents:**
  - US12211556B2, "Independent sensing times" (Micron; Yu-Chung Lien, Zhenming Zhou), tied to program-verify sensing (per search snippet). [Google Patents](https://patents.google.com/patent/US12211556)
  - US7580287 / US10109351, "Program and read trim setting": trim settings "include a sensing time or sense amplifier delay, a bitline precharge voltage, and a sensing or sense reference voltage," with a single trim set "applied to all blocks and all word lines" in the baseline. This is per search snippet: the snippet attributes it to Micron, and the full text was blocked (HTTP 403). [Justia](https://patents.justia.com/patent/7580287)
- **Leads only, assignee not verified:** sub-block and multi-sense-module patents listed as similar to the Tanaka application:
  - US11894069B2, "Unselected sub-block source line and bit line pre-charging to reduce read disturb"
  - US20250273275A1, "Execution of a memory access operation involving multiple memory cells… using multiple sense modules"
  - US12406731B2 / US20250356922A1, "Dynamic latches above a three-dimensional non-volatile memory array"
  - US20250364061A1, "Multi-step analog program convergence…"
  - [Google Patents US20260120774A1](https://patents.google.com/patent/US20260120774A1/en)
- **Intel CIM patents cited by Micron's Tanaka filing** (Intel-assigned; NAND relevance not verified):
  - US11061646B2, "Compute in memory circuits with multi-Vdd arrays and/or analog multipliers" (priority 2018-09-28, granted 2021-07-13)
  - US12602200B2, "Analog multiply-accumulate unit for multibit in-memory cell computing" (priority 2021-09-24, granted 2026-04-14)
  - [Google Patents US20260120774A1](https://patents.google.com/patent/US20260120774A1/en)
- **SanDisk filings found while searching** (outside Micron/Intel scope, but they show sense-amp reuse):
  - US12706153B2, "Calculation unit splitting for NAND in-memory compute" (Jaco Hofmann, Dejan Vucinic; priority 2024-05-03; granted 2026-08-11).
  - US12566814B2, "Vgs ladder for NAND in memory compute" (Hofmann, Richard New, Vucinic; granted 2026-03-03).
  - Both say "each bit line connects to one memory hole (NAND string) in each sub-block," apply the input vector on word lines, and use pre-charged sense capacitors discharged by bitline current.
  - [Google Patents US12706153B2](https://patents.google.com/patent/US12706153B2/en); [Google Patents US12566814B2](https://patents.google.com/patent/US12566814B2/en)
- **Inventor-name searches:** Yudanov, Castro and Tanaka plus "silicon measured" returned no Micron CIM papers, only financial news. [search: no relevant result]

### Inferences
- Micron's patents show that sense timing and references are internal trims, as one would expect. Making them a user-adjustable numerical-conversion knob on a raw die would need access that public documents do not give (see Q3).
- The Castro family's progression points to a dedicated MVM product concept rather than repurposed stock NAND: signed four-cell sets, bit-significance bias levels, bonded dies, wordline calibration, pre-compensation, multi-pillar cells and shunting.

### Gaps
- A Micron patent claiming concurrent multi-sub-block reads on a shared bitline for normal (non-CIM) use was not found. Assignee checks on several leads were blocked by Google rate limits.
- USPTO full-text (ppubs) assignee searches for Micron with "sub-block" and "concurrently" and "sense" were not run.

---

## Q3. Micron public raw-NAND documentation: Set/Get Features feature addresses, read-retry, array operation modes, and technical notes

### Takeaway
- **Micron's public raw-NAND documents expose only interface and housekeeping features.** These are timing mode, output drive strength, R/B# pull-down, array operation mode (OTP/ECC) and, on certain MLC parts, opaque read-retry mode numbers. SPI NAND adds block-lock, configuration, status and die-select registers.
- **No public document I found exposes** WL voltage values, sense time, reference current, multi-sub-block selection, or any analog or current readout.
- **Current Micron datasheets require a free micron.com registration.** Distributor-hosted copies carry a "Micron Confidential and Proprietary" running header. I flag this rather than resolving it (see Gaps).

### Cited Findings
- **Access to datasheets:** a Digi-Key forum moderator post (2025-10-02) says Micron datasheets must be accessed "directly from Micron's website" and "They will require that you register with them to access the data." [Digi-Key forum](https://forum.digikey.com/t/datasheets-for-micron-technology-parts/60947) The micron.com part page for MT29F4G08ABAEAWP-IT:E showed no part-specific documents without sign-in ("Specifications: No results found"; the documents list loads dynamically). [Micron part page](https://www.micron.com/products/storage/nand-flash/slc-nand/part-catalog/part-detail/mt29f4g08abaeawp-it-e)
- **MT29F4G08ABAEA:** I could not obtain a datasheet. Farnell's "datasheet" link 3916635 is a 2-page printout of the Micron product page (part MT29F4G08ABAEAWP-IT:E, 4Gb, x8, −40 to +85 °C, status "Production"). [Farnell 3916635](https://www.farnell.com/datasheets/3916635.pdf)
- **MT29F1G08ABADA / ABBDA (Micron "m68a_1gb_nand.pdf", Rev. R 1/18, 95 pp., mirrored by a distributor)** [ChipDip mirror](https://static.chipdip.ru/lib/032/DOC032032022.pdf); an earlier copy is at [LCSC/elcodis mirror](https://atta.szlcsc.com/upload/public/pdf/source/20151007/1457707427865.pdf):
  - **p. 41 (Feature Operations):** "The SET FEATURES (EFh) and GET FEATURES (EEh) commands are used to modify the target's default power-on behavior… one-byte feature address… subfeature parameters (P1–P4)." Features are volatile and "remains set, even if a RESET (FFh) command is issued."
  - **p. 41, Table 9 (Feature Address Definitions):** 00h Reserved; **01h Timing mode**; 02h–7Fh Reserved; **80h Programmable output drive strength**; **81h Programmable RB# pull-down strength**; 82h–FFh Reserved; **90h Array operation mode**.
  - **p. 41, ECC sequences:** "EFh(cmd)-90h(addr)-08h(data)-00h(data)-00h(data)-00h(data)-wait(tFEAT)" enables internal ECC; the same sequence with 00h in P1 disables it.
  - **p. 42, Table 10 (Feature Address 90h – Array Operation Mode), P1 bit patterns:** Normal = I/O0 0; OTP operation = I/O0 1; OTP protection = I/O1 1 and I/O0 1; Disable ECC = I/O3–I/O0 0000; Enable ECC = I/O3 1 (08h). P2–P4 are reserved. "These bits are reset to 00h on power cycle."
  - **Table of contents:** Table 11, Feature Address 01h Timing Mode (p. 44); Table 12, 80h I/O Drive Strength (p. 45); Table 13, 81h R/B# Pull-Down Strength (p. 45); SET FEATURES (EFh) p. 42; GET FEATURES (EEh) p. 43.
  - No sensing, reference or WL-voltage feature appears in Table 9.
- **MT29F1G01ABAFD 1Gb SPI NAND (Micron "m78a_1gb_3v_nand_spi.pdf", Rev. G 11/16, hosted by Farnell)** [Farnell 3151163](https://www.farnell.com/datasheets/3151163.pdf):
  - **p. 36:** GET FEATURES is 0Fh and SET FEATURES is 1Fh, with a 1-byte feature address. "Features such as OTP protect, block locking, SPI NOR like protocol configuration, and ECC correction can be managed."
  - **p. 37, Table 5 (Feature Address Settings):**
    - **A0h Block lock:** BRWD, BP3–BP0, TB, WP#/HOLD# Disable
    - **B0h Configuration:** CFG2, CFG1, LOT_EN, ECC_EN, CFG0
    - **C0h Status (read-only):** CRBSY, ECCS2–0, P_Fail, E_Fail, WEL, OIP
    - **D0h Die select:** DS0, "only available in 4Gb or greater stacked die devices"
- **Read-retry, Micron MLC (public Linux kernel sources):**
  - Brian Norris's 2014 linux-mtd patch says "Micron provides READ RETRY support via the ONFI vendor-specific parameter block" (which gives the number of modes). Modes are selected with SET_FEATURES at **feature address 89h** (mode 1, 2, …), and "mode 0" returns to the default.
  - Datasheet check in that patch: MT29F32G08CBADA (MLC, needs retry; tested, 8 modes) and MT29F64G08CBABA (MLC, needs retry) versus MT29F32G08CBABA (MLC), MT29F16G08ABABA (SLC) and MT29F1G08AACWP (SLC), which do not.
  - The patch does not describe what each mode does physically.
  - [linux-mtd, 2014-01-13](https://lists.infradead.org/pipermail/linux-mtd/2014-January/051525.html)
- **Linux `nand_micron.c`:**
  - Read-retry uses `ONFI_FEATURE_ADDR_READ_RETRY` (0x89).
  - On-die ECC uses `ONFI_FEATURE_ON_DIE_ECC` (0x90) with the enable bit `BIT(3)`.
  - Micron status bit 3 means a block was "corrected by on-die ECC and should be rewritten."
  - The vendor ONFI fields `read_retry_options`, `dq_imped` and `rb_pulldown_strength` are declared.
  - [Linux nand_micron.c via codebrowser.dev](https://codebrowser.dev/linux/linux/drivers/mtd/nand/raw/nand_micron.c.html)
- **Older SLC datasheets have no Set/Get Features.** Searching the text for EFh, EEh and "SET/GET FEATURES" in MT29F4G08AAA/MT29F8G08BAA/MT29F16G08FAA (2007) and MT29F2G08AABWP/MT29F4G08BABWP/MT29F8G08FABWP (2006) found only READ ID (90h). [radel.ru mirror](https://radel.ru/upload/iblock/369/bczxfcjrpxhit98nucgxe08ttq9vcw44.pdf); [MSOE course mirror](https://faculty-web.msoe.edu/johnsontimoj/EE4980/files4980/Nand_Spec.pdf)
- **Technical notes:** TN-29-19, "NAND Flash 101: An Introduction to NAND Flash and How to Design It In to Your Next Product" (Rev. A 11/06), is mirrored on a university course site. [opencourses.uoc.gr](https://opencourses.uoc.gr/mod/resource/view.php?id=7206) Old micron.com document URLs return HTTP 404 after the site migration:
  - `.../technical-note/nand-flash/tn2919_nand_flash_101.pdf`
  - `.../data-sheet/nand-flash/60-series/m60a_4gb_8gb_16gb_ecc_nand.pdf`
  - [micron.com legacy path, 404](https://www.micron.com/-/media/client/global/documents/products/technical-note/nand-flash/tn2919_nand_flash_101.pdf)

### Inferences
- The only public lever that touches sensing is the read-retry mode index (89h) on certain MLC parts. It selects vendor-defined, undocumented read-level offsets. It does not give an arbitrary WL voltage, a sense time or a reference current, and it does not change the one-sub-block-per-read addressing.
- From the public documents alone, capabilities (2)–(5) cannot be exercised through documented commands on these Micron raw parts. Capability (1) is reachable only coarsely, through read-retry on some MLC parts.
- Any claim that a Micron die "supports" CIM through test modes would need non-public documentation. That is out of scope under the constraints.

### Gaps
- **Confidentiality header.** All modern Micron datasheet copies I retrieved carry the running header "Micron Confidential and Proprietary". This includes the copy hosted by Farnell, an authorized distributor, the m68a Rev. R mirror and a 2012 aggregator copy. The header appears to be Micron's standard datasheet template on documents handed out through distribution, but I could not confirm the header-free official status on micron.com without registering.
  - A copy of the MT29F2G08ABAGA automotive datasheet hosted on a TI E2E forum post (user-uploaded) carries the same header. I excluded it entirely and did not use its contents.
  - The report writer should present the feature tables above with this caveat.
- I did not obtain the official MT29F4G08ABAEA, MT29F2G08ABAEA or MT29F2G01ABAGD datasheets. Micron registration is apparently required.
- Micron read-retry datasheet tables listing per-mode values for MLC/TLC parts were not found in openly hosted copies. Only the kernel-level description of 89h was available.
- Other TN-29-xx notes (ONFI, error management, read-retry) were not located in openly accessible form.

---

## Q4. Micron publications on NAND sensing circuits, and any published Micron CIM measurements on real silicon

### Takeaway
- **Micron's 3D NAND sensing publications are ISSCC product papers.** Examples: the 2016 768Gb 3b/cell floating-gate NAND (lead author T. Tanaka) and the 2022 1-Tb 4b/cell 176-tier NAND with CMOS-under-the-array (lead author T. Pekny). Joint Intel/Micron work moved sense amps and decoders under the array.
- **I found no Micron-published CIM measurement on NAND silicon.**

### Cited Findings
- **ISSCC 2016 paper 7.7:** Tomoharu Tanaka, Mark Helm, Tommaso Vali et al., "A 768Gb 3b/cell 3D-floating-gate NAND flash memory," ISSCC 2016, pp. 142–144. EE Times Japan reports a read throughput of about 800 MB/s. [dblp](https://dblp.org/pid/176/6247); [EE Times Japan](https://eetimes.itmedia.co.jp/ee/spv/1602/09/news079.html)
- **Intel/Micron 32L 3D FG-NAND:** "CMOS decoders and sense-amps are sitting under the 3D FG-NAND memory array for high memory density (2.28 Gb/mm2)… As Micron mentioned at ISSCC 2016, placement of the wordline drivers under the array allows for the wordline lengths to be short." [Semiconductor Digest](https://sst.semiconductor-digest.com/?p=72191)
- **ISSCC 2022:** T. Pekny, L. Vu, J. Tsai, … R. Ghodsi (25 authors, Micron), "A 1-Tb Density 4b/Cell 3D-NAND Flash on 176-Tier Technology with 4-Independent Planes for Read using CMOS-Under-the-Array." Author list per dblp via search. [dblp](https://dblp.org/pid/271/9726)
- **Patent background on standard sensing** (Micron's own description in US20260031152A1): standard NAND reads at a "constant sense current level… (e.g., 20 nA)" while sweeping the gate voltage. VT ranges from about −1 V to 5 V, and "VPASS is 8 V" ([0276]). [Google Patents](https://patents.google.com/patent/US20260031152A1/en)
- **No Micron CIM silicon measurement found.** Searches on Micron CIM, NAND, measured results and inventor names returned only financial and product news. [search: no relevant result]

### Inferences
- The numbers in the Micron CIM patents (0–245 nA in 35 nA steps at Vg = 1 V; 25/50/100 nA bit-significance currents in 152 [0161]) are presented as examples, not as reported measurements. They should not be treated as silicon data.

### Gaps
- I could not read the full ISSCC papers (IEEE Xplore paywall). Their sense-amp details (bitline precharge level, sense time, current-sensing scheme) are not captured here.
- VLSI Symposium and IEDM Micron papers on sensing were not searched.

---

## Q5. Intel / Solidigm: NAND CIM research, public NAND datasheets, and patents on multi-block sensing for MAC

### Takeaway
- **Intel's NAND group published 3D NAND product papers**, such as the ISSCC 2021 1Tb 4b/cell 144-tier floating-gate paper.
- **I found no Intel or Solidigm publication or patent on NAND-based CIM** or on multi-block sensing for MAC.
- Intel's CIM patents in this search are generic "compute in memory" circuits (likely SRAM; not verified).
- The one Intel/Solidigm sub-block patent found concerns programming, not sensing.
- No public JS29F datasheet with a Set/Get Features table was found.

### Cited Findings
- **ISSCC 2021:** Ali Khakifirooz et al. (Intel), "A 1Tb 4b/Cell 144-Tier Floating-Gate 3D-NAND Flash Memory," ISSCC 2021, pp. 424–426. AnandTech lists 144 layers, 1 Tb, a 74.0 mm² die, 13.8 Gb/mm² and 1.2 Gb/s I/O. PC Watch notes that 2021 NAND talks generally moved to four planes and CMOS-under-array. [dblp](https://dblp.org/pid/287/2509); [AnandTech](https://www.anandtech.com/show/16491); [PC Watch](https://pc.watch.impress.co.jp/docs/column/semicon/1315644.html)
- **US12334152B2, "Simultaneous programming of multiple sub-blocks in NAND memory structures":** assignee SK hynix NAND Product Solutions (originally Intel NDTM), per search snippet. It covers programming, not reading or MAC. [Google Patents](https://patents.google.com/patent/US12334152); [USPTO Gazette](https://patentsgazette.uspto.gov/week24/OG/html/1535-3/US12334152-20250617.html)
- **Intel generic CIM patents:** US11061646B2 and US12602200B2. Their NAND relevance is unverified (see Q2). [Google Patents US20260120774A1](https://patents.google.com/patent/US20260120774A1/en)
- **Intel NAND datasheets:** device-programmer listings for JS29F parts (e.g., JS29F04G08BANB3, JS29F08G08CANB1, JS29F32G08AAMDB) exist. No JS29F datasheet with a feature-address table was found openly hosted. [Elnec device list](https://www.elnec.com/en/device/Intel/JS29F08G08CANB1%20%5BTSOP48%5D/)
- **Searches with no relevant result:** a Solidigm or Intel NSG NAND CIM paper; Intel patents combining NAND, select-gate inputs and bitline current summation (results were Macronix and SanDisk filings and Intel structural NAND patents). [search: no relevant result]

### Inferences
- Within Intel and Solidigm, the public record I found gives no sign of a commercial or research NAND CIM capability. Any Intel/Solidigm raw-NAND sensing controls would sit in non-public documentation.

### Gaps
- No Intel-assigned patent search was run on USPTO ppubs with inventor names such as Pranav Kalavade, Shantanu Rajwade or Krishna Parat. The web searches did not surface any.
- Intel Labs NAND compute work (if any) was not found. 3D XPoint/Optane is not NAND and was excluded.

---

## Q6. Micron research programs, evaluation kits, or sample programs offering legitimate raw-NAND test access

### Takeaway
- **Micron runs university partnerships** (a European University Program, a NUS industrial postgraduate program, the Micron Foundation, and Micron Research Labs announced in 2026). **None of the material found mentions raw-NAND test-mode or sense-level access for researchers.**
- The legitimate routes visible publicly are: buying standard parts through distribution, registering on micron.com for datasheets, and university or collaborative research agreements.

### Cited Findings
- **Micron University Program (Europe):** funds PhD scholarships and contributes instrumentation and materials to student research. [Electronic Specifier](https://www.electronicspecifier.com/?p=169809)
- **Micron Academy (Italy, University of Naples):** the training programme includes a project on a simplified managed NAND prototype. [Micron Academy](https://www.micron-academy.unina.it/en/academy/academy-program.html?rCH=2)
- **NUS–EDB Industrial Postgraduate Program with Micron:** a 2026 posting for a research engineer / PhD on next-generation semiconductor technologies. [NUS posting](https://cde.nus.edu.sg/ece/wp-content/uploads/sites/3/2026/09/IPP-Micron-NUS-1.pdf)
- **Micron Research Labs (2026):** a Boise research hub with university partnerships and satellite labs, exploring memory beyond current DRAM and NAND. [Futurum](https://futurumgroup.com/insights/micron-research-labs-can-1-billion-a-year-out-research-samsung-and-sk-hynix/)
- **Datasheet access:** registration on micron.com is required. [Digi-Key forum](https://forum.digikey.com/t/datasheets-for-micron-technology-parts/60947)

### Inferences
- Access to Micron-internal test modes (sense-time or reference trims, multi-SGD selection) would plausibly require a formal research collaboration under NDA. The publicly documented interface does not provide it.

### Gaps
- I found no public Micron NAND evaluation kit exposing analog sensing, and no "sample program" page for raw NAND access.
- Micron's support portal contents behind login were not examined, deliberately.
