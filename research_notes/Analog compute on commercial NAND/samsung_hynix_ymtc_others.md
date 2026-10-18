# Samsung, SK hynix, YMTC, Macronix, small raw-NAND suppliers, and Korean/Chinese/Taiwanese academia: evidence for analog compute-in-memory (CIM) on commercial NAND

Scope note: this file covers Samsung, SK hynix, YMTC, Macronix, small SLC raw-NAND vendors (Winbond, GigaDevice, ISSI, ESMT, Alliance, etc.), and Korean, Chinese and Taiwanese academic work. Kioxia is excluded. Research date: 2026-10-17. Each source is labelled with one tag: **[MEASURED]**, **[SIM]** (simulation or estimate), **[PATENT]**, **[PRODUCT DOC]** (public datasheet) or **[NEWS/SECONDARY]**.

Terms used throughout:
- **Series (intra-string):** several wordlines (WLs) or cells in one NAND string. Their effect is AND-like or a series sum of resistance or voltage.
- **Parallel (inter-string):** several independently selected strings driving one bitline (BL) or source line (SL) at the same moment. Only this case gives Kirchhoff current summation, which is capability (3).
- **Binary vs numerical:** a sense amplifier with one trip point gives one bit. A numerical readout needs an ADC, several reference levels, or a sweep of sense time or Vread.

---

## Q1. Samsung (V-NAND): CIM/PIM-in-NAND publications and patents, sensing papers, public raw-NAND datasheets

### Takeaway
I found no Samsung-authored paper and no Samsung product feature that performs analog multiply-accumulate (MAC) on NAND. Samsung's public in-memory computing demonstrations are on MRAM (and DRAM PIM). The closest Samsung item is a patent co-filed with Seoul National University (SNU) for a V-NAND spiking network: several strings are turned on at once by input spikes and their combined bitline current is integrated. It is a patent only. Samsung's public legacy 2D SLC datasheets (K9F1G08 family) document only basic commands, and they explicitly prohibit any command not listed. They expose no read-reference, sense-time or multi-block controls.

### Cited Findings
- **[PATENT] EP4216218A1, "Spiking neural network device, nonvolatile memory device, and operation method thereof."** Applicants: Samsung Electronics and Seoul National University R&DB Foundation. Inventors: Seunghwan Song, Byung-Gook Park, Bosung Jeon. Priority dates 2022-01-06 (KR 20220002331) and 2022-05-06. Published 2023-07-26. — [EPO](https://data.epo.org/publication-server/rest/v1.2/patents/EP4216218NWA1/document.html)
  - Weights are programmed into the cells of NAND strings.
  - Each input spike turns on the string-select transistor of its string for a window ΔT.
  - A second spike can turn on a second string in the same window. The text says "the combined cell current of the cell string NS<0> and the cell string NS<3> are sensed by a sensing circuit."
  - WLs are selected one after another (read voltage on the selected WL, pass voltage on the others). Each WL maps to one of k integrate-and-fire sensing circuits through a switch.
  - The output is a spike, not an ADC code. An even/odd-string variant gives excitatory and inhibitory inputs.
  - The array may be V-NAND with cell-on-peripheral (COP).
  - This describes parallel multi-string summation on one BL, but as a patent claim, not a product feature. A US family member titled "Spiking neural network device, nonvolatile memory device, and operation method thereof" (US 12499943) appeared in search results. I did not verify its assignee. — [USPTO PDF](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12499943)
- **[NEWS] Samsung's in-memory computing demonstration was MRAM.** SAIT reported a 64×64 MRAM crossbar that uses resistance summation for analog MAC (2022). It is not NAND. — [eeNews Europe](https://www.eenewseurope.com/en/samsung-shows-mram-can-support-in-memory-computing/); [Business Wire](https://www.businesswire.com/news/home/20220112005887/en/Samsung-Demonstrates-the-Worlds-First-MRAM-Based-In-memory-Computing/)
- **[PATENT] Samsung patents found on Samsung NAND sensing are conventional storage patents, not CIM.**
  - US6735116B2 covers multi-page program, multi-page read and multi-block erase. — [Google Patents](https://patents.google.com/patent/US6735116B2/en)
  - US7016229B2 covers a page buffer design. — [Google Patents](https://patents.google.com/patent/US7016229B2/en)
  - US 9,396,796 covers "nonvolatile memory devices which contain multiple page buffers and control logic therein that support varying read voltage level test operations." This is internal or controller-level test functionality, not a documented raw-NAND command. — [Justia](https://patents.justia.com/patent/9396796)
- **[PRODUCT DOC] Samsung K9F1G08U0A / K9F1G08Q0A 1Gb SLC datasheet (128M×8, rev 0.0–0.3, 2003–2004; public mirror).**
  - Table 1 "Command Sets" on printed p.7 lists only: Read 00h-30h, Read for Copy Back 00h-35h, Read ID 90h, Reset FFh, Page Program 80h-10h, Cache Program 80h-15h, Copy-Back Program 85h-10h, Block Erase 60h-D0h, Random Data Input 85h, Random Data Output 05h-E0h, Read Status 70h.
  - It warns: "Any undefined command inputs are prohibited except for above command set of Table 1."
  - Features listed: 25 µs maximum random read, Unique ID, cache program, copy-back, floating-gate technology.
  - The mirror is a partial excerpt. — [cryptomuseum mirror PDF](https://cryptomuseum.com/covert/bugs/aid/7178/files/K9F1G08Q0A.pdf)
- **[PRODUCT DOC / SECONDARY] K9F1G08U0E (E-die) datasheet.** Alldatasheet lists it at 38 pages. My fetch was refused (HTTP 403), so I did not read its command table.
  - A TI E2E forum user reports that U0D and U0E differ in NOP (4 vs 1). This is a user report, not a Samsung source.
  - A search summary said the K9F1G08U0D command table has no cache-read or two-plane commands. I did not verify this in a datasheet. — [alldatasheet listing](https://pdf1.alldatasheet.com/datasheet-pdf/download/1132295/SAMSUNG/K9F1G08.html); [TI E2E thread](https://e2e.ti.com/support/processors/f/processors-forum/347989/use-nandwrite-command-but-dump-wrong-data-on-k9f1g08u0e-with-jffs2-filesystem)
- **[PRODUCT DOC, context] Samsung's 9th-generation V-NAND with molybdenum WLs** was presented at IEDM 2025 (paper 18-2). It is a process paper and has no CIM content. — [IEDM 2025 program](https://static1.squarespace.com/static/67a3eee4385dfb3390804f02/t/690e4eca5393d146db3b608c/1762545355037/IEDM+2025+Final+Program-v4.pdf)
- **[NEWS, context]** A report says Samsung signed a hybrid-bonding (Xtacking) agreement with YMTC for V10 NAND. — [EE Times China, 2025-02](https://www.eet-china.com/news/202502254769.html)

### Inferences
- Samsung's legacy 2D SLC parts are the best documented Samsung raw-NAND option. Their public command set gives only capability (1) in its fixed default form (one Vread per read) and the ordinary single-block read. No public command exposes (2) simultaneous multi-block or multi-string selection, (4) the analog BL or sense-node signal, or (5) programmable references or sense timing.
- The "undefined commands prohibited" warning means any multi-block sensing on Samsung parts would need undocumented test modes. Those are out of scope (non-public).

### Gaps
- I could not retrieve full public datasheets for K9F1G08U0E, K9F2G08U0C or K9GAG08U0E. The mikrocontroller.net and SparkFun mirror links returned HTML, not PDFs. I could not confirm which of these list cache read (31h/3Fh) or two-plane commands.
- I found no Samsung ISSCC V-NAND paper text describing the page buffer, sensing-node precharge or develop timing. The search returned only Samsung page-buffer patents (for example US12057173, US12211559), whose claims cannot be attributed to any product.
- Korean-language searches ("낸드 플래시 인메모리 컴퓨팅 곱셈누적") found no Samsung NAND-MAC work. They found only a generic MAC in-memory patent (KR20240057754A, not NAND-specific). — [Google Patents](https://patents.google.com/patent/KR20240057754A/ko)
- Google Patents assignee-filtered queries were blocked by a CAPTCHA, so I could not do a systematic Samsung patent sweep. Samsung NAND-CIM patents beyond EP4216218 may exist.

---

## Q2. SK hynix: NAND CIM/PIM research and patents, sensing papers, public raw-NAND datasheets

### Takeaway
SK hynix's public NAND-CIM evidence has three parts:
- **KAIST co-assigned patents** (Seonghwan Cho group). Several of them do series-string or time-sequential accumulation, not parallel multi-string summation.
- **An IEDM 2025 paper on analog CIM in 3D ferroelectric NAND (FeNAND).** This is a research device, not its charge-trap product NAND.
- **Supplying commercial TLC V-NAND wafers and measurement equipment to SNU.** SNU measured single cells with a probe station and parameter analyzer, and simulated the BL summation.

Legacy Hynix 2D SLC datasheets (H27U1G8F2B) are public but very minimal.

### Cited Findings
- **[PATENT] US11526739B2, "Nonvolatile memory device performing a multiplication and accumulation operation."** Assignees: KAIST and SK hynix. Inventors: Jin-O Seo, Hyuk-Jin Lee, Seonghwan Cho. Priority 2019-09-05. Granted 2022-12-13. — [Google Patents](https://patents.google.com/patent/US11526739B2/en)
  - Inputs become pulse widths that drive the BL selection switches.
  - Weights are stored as cell Vth (low Vth = 1).
  - Each cell string has its own multiplication output circuit. Its outputs charge a shared accumulation capacitor (VMAC), with an optional ADC.
  - K-bit weights take 2^K−1 steps at different read voltages.
  - Claim 11 recites NAND.
- **[PATENT] US11397561B2 (same title; KAIST + SK hynix; same inventors; priority 2019-09-05; granted 2022-07-26).** — [Google Patents](https://patents.google.com/patent/US11397561B2/en)
  - A constant current is forced through one NAND string.
  - Each series cell's drain-source voltage (three levels) depends on its input pulse and weight. The bitline voltage is the series sum.
  - A BL-voltage-controlled current source charges a capacitor. A calibration cell corrects the error.
  - This is intra-string (series) summation, not parallel strings.
- **[PATENT] US12444467B2, "Semiconductor memory device performing a multiplication and accumulation operation."** Assignees: KAIST and SK hynix. Inventors: Kyunghyun Kim, Seonghwan Cho. Priority 2022-07-07. Granted 2025-10-14. — [Google Patents](https://patents.google.com/patent/US12444467B2/en)
  - Inputs are programmed into the cells, and weights are applied as WL voltages (read voltage or ground).
  - A current mirror holds the BL current constant. Each conducting read removes a fixed charge from a capacitor, and an ADC reads the result.
  - Signed weights use two strings on separate BLs.
  - Accumulation is sequential over reads, not simultaneous parallel strings.
- **[MEASURED, research device] SK hynix IEDM 2025 paper 5-3, "Co-Optimizing Cell, Non-Cell, and Page Schemes for Energy Efficient Analog Computing in 3D FeNAND."** Authors: Won-Tae Koo et al. (all SK hynix). DOI 10.1109/IEDM50572.2025.11353774. — [Crossref DOI](https://doi.org/10.1109/iedm50572.2025.11353774); [IEDM 2025 program](https://static1.squarespace.com/static/67a3eee4385dfb3390804f02/t/690e4eca5393d146db3b608c/1762545355037/IEDM+2025+Final+Program-v4.pdf)
  - The abstract describes write-algorithm tuning for multi-level states, reduced WL-transition power, and "in-page pipelining and splitting" for analog MAC.
  - It claims up to 16× throughput and up to 4950× energy efficiency "compared to conventional 2D arrays."
  - The device is ferroelectric NAND, not SK hynix's commercial charge-trap 3D NAND.
  - Secondary coverage says SK hynix published a detailed public account on 2026-10-14 and stresses that the results do not yet show reliability or manufacturability. — [remio.ai summary](https://www.remio.ai/post/sk-hynix-3d-fenand-turns-nand-into-an-ai-compute-engine-but-the-hardware-test-co); [ifeng (Chinese)](https://tech.ifeng.com/c/8xFRAQ42zSe)
- **[MEASURED cells; SIM for VMM] SNU (Jong-Ho Lee) with SK hynix: "Model-Inversion-Resistant Physical Unclonable Neural Network Using Vertical NAND Flash Memory."** Advanced Science, 2026 (accepted 2026-02-11). Co-author Yeongheon Yang is from SK hynix R&D. — [PMC full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC13137843/)
  - Devices: "Commercial triple-level cell (TLC) V-NAND flash memory chips supplied by SK hynix" with more than 100 WL layers.
  - Measurement setup: probe station, Keysight B1500A parameter analyzer and B2201A switching matrix routing voltages "to the corresponding contact pads." SK hynix "contributed measurement wafers, equipment, and measurement data."
  - Measured: per-cell Vth/conductance, LTP/LTD and GIDL erase. Effective weight resolution is above 6 bits.
  - BL current summation with a 7-bit ADC is part of the proposed architecture and is simulated (PyTorch). Multi-string summation was not measured.
  - Takeaway: this is special wafer-level access, not the raw ONFI interface.
- **[MEASURED cells?] SNU, "Ising Solver Using Vertical NAND Flash Memory."** Advanced Intelligent Systems, v.8 no.8, 2026-08. Authors: Sung-Ho Park, Yeongheon Yang, …, Jong-Ho Lee. DOI 10.1002/aisy.70439.
  - It claims to use "commercial vertical NAND (V-NAND) flash memory … without structural changes" to implement a Hopfield network for max-cut.
  - I could not read the full text (403), so the access method and whether strings were summed are unknown. — [GIST record](https://scholar.gist.ac.kr/handle/local/34201)
- **[MEASURED cells] SNU, "Vertical NAND Flash Memory-based Bayesian Neural Networks with Intrinsic Gaussian Weight Sampling"** (Park et al.). The search snippet says it uses "commercial TLC V-NAND flash memory chips supplied by SK hynix." I could not read the full text. — [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6137183)
- **[PRODUCT DOC] Hynix H27U1G8F2B series, 1Gb SLC (Rev 1.2, Dec 2009; public on Farnell).** — [Farnell PDF](https://www.farnell.com/datasheets/1605619.pdf)
  - p.4: 1024 blocks × 64 pages; program typically 200 µs; erase typically 2 ms; 100K P/E cycles; "OTP/Unique ID area, Read ID2 extension"; 48-TSOP1 or 63-FBGA packages.
  - p.7: one plane, 1024 blocks, 2K+64-byte page buffer.
  - p.8, Table 4 command set: 00h-30h, 00h-35h, 90h, FFh, 80h-10h, 85h-10h, 60h-D0h, 70h, 85h, 05h-E0h, Cache Read Start 31h, Cache Read Exit 3Fh.
  - There is no Read Parameter Page or Get/Set Features in Table 4.
  - p.18: tR = 25 µs maximum.
  - RS lists the -BC part as out of stock and due to be removed from its range. — [RS listing](https://st1-uk.rs-online.com/web/p/flash-memory/6686168P)
- **[MEASURED, context] SK hynix IEDM 2025 papers 18-1 (321-layer 3D NAND) and 18-3 (isolated charge-trap layer in 176-layer NAND)** are process papers with no CIM content. — [IEDM 2025 program](https://static1.squarespace.com/static/67a3eee4385dfb3390804f02/t/690e4eca5393d146db3b608c/1762545355037/IEDM+2025+Final+Program-v4.pdf)

### Inferences
- The KAIST/SK hynix patents are useful for readout ideas: pulse-width inputs, capacitor integration and constant-current mirrors. Two of the three do not rely on parallel multi-string current summation on a shared BL. They sum in series along one string, or in time across sequential reads. Neither approach is available through any public command on product parts.
- In the SNU/SK hynix work, "commercial V-NAND" means wafers, probe pads and analyzer instruments supplied by the vendor. It does not mean a purchasable packaged die driven over ONFI. Capabilities (2) to (5) were not demonstrated on product silicon through its own periphery.
- The H27U1G8F2B (2009, pre-ONFI command table) offers fewer documented knobs than current ONFI SLC parts.

### Gaps
- I found no SK hynix ISSCC paper text describing its NAND page-buffer sensing (sense-node timing or references).
- I did not search SK hynix's own newsroom article (2026-10-14) directly. The claims rest on the IEDM program abstract and secondary coverage.
- I found no SK hynix Korean-language NAND-PIM publication beyond the patents and the FeNAND paper.
- I found no paper from KAIST (Seonghwan Cho) that implements the patents in silicon. His lab page lists 2024 JSSC papers, none on NAND CIM. — [KAIST profile](https://ee.kaist.ac.kr/en/professor/12287/)

---

## Q3. YMTC (Xtacking): architecture, and any YMTC/Chinese CIM work using Xtacking or YMTC dies

### Takeaway
Xtacking puts the CMOS periphery on a separate wafer bonded to the array wafer. That is attractive for adding ADC/TIA circuits under the array, but no YMTC product exposes CIM functions. Public YMTC-affiliated CIM work comes from YMTC and IME-CAS authors (Huo Zongliang, Xia Zhiliang) in Acta Physica Sinica in 2025–2026:
- a **simulated** architecture that requires a back-side source-line slicing process change and integrated ADC/TIA;
- a **process-optimization** paper with wafer-level measured bitline-current statistics.

Neither uses unmodified commercial YMTC dies through their normal interface. I found no public raw-NAND datasheets from YMTC.

### Cited Findings
- **[PRODUCT/NEWS] Xtacking processes the periphery and the memory array on two separate wafers and bonds them with metal vias.** Xtacking 3.0 (2022) shipped in the 4th-generation TLC part X3-9070: 1 Tb, 2400 MT/s I/O. — [Zhihu explainer](https://zhuanlan.zhihu.com/p/42033675); [ESMChina](https://www.esmchina.com/news/3936.html)
- **[NEWS] TechInsights found Xtacking 4.0 in a commercial SSD:** 294 active layers (150 lower deck + 144 upper deck). — [Tom's Hardware](https://www.tomshardware.com/news/chinas-ymtc-xtacking-4.0)
- **[SIM] Zheng Hao, Liu Huiwen, Fang Yuxuan, Fan Dongyu, Han Yuhui, Hou Chunyuan, Liu Wei, Xia Zhiliang, Huo Zongliang, "一种基于3D NAND存储器的存算一体架构及其系统技术协同优化仿真."** Acta Physica Sinica 74(24), 248502 (2025). DOI 10.7498/aps.74.20250891. The corresponding-author email is at ymtc.com. — [APS page](https://wulixb.iphy.ac.cn/cn/article/doi/10.7498/aps.74.20250891?viewType=HTML)
  - Proposes "基于源线背面切分工艺的通用3D NAND架构" (a general 3D NAND architecture based on back-side source-line slicing). SL slicing partitions the array for parallel computation with "array wastage below 3%."
  - Hybrid wafer bonding "integrates high-density ADC/TIA circuits."
  - Supports INT4/INT8. Open-state current σ < 2.5 nA.
  - Simulated results: GPT-2-124M at 20 tokens/s and 5.93 TOPS/W; GPT-2-355M at 8.5 tokens/s and 7.17 TOPS/W, from a PyTorch behavioural simulator.
  - "In INT8 mode, quantization error is the dominant accuracy bottleneck."
  - The abstract page does not say which lines carry inputs or how many strings are summed.
- **[MEASURED wafer statistics + TCAD + SIM] Zheng Hao, Liu Huiwen, Xu Kezhi, Zhang Baotong, Yang Yuancheng, Xia Zhiliang, Huo Zongliang, "面向高精度3维NAND存算一体芯片的多晶硅晶界势垒工艺优化与验证."** Acta Physica Sinica 75(8), 080804 (2026). DOI 10.7498/aps.75.20260199. The corresponding email is at ymtc.com. — [APS page](https://wulixb.iphy.ac.cn/article/doi/10.7498/aps.75.20260199)
  - "串电流分布展宽会导致累加电流偏差, 进而引起计算精度下降问题" (broadening of the string-current distribution causes accumulated-current deviation and degrades accuracy).
  - Polysilicon grain boundaries in the top-select-gate (TSG) channel directly affect the string-current distribution.
  - The process fix (precursor stack with a 9 nm DS layer) cuts the normalized standard deviation of BL current by 50% in wafer-scale statistics.
  - Simulated INT8 GPT-2-124M MVM error falls by 14.7–66.8%.
  - These are process-modified wafers, and the page does not say whether they were product or test wafers.
- **[NEWS/UNVERIFIED] A Zhihu post titled "湖北长江存储和中科院正在合作研发基于国产商用3D NAND…存算一体芯片"** (YMTC and CAS developing a low-cost CIM chip based on domestic commercial 3D NAND for LLM inference). The fetch returned 403, so only the title and search summary were seen. — [Zhihu](https://zhuanlan.zhihu.com/p/1962260222514009571)
- **[NEWS] IME-CAS (2026-04) reported two taped-out chips.** One is a hybrid-domain CIM macro on charge-trapping transistors (INT4/8 and FP4). The other is a near-memory chip on a new ferroelectric NAND. No venue, metrics or relation to YMTC are given. — [CAS news](https://www.cas.cn/syky/202604/t20260414_5106899.shtml)
- **[NEWS] A 2026 YMTC paper reviews 3D NAND evolution (Huo, Xia, Chen)** in 中国科学 / SSI-2025-0457. It is a review, not CIM. — [SciEngine](https://www.sciengine.com/doi/10.1360/SSI-2025-0457); [QQ News](https://news.qq.com/rain/a/20260105A065YY00)

### Inferences
- The YMTC-affiliated proposals depend on adding SL partitioning and ADC/TIA circuits in the bonded CMOS wafer. This implies, though no YMTC source states it, that stock Xtacking product dies lack the per-block SL access and analog readout needed for capabilities (4) and (5).
- The 2026 paper's focus on string-current spread (σ in the nA range) tells you what limits numerical precision when many strings are summed: TSG channel variability. Any experiment summing 2 to 128 strings should expect this.

### Gaps
- I found no YMTC raw-NAND datasheet in the public domain. YMTC mainly sells through SSD and module channels, so a raw-die experiment on YMTC silicon looks impractical. I did not confirm this with a distributor search.
- I did not find YMTC CIM patents on CNIPA or Espacenet. The Chinese query "长江存储 专利 存内计算" returned nothing assignee-confirmed.
- Affiliations on the two Acta Physica Sinica papers are inferred from the ymtc.com email and author names. The abstract pages list no affiliations.

---

## Q4. Macronix: 3D NAND and 3D AND CIM, in-memory search (FortiX), raw SLC NAND datasheets, and product vs test silicon

### Takeaway
Macronix has the richest industrial record of NAND CIM:
- patents on BL-input / source-line-summation MAC;
- an IEDM 2019 nvCIM study on a customized 32-layer 3D NAND prototype;
- an ISSCC 2022 512Gb in-memory-computing 3D NAND chip for vector similarity;
- a VLSI 2023 43Gb in-memory-search chip "based on a 96-layer 3D NAND product" with a new SSL design;
- 3D AND (NOR-type) analog GEMM (IEDM 2022) and an LLM in-storage-computing architecture (IEDM 2025).

All the measured demonstrations use customized or test silicon with modified peripheral or select-line design, not stock MX30LF raw SLC NAND. Macronix does sell 1Gb SLC raw NAND (MX30LF1G18AC) through distributors. I could not retrieve its datasheet text.

### Cited Findings
- **[PATENT] US11934480B2, "NAND block architecture for in-memory multiply-and-accumulate operations."** Macronix. Inventors: Hang-Ting Lue, Hung-Sheng Chang, Yi-Ching Liu. Priority 2018-12-18. Granted 2024-03-19. — [Google Patents](https://patents.google.com/patent/US11934480B2/en)
  - Inputs are BL voltages, kept below 0.3 V.
  - All SSLs are turned on, and a compute voltage is applied to one selected WL. Coefficients are spread over S cells, one per SSL.
  - The block's shared source line carries the sum of B product terms. A current-sensing amplifier on the SL produces a multi-bit output.
  - String current is below 50 nA, and block current averages 10–100 µA.
  - Blocks that share BLs are operated in sequence.
  - No product or test chip is mentioned.
- **[PATENT] US10741247B1, "3D memory array device and method for multiply-accumulate."** Macronix. Inventors: Teng-Hao Yeh, Hang-Ting Lue. Priority 2019-06-21. — [Google Patents](https://patents.google.com/patent/US10741247B1/en)
  - Each block has its own source line, switched by CMOS under the array to a NOR-type SL sense amplifier (about 300 ns).
  - The amplifier compares against Vref. Multiple references give a "hierarchical" multi-level output.
- **[MEASURED on customized prototype] Lue, Hsu, Wei, Yeh, Du, Chen, Wang, Lu (Macronix), "Optimal Design Methods to Transform 3D NAND Flash into a High-Density, High-Bandwidth and Low-Power Nonvolatile Computing in Memory (nvCIM) Accelerator for DNN."** IEDM 2019. DOI 10.1109/IEDM19573.2019.8993652. — [Crossref](https://doi.org/10.1109/iedm19573.2019.8993652); [ResearchGate](https://www.researchgate.net/publication/339262162_Optimal_Design_Methods_to_Transform_3D_NAND_Flash_into_a_High-Density_High-Bandwidth_and_Low-Power_Nonvolatile_Computing_in_Memory_nvCIM_Accelerator_for_Deep-Learning_Neural_Networks_DNN)
  - Georgia Tech/Macronix follow-up (Shim, Jiang, Peng, Yu, MEMSYS 2020) says the prototype "is of industry-grade and has been customized to support CIM paradigm" and that device parameters come from "measured experimental data of a 32-layer 3D NAND chip reported in [13]."
  - Measured cells: on-current about 2 nA, off-current below 1 pA (3 nm polysilicon channel).
  - Inputs are on BLs, and the summed current is sensed at the block SL. The follow-up's own design assumes a 7-bit SAR ADC and estimates an SL capacitance of about 16 pF with settling of hundreds of ns (HSPICE). — [MEMSYS 2020 PDF](https://www.memsys.io/wp-content/uploads/2020/10/p80-shim.pdf)
  - Related: an IRPS 2020 invited paper on read-disturb reliability of nvCIM in 3D NAND (Lue, Hsu, Wang, Lu). — [Crossref DOI](https://doi.org/10.1109/irps45951.2020.9128340)
- **[MEASURED chip] Hu, Wang, Chen, … Meng-Fan Chang, Chun-Hsiung Hung, Chih-Yuan Lu, "A 512Gb In-Memory-Computing 3D-NAND Flash Supporting Similar-Vector-Matching Operations on Edge-AI Devices."** ISSCC 2022, pp. 138–140. DOI 10.1109/ISSCC42614.2022.9731775. Crossref lists the first 12 authors with Macronix affiliation. — [Crossref](https://doi.org/10.1109/isscc42614.2022.9731775); [CityU Scholars](https://scholars.cityu.edu.hk/en/publications/a-512gb-in-memory-computing-3d-nand-flash-supporting-similar-vect/)
  - Computes vector-vector multiplication (VVM) for cosine similarity.
  - It names two challenges: "low readout accuracy when there is a large amount of current summation by using the wide range Vt-level of cells," and high readout power to keep settling time constant across varying summation currents.
  - The abstract page gives no precision or sensing details.
- **[MEASURED chip, product-derived, search rather than MAC] Hsieh, Lue, Li, Hung, Hung, Wang, Lu (Macronix), "Chip Demonstration of a High-Density (43Gb) and High-Search-Bandwidth (300Gb/s) 3D NAND Based In-Memory Search Accelerator for TCAM and Proximity Search of Hamming Distance."** VLSI 2023, paper T15-1. DOI 10.23919/VLSITechnologyandCir57934.2023.10185361. — [VLSI 2023 tip sheet](https://archive.vlsisymposium.org/23web/files/press_kit/VLSI2023_TipSheet_En_re1_230519.pdf); [Crossref](https://doi.org/10.23919/vlsitechnologyandcir57934.2023.10185361)
  - The tip sheet says the chip is "based on a 96-layer 3D NAND product."
  - "The novel String-Select Line design achieved 300Gb/s search bandwidth with a measured power of less than 400mW."
  - The chip outputs which BL address matches.
- **[NEWS] FortiX (FMS 2022)** is in-memory search built on non-volatile ternary CAM (nvTCAM): keyword and Hamming search, no MAC.
  - Macronix described a 96-layer FortiX 3D NAND with a 64 Gbit die "in prospect" and a 32-layer 3D NOR variant.
  - No availability date was given. — [Blocks & Files](https://www.blocksandfiles.com/ai-ml/2022/08/12/macronix-intros-compute-in-nand-storage/1609896)
- **[MEASURED? 3D AND, not NAND] Lue et al., "Analog Computing in Memory (CIM) Technique for General Matrix Multiplication (GEMM) to Support DNN and Cosine Similarity Search Computing using 3D AND-type NOR Flash Devices."** IEDM 2022. — [ResearchGate](https://www.researchgate.net/publication/367370008_Analog_Computing_in_Memory_CIM_Technique_for_General_Matrix_Multiplication_GEMM_to_Support_Deep_Neural_Network_DNN_and_Cosine_Similarity_Search_Computing_using_3D_AND-type_NOR_Flash_Devices)
- **[ARCHITECTURE; measured status unclear] Yu-Yu Lin, Feng-Min Lee, Ming-Hsiu Lee, Keh-Chung Wang, Chih-Yuan Lu, "3D NAND-based Mixed-mode in-Storage-Computing Architecture for Large Language Model."** IEDM 2025, paper 5-2. DOI 10.1109/IEDM50572.2025.11353631.
  - Uses Qwen 2.5 Math 7B and MATH500 to assess the effect of iSC-induced errors in an "iSC + ALU hybrid system."
  - The session summary says it "demonstrates the execution of a compact LLM." — [IEDM 2025 program v4](https://static1.squarespace.com/static/67a3eee4385dfb3390804f02/t/690e4eca5393d146db3b608c/1762545355037/IEDM+2025+Final+Program-v4.pdf); [Crossref](https://doi.org/10.1109/iedm50572.2025.11353631)
  - Affiliation conflict: a search summary of program v5 lists TUM and NYCU as additional affiliations. Program v4 and Crossref list only Macronix. — [IEDM program v5](https://static1.squarespace.com/static/67a3eee4385dfb3390804f02/t/692722bf0dad5d330cf60d98/1764172479207/IEDM+2025+Final+Program-v5.pdf)
- **[SECONDARY, conflicting] A Chinese review (Zhou Zheng, Huang Peng, Kang Jinfeng, PKU, Acta Physica Sinica 2022)** was surfaced by search with the claim "2019 年，旺宏公司成功演示了基于64 GB 容量、SLC 存储密度和3D堆叠结构的NAND 型flash 颗粒…矩阵向量乘积运算加速器" (Macronix demonstrated a matrix-vector accelerator on 64 GB SLC 3D NAND parts).
  - This conflicts with Shim et al.'s statement that the 2019 work used a customized 32-layer prototype.
  - I could not read the PKU PDF (connection reset). — [APS PDF link](https://wulixb.iphy.ac.cn/pdf-content/10.7498/aps.71.20220397.pdf); contrast [MEMSYS 2020](https://www.memsys.io/wp-content/uploads/2020/10/p80-shim.pdf)
- **[PRODUCT] MX30LF1G18AC 1Gb SLC NAND (128M×8, 2.7–3.6 V, TSOP-48 or VFBGA-63).**
  - Microchip USA's listing says it has an "ONFI interface."
  - Temperature grades: -TI is −40 to 85 °C; -XKJ/-TJ are −40 to 105 °C.
  - Distributors list access time as 16 ns or 25 ns, which conflicts.
  - JLCPCB/LCSC list it as part C128679, and the datasheet link is a time-limited signed URL. — [Farnell](https://uk.farnell.com/macronix/mx30lf1g18ac-ti/flash-memory-1gbit-40-to-85deg/dp/3129216); [Microchip USA](https://www.microchipusa.com/product/macronix/memory-2/MX30LF1G18AC-XKJ); [JLCPCB](https://jlcpcb.com/partdetail/MX30LF1G18AC-TI/C128679)

### Inferences
- Macronix's architecture puts inputs on BLs and sums along the SL within one block, with all SSLs on (capabilities 1, 3, 4 and 5). It needs per-block SL isolation, BL analog drivers and an SL ADC or sense amplifier. Those circuits are absent or undocumented on standard NAND, where the SL is common and BLs are driven by the page buffer to fixed precharge levels. So even Macronix's "product-based" 2023 chip needed a new SSL design.
- None of the Macronix measured CIM results were obtained on stock MX30LF parts through the public command set.
- For the user's preferred topology (many strings in different blocks summing on one BL), the Macronix scheme is the transpose: many BLs summing into one SL.

### Gaps
- I could not retrieve the MX30LF1G18AC datasheet text. Macronix's site rendered "Loading…", and JLCPCB's link needs a signed token. Whether it implements ECh, EEh/EFh and which feature addresses remain unverified. It is also not confirmed whether the TSOP part is "Not For New Designs" (one vendor) or Active (Future Electronics).
- I could not retrieve full texts of ISSCC 2022, VLSI 2023 or IEDM 2025 5-2. The number of strings summed, ADC bits and measured accuracy remain unknown.

---

## Q5. Korean academia (SNU, KAIST, Hanyang, POSTECH, SeoulTech): NAND VMM/CIM measurements, chip source, summation and readout

### Takeaway
The Seoul National University group of Jong-Ho Lee (with B.-G. Park co-filings) dominates Korean NAND-CIM work:
- early work measured single 26-nm floating-gate 2D NAND cells and strings (vendor not named) and simulated the networks;
- 2024–2026 work measured "commercial TLC V-NAND supplied by SK hynix" at wafer level with a probe station and B1500A. Multi-string BL summation and ADC readout were simulated, not measured on chip.

KAIST appears through SK hynix-co-assigned patents (Seonghwan Cho) and FeNAND device papers. SeoulTech (Wonbo Shim) published architecture estimates. I found no Korean paper measuring parallel multi-string current summation through a commercial die's own periphery.

### Cited Findings
- **[MEASURED cells; SIM network] S.-T. Lee and J.-H. Lee, "Neuromorphic Computing Using NAND Flash Memory Architecture With Pulse Width Modulation Scheme."** Frontiers in Neuroscience, 2020. — [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC7530297/)
  - "We measured floating-gate 2D NAND cells fabricated with 26-nm technology." No vendor is named. A measured string has 64 cells plus select and dummy cells.
  - Inputs are PWM pulses "simultaneously imposed on all SSLs." Weights are differential pairs on even and odd BLs. Charge is integrated in a current-mirror and capacitor neuron with no ADC.
  - Each cell has 8 levels (0–1.4 µA in 200 nA steps), and two cells give 4-bit weights. W2 variation is 3.43%.
  - MNIST 98.14% and CIFAR-10 89.6% are simulated.
  - The search summary of the group's 2019 "Operation Scheme of Multi-Layer Neural Networks Using NAND Flash Memory as High-Density Synaptic Devices" says VMM time complexity is O(N) and notes that layer size is set by the WL and BL counts. — [ResearchGate](https://www.researchgate.net/publication/336574520_Operation_Scheme_of_Multi-Layer_Neural_Networks_Using_NAND_Flash_Memory_as_High-Density_Synaptic_Devices)
- **[MEASURED cells; SIM architecture] Binary NAND synapse (4T2S, two strings per synapse, differential sensing; on/off about 7×10^5)**, published in Neurocomputing 2022. The IEDM 2019 predecessor is "High-density and highly-reliable binary neural networks using NAND flash memory cells as synaptic devices." — [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0925231222005756)
- **[MEASURED cells; SIM scheme] Ko, Park, Im, Kim, Koo, Yang, Lee, "Vertical NAND flash memory-based matrix-matrix multiplication scheme for energy-efficient attention score computation."** Neurocomputing 2025. DOI 10.1016/j.neucom.2024.129210. The search snippet reports cells representing "over 50 levels" and energy at 12.2% of a TPU's. I could not read the full text (403), so the device origin is unverified. — [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4953738); [SNU GENIE page](https://genie.snu.ac.kr/publication/vertical-nand-flash-memory-based-matrix-matrix-multiplication-scheme-for-energy-efficient-attention-score-computation/)
- **[MEASURED cells at wafer level; SIM VMM] SNU + SK hynix PUF neural network (Advanced Science 2026).** Details are under Q2: probe station, B1500A, wafers supplied by SK hynix, BL summation and 7-bit ADC simulated. — [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC13137843/)
- **[SIM] SeoulTech (Wonbo Shim et al.), "Technological Design of 3D NAND-Based Compute-in-Memory Architecture for GB-Scale Deep Neural Network."** It estimates a 512 Gb, 128-layer 3D NAND CIM at 1.15–19.01 TOPS/W (search snippet). The related co-design paper estimates a chip size of 166 mm² with 7 nm logic. — [SeoulTech Pure](https://pure.seoultech.ac.kr/en/publications/technological-design-of-3d-nand-based-compute-in-memory-architect/); [ResearchGate](https://www.researchgate.net/publication/352865690_System-Technology_Co-Design_of_3D_NAND_Flash_based_Compute-in-Memory_Inference_Engine)
- **[MEASURED research devices, FeNAND] KAIST FeNAND cells at IEDM 2025** (2 nm IGZO trap layer; NC-NAND). These are device papers, not CIM on commercial NAND. — [IEDM 2025 program](https://static1.squarespace.com/static/67a3eee4385dfb3390804f02/t/690e4eca5393d146db3b608c/1762545355037/IEDM+2025+Final+Program-v4.pdf)
- **[PATENT] KAIST (Seonghwan Cho) with SK hynix.** US11526739B2, US11397561B2 and US12444467B2 are described under Q2.

### Inferences
- Korean academic "commercial V-NAND" results depend on vendor-supplied wafers, test pads and instruments (special access). They show cell-level analog weight capability above 6 bits, not chip-level analog summation through product periphery.
- The SNU input scheme (PWM on SSL/DSL, many strings feeding one BL) matches the user's target topology. It was demonstrated only in simulation using measured single-cell data.

### Gaps
- I found no Hanyang or POSTECH NAND-CIM paper that measures commercial chips. A POSTECH OASIS record appeared in a Chinese search, but its content was not checked. — [POSTECH OASIS](https://oasis.postech.ac.kr/handle/2014.oak/117381)
- I could not verify who fabricated the 26-nm 2D NAND cells (SNU 2019–2020). It is often assumed to be industry, but no source here states the vendor.
- I did not search DBpia, KCI or RISS directly. Korean-language web searches returned no Korean-language NAND-MAC papers.

---

## Q6. Chinese academia (PKU, Tsinghua, IME-CAS, Fudan, HUST, Hubei Yangtze Memory Labs): NAND-based VMM/CIM

### Takeaway
Chinese NAND-CIM work is mostly simulation, process or device studies:
- YMTC/IME-CAS: back-side SL slicing simulation and TSG process optimization with wafer statistics;
- Tsinghua/ASU: a SPICE study of 3D NAND VMM;
- HUST and Hubei Yangtze Memory Labs: a review that states outright that vendors do not open chip-level port access, and that most work simulates networks from cell data measured on vendor samples.

I found no Chinese paper measuring VMM with multi-string summation on a commercial NAND die's own sense amplifiers.

### Cited Findings
- **[REVIEW] Chen Yang-Yang, He Yu-Hui, Miao Xiang-Shui, Yang Dao-Hong, "基于3D-NAND的神经形态计算."** Acta Physica Sinica 71(21), 210702 (2022). Affiliations: HUST; XMC (Wuhan Xinxin) post-doctoral station; Hubei Yangtze Memory Laboratories. — [APS page](https://wulixb.iphy.ac.cn/cn/article/doi/10.7498/aps.71.20220974); [PDF](https://wulixb.iphy.ac.cn/pdf-content/10.7498/aps.71.20220974.pdf)
  - Section 3 (总结与展望) says: "由于 3D-NAND 的专利特性, 厂商并未开放用户对芯片颗粒端口的权限. 目前的工作中, 前向传播过程和反向传播过程并未做硬件实现, 多数是基于厂商样片测得的存储单元特性以及读误差分布, 通过电路和软件层面上仿真得到的结果."
  - Translation: because 3D NAND is proprietary, vendors have not opened chip-level port access to users. In current work, forward and backward propagation have not been implemented in hardware. Most results are simulations at circuit and software level, based on cell characteristics and read-error distributions measured on vendor sample chips.
  - The review also mentions a 2021 SNU and SK hynix collaboration on a single device for neuromorphic computing.
  - The abstract notes that "owing to the proprietary nature of the technology, there are few hardware implementations."
- **[SIM] Panni Wang, Feng Xu, Bo Wang, Bin Gao, Huaqiang Wu, He Qian, Shimeng Yu (Tsinghua/ASU), "Three-Dimensional NAND Flash for Vector–Matrix Multiplication."** IEEE TVLSI (2018/2019). Uses array-level SPICE simulation to tune biases. — [IEEE Xplore](https://ieeexplore.ieee.org/document/8571188/); [ASU experts](https://experts.azregents.edu/en/publications/three-dimensional-nand-flash-for-vector-matrix-multiplication/)
- **[SIM / MEASURED wafer statistics] YMTC/IME-CAS (Huo Zongliang group), Acta Physica Sinica 2025 and 2026.** Details are under Q3. — [2025](https://wulixb.iphy.ac.cn/cn/article/doi/10.7498/aps.74.20250891?viewType=HTML); [2026](https://wulixb.iphy.ac.cn/article/doi/10.7498/aps.75.20260199)
- **[NEWS] IME-CAS 2026-04: a charge-trap-transistor hybrid-domain CIM macro and a ferroelectric-NAND near-memory chip** (taped out, no metrics). Not commercial NAND. — [CAS news](https://www.cas.cn/syky/202604/t20260414_5106899.shtml)
- **[MEASURED, not NAND] IEDM 2025 session 5 included Chinese CIM papers on other device types:** IME-CAS/Tsinghua monolithic 3D Si-FinFET/CNT; PKU 3D ferroelectric capacitor; Tsinghua ferroelectric parallel read. — [IEDM 2025 program](https://static1.squarespace.com/static/67a3eee4385dfb3390804f02/t/690e4eca5393d146db3b608c/1762545355037/IEDM+2025+Final+Program-v4.pdf)
- **[REVIEW] Zhou Zheng, Huang Peng, Kang Jinfeng (PKU), "基于非挥发存储器的存内计算技术."** Acta Physica Sinica 2022. Its Macronix claim conflicts with other sources (see Q4). — [PDF link](https://wulixb.iphy.ac.cn/pdf-content/10.7498/aps.71.20220397.pdf)

### Inferences
- The HUST/Yangtze-Lab review's statement about port access matches what the public datasheets show (Q8). It is independent confirmation that, as of 2022, Chinese groups were not doing chip-level analog summation on commercial NAND through public interfaces.
- The YMTC-affiliated authors' emphasis on TSG polysilicon variability gives a concrete physical precision limit for summed-string readout.

### Gaps
- I found no Fudan or HUST paper measuring NAND VMM on commercial dies. PKU's NAND-related CIM appears only as reviews in my searches. CNKI and Baidu Xueshu were not searched directly.
- The Zhihu claim of a CAS–YMTC "commercial 3D NAND" CIM chip is unverified (403).

---

## Q7. Taiwanese academia (NTHU, NYCU, NCKU, NTU, Academia Sinica): NAND-based CIM

### Takeaway
Taiwanese academic NAND-CIM work appears mainly as co-authorship on Macronix silicon:
- ISSCC 2022 512Gb IMC 3D NAND, co-authored with Meng-Fan Chang, Tei-Wei Kuo and Yuan-Hao Chang (affiliations not verified on the page I read);
- an NYCU affiliation listed on IEDM 2025 5-2 in one program version.

I found no standalone NTHU, NYCU or NCKU paper measuring CIM on commercial NAND dies.

### Cited Findings
- **ISSCC 2022 "A 512Gb In-Memory-Computing 3D-NAND Flash…"** lists 19 authors, including Yuan-Hao Chang, Hsiang-Pang Li, Tei-Wei Kuo and Meng-Fan Chang. Crossref shows Macronix affiliation for the first 12 authors. — [CityU Scholars](https://scholars.cityu.edu.hk/en/publications/a-512gb-in-memory-computing-3d-nand-flash-supporting-similar-vect/); [Crossref](https://doi.org/10.1109/isscc42614.2022.9731775)
- **Academia Sinica IIS's 2022 publication list includes the work**, per search results. — [IIS Sinica](https://iis.sinica.edu.tw/en/page/ResearchOverview/Publications/2022.html)
- **A MICRO 2022 follow-up, "ICE: 3D NAND-based In-Memory Computing for Vector Similarity Search Acceleration,"** was noted in search results. I did not read it. — [dblp](https://dblp.org/pid/316/3624)
- **IEDM 2025 5-2 (Macronix iSC for LLM):** one program version lists NYCU and TUM affiliations. See Q4. — [IEDM program v5](https://static1.squarespace.com/static/67a3eee4385dfb3390804f02/t/692722bf0dad5d330cf60d98/1764172479207/IEDM+2025+Final+Program-v5.pdf)

### Inferences
- Taiwanese groups that want NAND CIM silicon appear to work through Macronix's customized chips rather than commercial raw parts.

### Gaps
- I did not search Airiti or NDLTD Taiwan theses directly, so any NCKU or NYCU master's theses measuring commercial NAND are unknown.
- Author affiliations for the Taiwanese academics on ISSCC 2022 were not confirmed from the paper.

---

## Q8. Small SLC raw-NAND suppliers (Winbond, GigaDevice, ISSI, ESMT, Alliance, Macronix MX30LF, legacy Samsung/Hynix): documentation completeness, ONFI/Set-Get Features, price, topology

### Takeaway
Winbond (W29N) and GigaDevice (GD9F) have complete public datasheets:
- ONFI parameter page (ECh), Unique ID (EDh), Get/Set Features (EEh/EFh), cache read, copy-back, and on GigaDevice two-plane read.

The public Set/Get Features addresses are limited to timing mode, I/O drive strength and RY/#BY pull-down (Winbond), or output drive strength only (GigaDevice). No read-reference (Vread) offset, sense-time trim, or multi-block or multi-WL sensing is documented. On these parts the only public analog-relevant knob is "which page or block to read." Capabilities (1) through (5) are not exposed. Typical price is about US$3–4 per unit for 1Gb SLC TSOP-48.

### Cited Findings
- **[PRODUCT DOC] Winbond W29N01GV 1Gb 3.3 V SLC NAND datasheet, Rev H, 2018-01-11 (public mirror).** — [mirror PDF](https://cdn.eicom.ru/media/PDF/2065449.pdf)
  - p.14: 1024 blocks × 64 pages; 2048+64-byte page; separate data and cache registers.
  - Command table (section 8, p.16): Page Read 00h-30h; Copy-Back Read 00h-35h; Sequential Cache Read 31h; Random Cache Read 00h-31h; Last Address Cache Read 3Fh; Read ID 90h; Read Status 70h; Copy-Back Program 85h-10h; Cache Program 80h-15h; Block Erase 60h-D0h; Read Parameter Page ECh; Read Unique ID EDh; Get Features EEh; Set Features EFh; OTP commands A0h-10h, A5h-10h, AFh-30h.
  - p.36: the feature table lists only 01h Timing mode, 80h Programmable I/O drive strength and 81h Programmable RY/#BY pull-down strength. All other addresses are reserved.
  - pp.39–40: Get/Set Features operation.
  - p.52: tR = 25 µs maximum.
- **[PRODUCT] Winbond's product page says the W29N-HV series (W29N01HV, W29N02KV, W29N02GV, W29N04GV, W29N08GV) is "ONFI 1.0 compliant,"** with a 2048+64-byte page, 3 V, x8 multiplexed bus, and Automotive Grade 2 and 2+. — [Winbond](https://winbond.com/hq/product/code-storage-flash/onfi-nand/w29n-hv/)
- **[PRODUCT DOC] Winbond W29N01GZ/W (1.8 V) datasheet, Rev G, 2016-02-01.** — [chipdip mirror](https://static.chipdip.ru/lib/704/DOC041704624.pdf)
- **[PRICE] W29N01HVSINA (TSOP-48):**
  - Cytech: Active, US$3.68 at quantity 1 down to US$2.91 at 10k, 480 in stock;
  - Digi-Key: about US$3.58 per a third-party snapshot, showing 0 stock;
  - RS UK: about £3.06 at quantity 5+, temporarily out of stock.
  - Snapshots are of varying dates. — [Cytech](https://www.cytechsystems.com/fr/product/w29n01hvsina); [RS UK](https://uk.rs-online.com/web/p/flash-memory/1882817P); [electronicspecifier/Digi-Key](https://electronicspecifier.com/product-centre/distributors/digi-key/part/5a966687d6e73f05139af2e5)
- **[PRODUCT DOC] GigaDevice GD9Fx2GxF2A 2Gb SLC (2K+128), DS-00879 Rev 1.1 (public via Endrich).** — [Endrich PDF](https://endrich.com/Datenbl%C3%A4tter/Aktive%20Komponenten/DS-00879-GD9FU2G8F2A-Rev1.1.pdf)
  - p.10: 2048 blocks, two planes of 1024 blocks, 64 pages per block; one cache register and one data register per plane.
  - p.14 command set: 00h-30h; 00h-35h; Special read for copy-back 00h-36h; 05h-E0h; 06h-E0h; cache read 31h, 00h-31h, 3Fh; 90h; 70h; Read Status Enhanced 78h; 80h-10h; 85h; 85h-10h; 80h-15h; 60h-D0h; FFh; Page Re-program 8Bh-10h; ECh; EDh; EEh; EFh; multi-plane program, erase and copy-back; "Read page two-plane 00H-32H-00H-30H."
  - p.52: Set Feature (EFh) defines only feature address 10h, Output Driver strength. Other addresses are reserved.
  - p.65: tR = 25 µs maximum.
- **[PRODUCT DOC/catalog] GigaDevice ordering code:** "9F" means parallel NAND without internal ECC, "U" means 2.7–3.6 V. The 1Gb variants GD9FU1G8F2DMGI and GD9FU1G8F3ALGI are listed as ONFI, TSOP-48. — [zenode](https://zenode.ai/parts/8azdxrj97m); [pcxco](https://pcxco.com/product/gd9fu1g8f3algi/)
- **[PRICE] GigaDevice 1Gb parallel SLC on Mouser India:** GD9FU1G8F2DDGI at ₹215.25 per unit at a 4,800-unit tier, and GD9FS1G8F2DMGI at ₹536.72 with a 960 minimum. Both were non-stocked. — [Mouser India](https://www.mouser.in/en/c/embedded-solutions/memory-data-storage/memory-ics/nand-flash/?pg=9)
- **[PRODUCT DOC] Hynix H27U1G8F2B:** basic command set without ONFI parameter page or Features. See Q2 for page references. — [Farnell PDF](https://www.farnell.com/datasheets/1605619.pdf)
- **[PRODUCT DOC] Samsung K9F1G08U0A:** basic commands only, and undefined commands are prohibited. See Q1. — [cryptomuseum PDF](https://cryptomuseum.com/covert/bugs/aid/7178/files/K9F1G08Q0A.pdf)
- **[PRODUCT] ISSI IS34ML01G084:** 1Gb SLC, 2.7–3.6 V, 25 ns, 4-bit ECC requirement, 48-TSOP. Listings conflict on temperature (−40 to 105 °C vs −40 to 85 °C). — [absunshine](https://www.absunshine.com/en/parts/IS34ML01G084-TLE-ISSI-5469072); [Avnet](https://www.avnet.com/americas/product/issi/is34ml01g084-tli-tr/evolve-36976907/)
- **[PRODUCT] ESMT F59L1G81MB:** 1Gb SLC, 2K+64 page, 128K+4K block, 100K P/E cycles. Distributors list cache program and read, copy-back and automatic page-0 read. Packages TSOP-48 or BGA-63/67 depending on suffix. — [Suntsu](https://suntsu.com/product/integrated-circuits/memory/f59l1g81mb-25tig2m/)
- **[PRODUCT, ONFI general] The ONFI parameter page "optional commands" field bit 2 indicates Get/Set Features support.** The Linux and RTEMS ONFI headers define Get Features 0xEE, Set Features 0xEF and feature address 0x01 (timing mode). — [Intel Agilex5 doc](https://www.intel.com/content/www/us/en/programmable/hps/agilex5/topics/register_rf_controller_params_device_features.html); [RTEMS header](https://git.rtems.org/rtems/tree/bsps/include/dev/nand/xnandpsu_onfi.h); [Linux onfi.h mirror](https://tangled.org/tjh.dev/kernel/blob/v6.0/include/linux/mtd/onfi.h)
- **[MEASURED, commercial chips, binary only; vendor not named; uses non-public test mode] Flash-Cosmos (Park et al., MICRO 2022; arXiv 2209.05566):** relevant topology evidence. — [arXiv PDF](https://arxiv.org/pdf/2209.05566)
  - It states that "thousands of NAND strings are connected to the same bitline," so sensing WLs in different blocks at once gives bitwise OR (inter-block multi-wordline sensing, MWS).
  - It tested 160 real 48-layer 3D TLC chips (tR = 22.5 µs SLC mode) on an FPGA platform. The platform used "various test-mode commands necessary to … simultaneously activate multiple WLs."
  - Inter-block MWS latency was measured with up to 32 blocks active at once. Power stays below that of an erase up to 4 blocks.
  - "NAND flash vendors consider their test-mode command design to be proprietary and do not reveal any details in publicly-accessible documentation."
  - The readout is binary (a single sense-amplifier trip point).

### Inferences
- Among small vendors, Winbond's W29N01GV/HV and GigaDevice's GD9F family are the best-documented, cheapest (about $3–4), stocked or orderable 2D SLC parallel-NAND parts. They are ONFI-style, with parameter page, Unique ID and Get/Set Features.
- Their public Features are limited to interface electrical settings (timing mode, drive strength). Nothing documented changes Vread, sense timing or reference, or enables multi-block activation. That is the gap for capabilities (2), (4) and (5).
- GigaDevice's two-plane read (00h-32h-00h-30h) reads two blocks in different planes at the same time. Each plane has its own page buffer and bitlines (per the p.10 organization), so this is not current summation on a shared bitline.
- Topology for 2D planar SLC: each block contributes one series string per bitline, and all blocks in a plane share the bitlines. Flash-Cosmos's inter-block MWS shows that real (3D) chips can physically sum several blocks' strings on one BL. It needed undocumented test-mode commands and yielded only binary OR.
- With public commands only, an experimenter could measure numerical information indirectly, for example by repeated reads under different timing modes. A numerical multi-string sum would need off-label methods. The datasheets give no basis for this, and Samsung explicitly prohibits undefined commands.
- Legacy Samsung K9F and Hynix H27U parts are worse documented than Winbond and GigaDevice parts: no parameter page or Features, and a minimal command set. Older is not better here unless the specific datasheet is unusually detailed, which those I read are not.

### Gaps
- I did not obtain full datasheets for Macronix MX30LF1G18AC, ISSI IS34ML01G084, ESMT F59L1G81MB, Alliance Memory (for example AS5F3 series), Dosilicon or XTX. I could not verify their ONFI parameter-page and feature-address contents or the presence of any vendor-specific "read level" features.
- I did not search Alliance Memory, Dosilicon or XTX at all because of time limits.
- I could not get current LCSC prices for W29N01HV or GD9FU1G8F2A. The LCSC search page did not render via fetch.
- No public SLC datasheet I read documents internal string count per block, sense-amplifier type (current vs voltage sensing) or sense-node capacitance.
