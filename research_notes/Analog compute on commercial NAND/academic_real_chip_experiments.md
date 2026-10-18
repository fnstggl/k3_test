# Academic experiments that compute on real commercial NAND flash chips, and the platforms they used

Scope note: this file covers published academic and industrial-academic experiments that compute (Boolean or analog) on real NAND silicon, and how each experiment reached the die. All facts carry inline citations. Exact quotes are marked with quotation marks and section references. Primary PDFs were downloaded and searched for: Flash-Cosmos (arXiv 2209.05566), MCFlash (arXiv 2605.05119), ParaBit (NSF PAR copy), Cai et al. DATE 2013, Cai et al. Proc. IEEE (arXiv 1706.08642), 3D-aCortex (arXiv 1908.02472), and three SNU/SK hynix V-NAND papers (full text via Europe PMC). The rest of the material comes from abstracts or search listings, as marked.

---

## Q1. Flash-Cosmos (Park et al., MICRO 2022): which chips, which platform, how MWS was triggered, vendor cooperation, and what was released

### Takeaway
Flash-Cosmos measured 160 unnamed 48-layer 3D TLC chips on an in-house FPGA tester. Multi-wordline and multi-block sensing came from the chips' own **proprietary, undisclosed test-mode commands**, not ordinary ONFI commands. The paper does not name the vendor, does not disclose the commands, and no code, tester design or bitstream was found to have been released. The "MWS command" shown in the paper is the authors' own proposed command format. It is not an existing command.

### Cited Findings
- **Paper and authors.** "Flash-Cosmos: In-Flash Bulk Bitwise Operations Using Inherent Computation Capability of NAND Flash Memory." Authors: Jisung Park (ETH Zürich and POSTECH), Roknoddin Azizi, Geraldo F. Oliveira, Mohammad Sadrosadati, Rakesh Nadig, David Novo (LIRMM), Juan Gómez-Luna, Myungsuk Kim (Kyungpook National University) and Onur Mutlu. MICRO 2022, DOI 10.1109/MICRO56248.2022.00069. arXiv v1 posted 12 Sep 2022. — [POSTECH-hosted MICRO PDF](https://www.caos.postech.ac.kr/_files/ugd/ceab3b_bf84a4fec67d45e086332f53e8babe9e.pdf); [arXiv 2209.05566](https://arxiv.org/abs/2209.05566)
- **Chips tested.** §5.1: "We characterize 160 48-layer 3D TLC NAND flash chips, where a NAND string consists of 48 flash cells and the page size is 16 KiB. Under regular SLC-mode programming, the chips have a read latency tR=22.5 µs and a program latency tPROG=200 µs." The chips came from "five different wafers". The authors selected "120 blocks (not sub-blocks) from each of the 160 chips at random locations", 3,686,400 wordlines in total. — [arXiv 2209.05566, §5.1](https://arxiv.org/pdf/2209.05566)
- **Vendor not named.** A full-text search of the arXiv PDF for Samsung, SK hynix, Micron, Kioxia/Toshiba, WD and YMTC finds no attribution of the tested chips. Vendors appear only in reference-list datasheets and in the Samsung 980 Pro SSD power numbers used for system modelling (§7). — [arXiv 2209.05566](https://arxiv.org/pdf/2209.05566)
- **Test platform (exact quote, §5.1 "Infrastructure").** "We use an FPGA-based testing platform that contains a custom NAND flash controller and a temperature controller. The flash controller supports all the commands implemented in our NAND flash chips, including not only basic read/program/erase commands but also various test-mode commands necessary to dynamically change operating parameters (e.g., the ISPP step voltage and other timing parameters) and simultaneously activate multiple WLs. The temperature controller maintains a NAND flash chip within ±1 °C of the target temperature." Tests ran at 85 °C, with Arrhenius-accelerated retention. — [arXiv 2209.05566, §5.1](https://arxiv.org/pdf/2209.05566)
- **The platform is not described further.** The paper gives no FPGA part, board, schematic or bitstream. Its reliability methodology follows JEDEC: "JEDEC recommends testing more than 39 flash chips from three different wafers." — [arXiv 2209.05566, §5.1](https://arxiv.org/pdf/2209.05566)
- **How MWS was triggered: proprietary test mode.** §6.2: "Although we demonstrate that our NAND flash chips already support all necessary features to perform the ESP and MWS operations in their test-mode command set, efficient design of Flash-Cosmos commands is important due to two reasons. First, NAND flash vendors consider their test-mode command set design to be proprietary and do not reveal any details in publicly-accessible documentation." — [arXiv 2209.05566, §6.2](https://arxiv.org/pdf/2209.05566)
- **The "MWS" command in Fig. 15 is the authors' design, not an existing command.** "Figure 15 shows three new NAND flash commands that we design for Flash-Cosmos: (a) MWS, (b) ESP, and (c) XOR." The proposed format extends the regular read with (i) an "ISCM" slot holding flags for inverse read, sensing-latch init, cache-latch init and S→C transfer, (ii) a page bitmap (PBM) in place of the page index, and (iii) "up to four address slots for inter-block MWS by sending the additional block address and PBM after a CONT (continue) slot." The illustrative bit strings in Fig. 15/16 are example encodings of this proposal. — [arXiv 2209.05566, §6.2, Fig. 15–16](https://arxiv.org/pdf/2209.05566)
- **Precondition stated by the authors.** §5.2 conclusion: "real commodity NAND flash chips can reliably support both intra-block and inter-block MWS operations, so computer architects can build a system that leverages Flash-Cosmos, as long as they have access to the command interfaces used for our characterization." — [arXiv 2209.05566, §5.2](https://arxiv.org/pdf/2209.05566)
- **Feasibility argument (a claim about chips in general).** §4.1: "existing chips already use/support both inter- and intra-block MWS for other purposes. For example, after erasing a block, a NAND flash chip needs to check if all the cells in the block are completely erased (called erase verify) by simultaneously applying VREF to all the cells [92] … Also, manufacturers commonly design a chip to support the activation of multiple WLs (i.e., intra-block MWS) and multiple blocks (i.e., inter-block MWS), to perform multi-page reads/writes and multi-block erases that are critical for rapid testing of the chip [92]." Reference [92] is the textbook Micheloni, Crippa and Marelli, *Inside NAND Flash Memories* (2010). — [arXiv 2209.05566, §4.1 and refs](https://arxiv.org/pdf/2209.05566)
- **Changes the authors say are needed.** Intro: "integrating Flash-Cosmos into existing NAND flash chips requires changes only to the command latching circuitry and the firmware of the microcontroller in the flash chip". Also: "no changes to its cell array and sensing circuitry." — [arXiv 2209.05566, §1](https://arxiv.org/pdf/2209.05566)
- **Program tuning (ESP).** ESP uses ISPP tuning. The paper says commodity chips "can tune ISPP parameters … using the SET FEATURE command [64, 116]" (ONFI 4.2 is ref. 116). The experiments themselves used the test-mode commands described in §5.1. — [arXiv 2209.05566, §4.2](https://arxiv.org/pdf/2209.05566)
- **Other on-die features used.** Inverse read is used for NOT/NAND/NOR. "many modern NAND flash chips (including the 160 chips used in our real-device characterization …) support a bitwise XOR operation between the data in different latches". — [arXiv 2209.05566, §6.1](https://arxiv.org/pdf/2209.05566)
- **Results.** "bitwise AND/OR/NAND/NOR of up to 48 operands via a single sensing operation (25 µs)", and "In our validation of computation results across more than 10^11 flash cells, we observe zero bit errors." System-level gains were obtained by simulation ("Our simulation-based real workload evaluations…"). — [arXiv 2209.05566, §1 and §11](https://arxiv.org/pdf/2209.05566)
- **No NAND vendor cooperation is acknowledged.** The acknowledgments list "Google, Huawei, Intel, Microsoft, VMware, the Semiconductor Research Corporation and the ETH Future Computing Laboratory", plus a Korean NRF grant to Jisung Park. Co-corresponding authors are Jisung Park, Myungsuk Kim and Onur Mutlu. Footnote 9 says "manufacturers can significantly reduce the faulty-cell fraction by specially designing chips for Flash-Cosmos". — [arXiv 2209.05566, Ack. and fn. 9](https://arxiv.org/pdf/2209.05566)
- **Academic limits on reliability claims.** Footnote 11: "Given the limitations in academia, it is challenging to experimentally guarantee the UBER requirements, which requires around 1,000× samples and 1,000× longer testing time than our experiments". — [arXiv 2209.05566, fn. 11](https://arxiv.org/pdf/2209.05566)
- **No code repository found.** A search of the CMU-SAFARI GitHub organization for "flash" showed only "CertiFlash", a Rocq/Coq FTL verification framework. No Flash-Cosmos repository or NAND tester repository appeared. — [GitHub CMU-SAFARI search "flash"](https://github.com/orgs/CMU-SAFARI/repositories?q=flash). A web search for a Flash-Cosmos GitHub repository found only paper mirrors. — [HAL mirror](https://hal-lirmm.ccsd.cnrs.fr/lirmm-03777151); [ETH Research Collection entry](https://www.research-collection.ethz.ch/entities/publication/7dac73e7-9209-48dc-8226-d90c53efaeec)

### Inferences
- The Flash-Cosmos capabilities (multi-WL VREF application, multi-block activation, ISPP and timing changes) were reached through vendor test-mode commands on an in-house FPGA controller. Because the vendor is anonymous and the paper says test-mode commands are proprietary, the chips are commercial and unmodified, but the access path is not public. Treat it as "commercial die + non-public command interface".
- Myungsuk Kim (Kyungpook, formerly SNU) is a co-corresponding author. The same "160 × 48-layer 3D TLC chips + FPGA + temperature controller" setup appears in SNU/Jihong Kim group papers such as Park et al., "Reducing SSD Read Latency by Optimizing Read-Retry", ASPLOS 2021 (Flash-Cosmos ref. [64]). The platform likely comes from that Korean group's industry-linked infrastructure. This is an inference; the paper does not say so.
- The Fig. 15 command bytes and fields are a proposal. They should not be described as existing commands.

### Gaps
- No "extended version" of Flash-Cosmos was found. arXiv 2209.05566 v1 is the MICRO version. I found no ETH thesis by Jisung Park that adds methodology. The ETH Research Collection entry is the paper itself.
- The chip vendor, part number, FPGA model, board and any released artifact are not disclosed anywhere I could find.
- GitHub org-wide search via the API was blocked in this environment, so only the GitHub web search for "flash" was checked.

---

## Q2. Is Flash-Cosmos inter-block MWS a parallel current summation on a bitline, and is there evidence of analog behavior or magnitude readout?

### Takeaway
Physically, yes. Inter-block MWS connects strings from several blocks to one precharged bitline/sense-out node at the same time, so their discharge currents add (a wired-OR). But Flash-Cosmos only ever read this through the normal latch as a **binary threshold** ("any string conducts"). Its "analog" evidence is limited to latency (tMWS) versus number of blocks (1–32), power versus number of blocks, and zero-error validation. Nothing measures or resolves the magnitude of the summed current.

### Cited Findings
- **Sensing mechanism the paper describes (§2.1).** "a NAND flash chip charges all target BLs and their sense-out (SO) capacitors (CSO) to the precharge voltage VPRE … applies the read-reference voltage VREF to the target WL while applying a much larger pass voltage VPASS to the other WLs … If the target cell's VTH level is lower than VREF, the charge in CSO quickly flows through the NAND string, which is sensed as a '1'. If VTH > VREF, the capacitance of CSO hardly changes…" — [arXiv 2209.05566, §2.1](https://arxiv.org/pdf/2209.05566)
- **Topology.** The paper says simultaneous sensing gives "(i) bitwise AND of all the sensed wordlines if they are in the same NAND string or (ii) bitwise OR of all the wordlines if they are in different NAND strings", because "thousands of NAND strings are connected to the same bitline (similar to digital NOR logic)". For inter-block MWS, "the chip would read a BL j as '1', only when at least one of Blkl and Blkn has a NAND string in which every cell stores '1'". — [arXiv 2209.05566, §1, §4.1](https://arxiv.org/pdf/2209.05566)
- **Number of blocks tested.** "we perform inter-block MWS operations on all WLs in the target blocks while changing the number of activated (target) blocks from 1 to 32." In these experiments every WL of each activated block was at VREF, so each block contributes a string-AND. — [arXiv 2209.05566, §5.2](https://arxiv.org/pdf/2209.05566)
- **Latency versus blocks, with the authors' explanation.** "when simultaneously reading WLs in 32 different blocks, tMWS is 36.3% higher than tR. This is because activating multiple blocks significantly increases the number of WLs to precharge at the same time. The increased WL-precharge time is mostly hidden by the BL-precharge time until we activate eight blocks, but it becomes larger than the BL-precharge time as the number of activated blocks further increases". Intra-block: all 48 WLs gives +3.3% over tR; 8 or fewer WLs gives <1%. — [arXiv 2209.05566, §5.2, Fig. 12–13](https://arxiv.org/pdf/2209.05566)
- **Power limit.** "Increasing the number of activated blocks from one to two increases the average power consumption by about 34%… Until we activate four blocks, the power consumption of inter-block MWS remains lower than that of an erase operation." Recommendation: "If we limit the maximum number of simultaneously-activated blocks for inter-block MWS to 4, we can support any MWS operation with a fixed latency (tMWS) only 3.3% higher than tR." — [arXiv 2209.05566, §5.2, Fig. 14](https://arxiv.org/pdf/2209.05566)
- **String-resistance stress pattern.** To stress string resistance, the authors programmed blocks so that "(i) the number of cells that store bit value '1' … must be less than two; (ii) if a NAND string has a '1' cell, the cell must be in one of the MWS operations' target wordlines". They also note that without randomization a string "can have low resistance … which may increase the precharge latency and the evaluation latency". This shows they were aware that string conductance affects sense timing. — [arXiv 2209.05566, §4.1, §5.2](https://arxiv.org/pdf/2209.05566)
- **The authors reject analog current summation for current chips.** Prior multiply-accumulate proposals inside NAND "rely on analog current sensing, which requires significant changes to regular flash chips". They cite ADC cost: "each ADC accounts for 58% of the chip power and 31% of the chip area even when each ADC is shared across 128 output columns". — [arXiv 2209.05566, §4.1](https://arxiv.org/pdf/2209.05566)
- **MCFlash (2026) contradicts the "commonly supported" framing, at least for user-mode access.** It says MWS "incurs higher power and energy consumption, particularly in inter-block configurations where multiple blocks must be activated simultaneously, an uncommon practice in current NAND flash chip designs. Furthermore, realizing MWS requires a more complex wordline decoder circuitry, since existing NAND chips typically support only single-wordline sensing." — [MCFlash, arXiv 2605.05119, §1](https://arxiv.org/pdf/2605.05119); contrasted with [Flash-Cosmos §4.1](https://arxiv.org/pdf/2209.05566)

### Inferences
- Against the user's five capabilities, Flash-Cosmos shows:
  - (1) Wordline bias: demonstrated, but only selection of VREF versus VPASS per wordline, plus test-mode changes to ISPP and timing parameters.
  - (2) Independent block selection on a shared bitline: demonstrated for 1–32 blocks, via test mode.
  - (3) Simultaneous summation: physically present for 2–32 strings per bitline (one per block).
  - (4) Access to the analog summed signal: not shown. Output is the page buffer bit only.
  - (5) Numerical conversion: not shown.
- Sensing time is a possible route to a count. The platform could change "other timing parameters" through test mode. The discharge of CSO should speed up with the number (and conductance) of conducting strings. Sweeping evaluation time or read level across repeated MWS reads could therefore turn the summed current into a count or level. **This is an extrapolation. The paper does not attempt or report it.** Each such step would also need the undisclosed test-mode interface.
- Zero errors at 32 blocks under worst-case patterns imply something about margins. The sense threshold separated "no conducting string, many leaking strings" from "at least one conducting string". The usable dynamic range for a multi-level count, including leakage from 31 off strings, bitline capacitance and string-to-string current variation, was not characterized.
- The power data (+34% from 1 to 2 blocks, erase-level power at about 4 blocks) suggest that simultaneous activation of many blocks (e.g., 64–128) may hit power and WL-precharge limits on commercial dies. This is extrapolated from the 1–32 block data.

### Gaps
- No data on bitline current or discharge rate versus number of conducting strings, no sense-margin-versus-count curves, no multi-level readout.
- Sub-block (multiple string-select lines within a block) parallelism on one bitline was not studied. The experiments used "blocks (not sub-blocks)".

---

## Q3. Related in-flash computing work (ParaBit, Ares-Flash, CrossBit, MCFlash), the Cai/Haratsch/Mutlu FPGA characterization platform, and open-source tooling

### Takeaway
Only two works in this line computed on real commercial NAND:
- **Flash-Cosmos:** test-mode, unnamed vendor, FPGA.
- **MCFlash (Colorado State, 2026):** fully user-mode ONFI commands (read offset via SET FEATURE, soft-bit read, read retry) on 50 COTS 3D NAND chips, using an FTDI-USB board. Bitwise only, single wordline.

ParaBit used real Intel MLC chips only for an error-count check; its performance results are simulated. Ares-Flash (MICRO 2024) and CrossBit (MICRO 2025) propose page-buffer or added circuitry; their abstracts give no real-chip evidence. The SAFARI/Cai platform reads per-cell Vth by sweeping read-retry reference levels, a numerical-conversion method that works on single cells.

### Cited Findings
**ParaBit (MICRO 2021)**
- Authors: Congming Gao, Xin Xin, Youyou Lu, Youtao Zhang, Jun Yang, Jiwu Shu (Tsinghua and Univ. of Pittsburgh). "We evaluated the performance of ParaBit in MLC SSD using a modified SSD simulator … The reliability of ParaBit also is verified in real flash chips." — [ParaBit, NSF PAR](https://par.nsf.gov/servlets/purl/10316348)
- Real-chip check: "customer grade Intel MLC flash chips with cache read are evaluated [23]. When the number of P/E cycles is 5K, the average and maximal numbers of bit errors per WL after seventh (for XOR operation) sensings are 0.945 and 5 while the page size is 8KB". The paper does not describe the test platform in the passages examined. — [ParaBit §5.7](https://par.nsf.gov/servlets/purl/10316348)
- Mechanism: ParaBit sequences latch control and sensing steps across serially read operands. It performs two-operand operations by sequential sensing, not simultaneous multi-string activation. — [ParaBit](https://par.nsf.gov/servlets/purl/10316348); characterized in [Flash-Cosmos §3](https://arxiv.org/pdf/2209.05566). MCFlash adds that ParaBit "necessitate[s] changes to the timing control logic, which means a privileged command sequence must be developed for its execution." — [MCFlash §1](https://arxiv.org/pdf/2605.05119)

**Ares-Flash (MICRO 2024)**
- Authors: Jian Chen, Congming Gao, Youyou Lu, Yuhao Zhang, Jiwu Shu. Abstract: "Ares leverages the designed page buffer to perform basic mechanisms: full-adder logic and bit-shift … we construct computational operations using dedicated control sequences in the page buffer". It reports 8.58×/9.89× performance gains over OSP/ISP for accumulation. — [Semantic Scholar record (abstract)](https://api.semanticscholar.org/graph/v1/paper/DOI:10.1109/MICRO61859.2024.00109?fields=title,abstract,authors.name,year,venue); [IEEE Xplore](https://ieeexplore.ieee.org/document/10764476/)
- The abstract does not mention real-chip experiments. "designed page buffer" implies page-buffer hardware changes. — same source

**CrossBit (MICRO 2025)**
- Authors: Hyunjin Kim, Seunghwan Song, Su-hyeon Choi, Jeongin Choe, Sanghyeok Han, Jisung Park, Jinho Lee, Jae-Joon Kim. Abstract: "a new IFP architecture that enables both intra-bitline and inter-bitline operations with minimal additional circuitry integrated into commodity NAND flash memory"; it adds in-flash ECC for MLC IFP. — [Semantic Scholar record (abstract)](https://api.semanticscholar.org/graph/v1/paper/DOI:10.1145/3725843.3756055?fields=title,abstract,authors.name,year,venue); [DOI](https://doi.org/10.1145/3725843.3756055)
- Search listings report that CrossBit claims a 3.6× (MLC) and 1.9× (SLC) speedup over Ares-Flash. — [ACM DL listing via search](https://dl.acm.org/doi/10.1145/3725843.3756055)

**MCFlash (Colorado State; arXiv May 2026)**
- Authors: Habib Ur Rahman, Tharini Suresh, Sudeep Pasricha, Biswajit Ray. Abstract: "MCFlash relies solely on standard user-mode instructions, combining Multi-Level Cell (MLC) data encodings with dynamically tuned read reference voltages to execute in-place bitwise operations." — [arXiv 2605.05119](https://arxiv.org/abs/2605.05119). A Springer journal version is also listed. — [Springer s11227-026-08557-8](https://link.springer.com/article/10.1007/s11227-026-08557-8)
- Chips: "COTS 3D NAND flash memory chips from a major vendors across three different generations, incorporating two technology types: 176-layer charge-trap and 64-layer floating-gate … A total of 50 individual chips were rigorously tested, comprising 10 chips from each product category and generation." The vendor is not named. — [MCFlash §5.1](https://arxiv.org/pdf/2605.05119)
- Platform (exact): "a custom-built interface board was employed … integrates a Ball-Grid-Array (BGA) socket suitable for NAND flash packages and utilizes an FT2232H mini-module (Future Technology Devices International, FTDI), offering a USB connection to the host computer. Collectively, the FTDI module and host computer simulate the operations of a standard NAND flash controller." — [MCFlash §5.1, Fig. 5](https://arxiv.org/pdf/2605.05119)
- Commands (exact): "Low-level firmware complemented by user-level wrapper functions were implemented to conform with the Open NAND Flash Interface (ONFI) standard command sets. These software routines enabled … page read, page program, and block erase, and supported advanced commands such as copyback, read reference shifting, soft bit reading, and read retry via SET FEATURE user-mode commands. Critically, the experimental configuration facilitated direct access to the raw NAND flash array memory bits, deliberately bypassing any ECC and data randomization mechanisms." Timing and energy were measured with a "Siglent SDS2354X oscilloscope and Nordic Power Profiler Kit II". — [MCFlash §5.1](https://arxiv.org/pdf/2605.05119)
- Results and limits: two-operand AND, OR, XNOR and NOT at zero RBER on fresh blocks; "over one billion bitwise operations on 10 chips per part-number"; at least 1000 pages of 16 KB per operation. Other operations "may show higher RBER (greater than 5%) due to limited read-offset ranges in the chips under test". "practical implementation constraints such as limited DAC bits" restrict offsets; "permissible offset voltage ranges vary significantly across vendors". — [MCFlash §4–5](https://arxiv.org/pdf/2605.05119)
- MCFlash on analog multiply-accumulate in NAND: "These approaches typically rely on analog current accumulation, which requires substantial modifications to the NAND array structure and depends on expensive analog-to-digital converters." — [MCFlash §1](https://arxiv.org/pdf/2605.05119)

**Cai/Haratsch/Mai/Mutlu FPGA platform and read-retry Vth measurement**
- DATE 2013 (Cai, Haratsch, Mutlu, Mai, "Threshold Voltage Distribution in MLC NAND Flash Memory"): "Read retry requires the implementation of two additional controller commands: Set REF and Get REF. Set REF sets the read reference voltage to a new value… We implemented these two commands in our FPGA-based flash testing framework [14]." [14] is "Y. Cai et al., 'FPGA-based Solid-State Drive prototyping platform', FCCM 2011." Chips: 2Y-nm (20–24 nm) MLC. Limitation: "Due to limitations in the flash chips we test, we cannot set the read reference voltage to negative values and thus the threshold voltage of cells in erased state cannot be characterized." — [Cai et al. DATE 2013 PDF](https://people.inf.ethz.ch/omutlu/pub/flash-memory-voltage-characterization_date13.pdf)
- Proc. IEEE 2017 survey (arXiv 1706.08642): "We use an FPGA-based testing platform [13] to characterize state-of-the-art TLC NAND flash chips. We use the read-retry operation present in NAND flash devices to accurately read the cell threshold voltage … As absolute threshold voltage values are proprietary information to flash vendors, we present our results using normalized voltages, where the nominal maximum value of Vth is equal to 512 in our normalized scale". [13] is Cai, Haratsch, McCartney, Mai, "FPGA-Based Solid-State Drive Prototyping Platform" (FCCM 2011). — [arXiv 1706.08642](https://arxiv.org/abs/1706.08642)
- SAFARI open-sourced SoftMC, a DRAM testing infrastructure (HPCA 2017; cited in the same survey). I found no equivalent open-source NAND tester from SAFARI. — [arXiv 1706.08642 reference list](https://arxiv.org/pdf/1706.08642); [GitHub CMU-SAFARI "flash" search](https://github.com/orgs/CMU-SAFARI/repositories?q=flash)

**Open-source raw-NAND platforms (adjacent; not compute papers)**
- Cosmos+ OpenSSD: "XC7Z045-3FFG900 Zynq-7000 FPGA", two NAND SO-DIMM slots, "4-way NAND Flash Interface for each slot", initially supporting "Hynix 128Gbit MLC NAND". — [Technion PSL page](https://psl.technion.ac.il/?p=1591). A community firmware fork notes it "requires the Cosmos+ Board with hynix NAND firmware version". — [FlashSQL/Flashalloc-Cosmos](https://github.com/FlashSQL/Flashalloc-Cosmos)

### Inferences
- For user-mode-only access, MCFlash is the closest published template. It uses an ONFI command sequencer (FTDI bit-bang) and SET FEATURE read-offset / read-retry sweeps on unmodified packaged chips. This covers capability (5), multi-level quantization through repeated reads at shifted references, but only for **single cells on single wordlines**. It does not do multi-string summation.
- The Cai read-retry sweep (Set REF / Get REF, up to a normalized 512-step Vth scale on TLC) is the established public method to "digitize" a cell's analog state with commercial sense amps. Applying it to a summed multi-string bitline would require simultaneous multi-block activation, which no user-mode ONFI command provides in the papers reviewed.
- After ETH, Jisung Park's in-flash work (CrossBit, with SNU/POSTECH co-authors) moved toward circuit additions rather than more real-chip test-mode experiments. This rests only on the abstract.

### Gaps
- Full texts of Ares-Flash and CrossBit were not accessible (ACM DL returned 403). Whether either used real chips (e.g., FPGA characterization) is unverified.
- The ParaBit real-chip platform was not identified in the passages read. Its reference [23] is listed as an Intel datasheet.
- No 2023–2026 follow-up by Myungsuk Kim (Kyungpook) on in-flash computing with real chips was found by search.
- I did not obtain the FCCM 2011 platform paper, so FPGA part and board details of the Cai platform are not recorded here. The DATE 2012 PDF URL returned HTML, not the paper.
- No GitHub, GitLab or Zenodo artifact (bitstream, schematic, ONFI sequencer) was found for Flash-Cosmos, ParaBit, Ares-Flash, CrossBit or MCFlash.

---

## Q4. Experiments using commercial NAND (2D or 3D) as synaptic arrays, vector-matrix multipliers or analog compute-in-memory: custom test arrays versus commercial die

### Takeaway
The only measured analog-current work on commercial-process NAND that I found is from **Seoul National University (Jong-Ho Lee) with SK hynix**: >100-layer TLC V-NAND, described as "unmodified commercial". Even there, the die was **not** operated through its own periphery. Measurements used a probe station, a Keysight B1500A and a switching matrix on **SK hynix-supplied measurement wafers with contact pads**. Bitline currents were measured externally, and the multi-string VMM and ADC were evaluated in simulation. Macronix demonstrates search/Hamming computation on its *own* 48L/96L 3D NAND technology, using a dedicated "IMAS chip". The other prominent works are simulation-only (3D-aCortex; Wang/Yu) or custom silicon (UMN embedded NAND in a logic process).

### Cited Findings
**SNU (Jong-Ho Lee) + SK hynix, commercial >100-layer V-NAND (2025–2026)**
- TLCAM, Adv. Sci. 2026: "The devices employed in this study are unmodified commercial TLC V-NAND flash memory provided by SK hynix, consisting of more than 100 WL layers and a total storage capacity of 512 GB … No physical modifications were made to the memory devices or peripheral circuitry, including the cell structure, WL stack, drain/source select devices, or SAs." — [Park et al., "Triple-Level Content-Addressable Vertical NAND Flash Memory," Adv. Sci. 2026, PMC13502362, §4.1](https://pmc.ncbi.nlm.nih.gov/articles/PMC13502362/)
- Same paper, measurement method: "Device characteristics were evaluated using a semiconductor parameter analyzer (Keysight B1500A) integrated with a probe station. The analyzer is linked to a switching matrix (B2201A), which routes the applied voltages to the designated contact pads. This configuration enables array-level measurements with simultaneous multi-WL driving and controlled BL, DSL, SSL, and SL biasing." — [PMC13502362, §4.2](https://pmc.ncbi.nlm.nih.gov/articles/PMC13502362/)
- TLCAM operations:
  - Search runs along the WL direction: "Each DSL plane is processed sequentially, while all BLs within that plane are evaluated in parallel".
  - The parity-split scheme "enables 32 WLs in total (16 odd and 16 even) to be searched in just four read operations".
  - Sensing is described as "the same fundamental principle as conventional V-NAND flash SAs, with the key distinction being an increased number of sampling events".
  - Measured effect: "As the number of simultaneously read WLs increases, the effective resistance of the V-NAND string also increases. This resistance rise reduces the sensing margin".
  - Energy was "estimated from the measured I_BL" and "summed over the active strings".
  - [PMC13502362, §2–4](https://pmc.ncbi.nlm.nih.gov/articles/PMC13502362/)
- PUNN, Adv. Sci. 2026: "Commercial triple-level cell (TLC) V-NAND flash memory chips supplied by SK hynix are used … a vertical stack exceeding 100 WL layers." "All device-level characteristics are obtained using a Keysight B1500A semiconductor parameter analyzer connected to a probe station. A B2201A switching matrix is employed to accurately route the programmed voltage signals to the corresponding contact pads."
  - Funding: "SK hynix Inc., in 2025, which contributed measurement wafers, equipment, and measurement data for the research."
  - The architecture text says: "the summed string currents are accumulated along the BLs, naturally performing vector–matrix multiplication (VMM) operations. The resulting analog current sum is then digitized by an analog-to-digital converter (ADC)". Yet the network results come from "Machine-learning simulations … conducted using the PyTorch framework, incorporating the LTP/LTD characteristics … measured", with "All ADC operations … performed with a 7-bit resolution."
  - Single-cell weight updates used a "1-bit erase scheme" via GIDL.
  - [Park et al., "Model-Inversion-Resistant Physical Unclonable Neural Network Using Vertical NAND Flash Memory," Adv. Sci. 2026, PMC13137843](https://pmc.ncbi.nlm.nih.gov/articles/PMC13137843/)
- DPB, Nano Convergence 2025 (co-authors from SK hynix R&D): "commercial V-NAND flash memory fabricated by SK hynix, featuring over 100 WL layers, was employed for all electrical measurements." Measured I_BL–V_WL was taken at several temperatures. The text says "The currents from V-NAND strings connected to the same BL are summed at the BL, enabling efficient vector-matrix multiplication (VMM) operations. The resulting BL current is subsequently processed through an analog-to-digital converter (ADC)". CIFAR-10/VGG-11 accuracy came from simulation with "4-bit ADCs". Data are available "with permission of SK hynix Inc." — [Park et al., "Dynamic pass bias control for temperature-resilient neural networks using vertical NAND flash memory," Nano Converg. 2025, PMC12484496](https://pmc.ncbi.nlm.nih.gov/articles/PMC12484496/)

**SNU earlier 2D NAND (26 nm)**
- "We measured floating-gate 2D NAND cells fabricated with 26-nm technology. One cell string is composed of 64 cells, including a ground select line transistor, an SSL transistor, and two dummy cells." Weights were written by read-verify-write, with "∼40 pulses … amplitude of V_PGM increases from 11 V with a fixed width of 100 μs". Eight weight levels were characterized. Networks (MNIST/CIFAR-10) were simulated. — [Lee & Lee, "Neuromorphic Computing Using NAND Flash Memory Architecture With Pulse Width Modulation Scheme," Front. Neurosci. 2020](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7530297/)
- A related SNU paper describes the strings as a "2-D NAND flash string fabricated in the industry using 26 nm technology". — [ResearchGate: Operation Scheme of Multi-Layer Neural Networks Using NAND Flash Memory as High-Density Synaptic Devices](https://www.researchgate.net/publication/336574520_Operation_Scheme_of_Multi-Layer_Neural_Networks_Using_NAND_Flash_Memory_as_High-Density_Synaptic_Devices)

**Macronix (vendor's own silicon)**
- IMW 2023, Tseng et al. (Macronix): "in-memory-approximate-search (IMAS) method from single-level cell (SLC) to multi-level cell (MLC) … based on our commercial 48-layer (48L) and 96-layer (96L) 3D-NAND flash technology. The input search word can be compared with 128 K data words in just one read cycle", with Hamming-distance (SLC) or similarity (MLC) computed in the array. "Latest 96L 3D-NAND IMAS chip with CMOS under array (CuA) technology". — [StorageNewsletter summary of IMW 2023 paper](https://storagenewsletter.com/?p=264195)
- IEDM 2020, "In-Memory-Searching Architecture Based on 3D-NAND Technology with Ultra-high Parallelism". Per the abstract, it covers cell composition, operation algorithm, array structures and reliability, with a k-NN demo. — [IEEE Xplore 9372035](https://ieeexplore.ieee.org/document/9372035)
- Lue et al., IEDM 2019, "Optimal Design Methods to Transform 3D NAND Flash into a High-Density, High-Bandwidth and Low-Power Nonvolatile Computing in Memory (nvCIM) Accelerator". Only the title was verified, from the Flash-Cosmos ref. [63]. — [Flash-Cosmos references](https://arxiv.org/pdf/2209.05566)

**Simulation-only "commercial 3D NAND" VMM proposals**
- 3D-aCortex (Bavandpour, Sahay, Mahmoodi, Strukov, UCSB): mixed-signal VMM "based on the existing 3D-NAND flash memory blocks, without any need for their modification … Our detailed simulations have shown that … the 5-bit VMM of 200-element vectors, using the commercially available 64-layer gate-all-around macaroni-type 3D-NAND memory blocks designed in the 55-nm technology node, may provide … 0.14 µm²/byte and energy efficiency of ~10 fJ/Op".
  - The array is unmodified, but the design adds new time-domain VMM peripheral circuits.
  - The cell model is a behavioral compact model that "accurately reproduces the experimental string current characteristics".
  - The paper also states that, because each WL plate is shared by all cells of a layer, the "current-mode" approach used for commercial 2D (NOR) flash cannot be applied directly.
  - [arXiv 1908.02472](https://arxiv.org/abs/1908.02472)
- "Mixed-Signal Vector-by-Matrix Multiplier Circuits Based on 3D-NAND Memories for Neurocomputing" (IEEE): per the search abstract, results come from simulations of a 64-layer, 55 nm design. — [IEEE 9116401](https://ieeexplore.ieee.org/document/9116401/)

**Custom silicon (not commercial NAND)**
- UMN (Chris H. Kim group): "An Embedded NAND Flash-Based Compute-In-Memory …" (JSSC 2021) and "A 3D NAND Flash Ready 8-Bit Convolutional Neural Network Core …" (IEDM 2019). Both are NAND-like eflash in a standard logic process, i.e., custom test chips. — [JSSC21 PDF](https://people.ece.umn.edu/groups/VLSIresearch/papers/2021/JSSC21_NAND.pdf); [IEDM19 PDF](https://people.ece.umn.edu/groups/VLSIresearch/papers/2019/IEDM19_3DNAND.pdf)

**Unsuccessful or negative searches**
- A search for measured VMM on unmodified commercial 3D NAND returned only simulation or modified-array studies. — [search results incl. Springer 2026 memcapacitor paper](https://link.springer.com/article/10.1186/s40580-026-00575-9)
- The "Unified Characterization Platform … Using off-the-shelf NVM Chips" (Suri group, ISCAS 2020) covers MRAM, FeRAM, CBRAM and ReRAM, not NAND. — [arXiv 2006.05696](https://arxiv.org/abs/2006.05696)
- No paper was found reporting hyperdimensional-computing measurements on packaged commercial NAND via ONFI.

### Inferences
- "Commercial V-NAND" in the SNU/SK hynix papers means production-process arrays accessed through manufacturer-supplied wafers and probe pads. All terminals (WL, BL, DSL, SSL, SL) are driven directly by SMUs and the switching matrix, and bitline current is read by an external instrument. This gives capabilities (1)–(4): WL bias, string selection, summation and analog access. But it bypasses the die's own periphery, and the hardware is not obtainable by the public. It does **not** show that a packaged die can do the same through its standard interface.
- In these SNU papers, the ADC (4–7 bit) and the multi-string bitline-sum VMM are architectural or simulation assumptions built on measured single-cell and string I–V data. They are not a measured end-to-end analog MAC through on-die sense amps.
- Macronix's IMAS on "commercial 48L/96L technology" is vendor-internal silicon, apparently with a dedicated IMAS chip design (CuA). It is closer to "special silicon" than to an off-the-shelf die.

### Gaps
- Exact SNU measurement-structure details (how many strings share the probed BL, whether multi-string current sums were measured directly) are in supplementary notes (Note S1–S3), which I did not retrieve.
- Not verified first-hand: Wang/Xu/…/Yu "Three-Dimensional NAND Flash for Vector–Matrix Multiplication" (TVLSI) and Choi et al. (Western Digital) "An In-Flash Binary Neural Network Accelerator with SLC NAND Flash Array" (ISCAS 2020). Titles are confirmed via [Flash-Cosmos refs 57, 62](https://arxiv.org/pdf/2209.05566). Whether they were measured or simulated is not confirmed here.
- No Chinese (PKU, Tsinghua, IME-CAS) or Taiwanese (NTHU, NYCU) paper using **unmodified packaged commercial NAND** for analog VMM was found. Searches surfaced only custom, 3D-AND (Macronix patents), FeFET-NAND or simulation work.

---

## Q5. Per-experiment summary: strings summed, simultaneity, readout path, precision, timing, access type and obtainability

### Takeaway
No published experiment found reads a numerical (6–10 bit) value of summed multi-string current **through a commercial die's own sense amps**.
- **Flash-Cosmos:** simultaneous 2–32-block wired-OR, binary latch output, non-public test mode.
- **MCFlash and Cai:** public user-mode read-offset sweeps, single wordline/cell.
- **SNU/SK hynix:** real analog bitline current, but by external probing of vendor-supplied wafers.

### Cited Findings
| Work | Silicon | Strings/blocks on one sense node | Simultaneous? | Readout | Precision / timing | Access path | Public? |
|---|---|---|---|---|---|---|---|
| Flash-Cosmos (MICRO'22) | 160 × 48-layer 3D TLC, unnamed vendor | Intra-block: up to 48 WLs in one string (AND). Inter-block: 1–32 blocks per BL (OR) | Yes, single sensing | Page buffer / latch bit (binary) | tMWS = 1.033×tR (48 WLs); 1.363×tR (32 blocks); tR = 22.5 µs SLC; "25 µs" single sensing | FPGA custom controller + vendor test-mode commands | Commands proprietary; no artifact |
| MCFlash (arXiv'26) | 50 COTS chips: 176-layer CT, 64-layer FG, "major vendor" | 1 string per BL (single WL page read) | n/a | Page bit after shifted-reference reads | 2-operand ops, zero RBER fresh; offset range limited by "DAC bits" | FTDI FT2232H USB + BGA socket, ONFI user-mode + SET FEATURE | User-mode; code not found |
| ParaBit (MICRO'21) | Intel MLC (reliability check only) | 1 (sequential sensing) | No | Latch bits | 0.945 avg / 5 max bit errors per 8 KB WL at 5K P/E | Not described in passages read | Performance by simulator |
| Cai et al. (DATE'13; Proc. IEEE'17) | 2Y-nm MLC; TLC | 1 cell (per-cell Vth) | n/a | Read-retry sweep (Set REF/Get REF) | Normalized Vth scale 0–512 (TLC) | FPGA SSD prototyping platform (FCCM'11) | Platform not open-sourced (none found) |
| SNU/SK hynix (2025–26) | >100-layer TLC V-NAND, 512 GB, "unmodified" | Architectural BL summation; TLCAM: 32 WLs in 4 reads | Multi-WL driving yes | **External** B1500A current via probe pads; ADC simulated (4–7 bit) | — | Probe station + B2201A switch matrix on SK hynix measurement wafers | Not obtainable; data "with permission of SK hynix" |
| Macronix IMAS (IMW'23) | Macronix 48L/96L 3D NAND tech; 96L IMAS chip (CuA) | 128K data words compared per read cycle | Yes | Hamming distance / similarity | — | Vendor-internal | Vendor silicon |

Sources:
- [Flash-Cosmos](https://arxiv.org/pdf/2209.05566)
- [MCFlash](https://arxiv.org/pdf/2605.05119)
- [ParaBit](https://par.nsf.gov/servlets/purl/10316348)
- [Cai DATE 2013](https://people.inf.ethz.ch/omutlu/pub/flash-memory-voltage-characterization_date13.pdf)
- [Cai et al. arXiv 1706.08642](https://arxiv.org/abs/1706.08642)
- [SNU TLCAM PMC13502362](https://pmc.ncbi.nlm.nih.gov/articles/PMC13502362/)
- [SNU PUNN PMC13137843](https://pmc.ncbi.nlm.nih.gov/articles/PMC13137843/)
- [SNU DPB PMC12484496](https://pmc.ncbi.nlm.nih.gov/articles/PMC12484496/)
- [Macronix IMW 2023 summary](https://storagenewsletter.com/?p=264195)

### Inferences
- Combining public, demonstrated mechanisms (MCFlash-style SET FEATURE read-offset sweeps on an FTDI or FPGA ONFI sequencer) with simultaneous multi-block activation (shown only via Flash-Cosmos test mode) would be needed for a "weights in cells, summed string currents, multi-bit readout" experiment on a packaged commercial die. The second ingredient is the non-public one.
- Even with test-mode multi-block activation, the existing sense amp is a timed-discharge comparator. A 6–10 bit numerical value would need repeated reads with stepped reference voltage and/or evaluation time. That means about 2^b reads for a linear sweep, or b reads with a successive-approximation-style search if levels can be set arbitrarily. At about 25–30 µs per read this costs roughly 0.2–30 ms per value (arithmetic from Flash-Cosmos tR figures). Whether references or timing apply cleanly to a multi-string sum is undemonstrated.

### Gaps
- No experiment reports the linearity, noise or temperature dependence of summed current through a commercial die's own sense path. The SNU DPB paper does show strong temperature dependence of I_BL on external measurement, which would affect any analog sum. — [PMC12484496](https://pmc.ncbi.nlm.nih.gov/articles/PMC12484496/)

---

## Q6. Released code, FPGA bitstreams, schematics or board designs

### Takeaway
I found no public release (GitHub, GitLab or Zenodo) of tester code, bitstreams or boards for any of the real-chip NAND computing papers above. Open, adjacent infrastructure exists: Cosmos+ OpenSSD (a Zynq FPGA NAND controller platform) and its community forks. MCFlash describes an FTDI-based ONFI sequencer architecture well enough to reproduce, but no code link was found.

### Cited Findings
- Flash-Cosmos: the platform is described only in prose (§5.1). No artifact link appears in the arXiv PDF, and a GitHub CMU-SAFARI search for "flash" returns only CertiFlash. — [arXiv 2209.05566](https://arxiv.org/pdf/2209.05566); [GitHub CMU-SAFARI search](https://github.com/orgs/CMU-SAFARI/repositories?q=flash)
- MCFlash: hardware is an FTDI FT2232H mini-module plus BGA socket board, with host software implementing ONFI read, program, erase, copyback, read-reference shifting, soft-bit read and read retry. A full-text search of the arXiv PDF found no code link. — [arXiv 2605.05119 §5.1](https://arxiv.org/pdf/2605.05119)
- SNU/SK hynix: data "available from the corresponding author upon reasonable request and with permission of SK hynix Inc." — [PMC12484496](https://pmc.ncbi.nlm.nih.gov/articles/PMC12484496/)
- Cosmos+ OpenSSD hardware (Zynq-7000 XC7Z045, NAND SO-DIMM modules with Hynix MLC) is publicly documented. Firmware forks exist on GitHub. — [Technion PSL](https://psl.technion.ac.il/?p=1591); [FlashSQL/Flashalloc-Cosmos](https://github.com/FlashSQL/Flashalloc-Cosmos)

### Inferences
- A replication path that needs no vendor NDA is limited to ONFI-documented commands plus vendor-datasheet SET FEATURE read-offset and read-retry registers, as in MCFlash and Cai. These support single-wordline Boolean ops and per-cell Vth quantization, not simultaneous multi-string analog summation.

### Gaps
- GitHub API search was blocked in this environment (HTTP 403), so repositories outside the CMU-SAFARI web search were not found. A manual GitHub, GitLab or Zenodo search for "ONFI", "NAND tester" and "read retry" is still worth doing.
- Whether the Cosmos+ OpenSSD NAND controller exposes vendor read-retry / SET FEATURE paths, and on which NAND parts, was not verified.
