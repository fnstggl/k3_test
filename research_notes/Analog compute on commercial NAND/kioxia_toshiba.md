# Kioxia / Toshiba Memory: analog inner-product (compute-in-memory) on NAND flash, and the public raw-NAND documentation that bears on it

Scope note: these notes cover only Kioxia and Toshiba (Memory). The research ran on 2026-10-17. Labels used throughout:
- **[MEASURED]**: a result on real silicon.
- **[PATENT]**: a proposal in a patent.
- **[PRODUCT DOC]**: something stated in a public datasheet.
- **[INFERENCE]**: my own reasoning, not stated by a source.

The two IMW full papers are paywalled on IEEE Xplore and their figures are access-restricted (HTTP 403). I did not get around those restrictions. Everything below comes from the IEEE abstracts, the figure captions (served publicly by IEEE's metadata endpoint), Kioxia's own public "Technology Topics" pages and the figures on them, the IEEE reference lists, and USPTO full text.

---

## Q1. Kioxia IMW 2025 and IMW 2026 papers (Kudo, Aiba, Sanuki et al.): what was shown, on what silicon, and how

### Takeaway
Kioxia ran a time-multiplexed scheme on real 3D-flash silicon. Several blocks on the same bitline are activated one after another, and a "current-control (CC) cell" in each string caps the on-string current at a small constant value. The precharged bitline therefore loses charge in proportion to the inner product, and the on-chip sense amplifier (S/A) makes a pass/fail decision at a chosen sense or activation time. Results:
- IMW 2025: 1-bit × 128-dimension.
- IMW 2026: 3-bit × 128-dimension, where activation time encodes bit weight and query value.

Accumulation is **sequential** (charge integrated on the bitline across non-overlapping block activations), not simultaneous summation of many strings. Readout is a **threshold/comparator decision**, swept over time, not a single-shot multi-bit conversion. The publications do not name the die generation or the test method (internal test mode or not). Kioxia calls the scheme "fully compatible with conventional 3D flash memory".

### Cited Findings

**Paper 1 (IMW 2025)**
- Title: "Energy-Efficient In-Memory Computing using 3D Flash Memory with Sequential Multi-Block Activation and Current Control Cell (CC cell)".
- Authors: Kana Kudo, Yuta Aiba, Kazuma Hasegawa, Xu Li, Yuichi Sano, Tomoya Sanuki.
- Venue: 2025 IEEE International Memory Workshop (IMW), pp. 1–4, publication date 18 May 2025. DOI 10.1109/IMW61990.2025.11026979; IEEE article 11026979.
- Affiliations: Memory Div. and Frontier Technology R&D Institute, Kioxia Corporation.
- Sources: [IEEE Xplore 11026979](https://ieeexplore.ieee.org/document/11026979); [DOI](https://doi.org/10.1109/IMW61990.2025.11026979).
- It was talk 5.1 in Session 5 "NAND II", proceedings page 57 — [IMW 2025 proceedings TOC (Curran)](https://www.proceedings.com/content/080/080626webtoc.pdf).
- Kioxia's English and Japanese "Technology Topics" summaries are dated Aug 7, 2025 and credit the Memory Division — [Kioxia topic-85 (EN)](https://www.kioxia.com/en-jp/rd/technology/topics/topics-85.html); [Kioxia topic-85 (JA)](https://www.kioxia.com/ja-jp/rd/technology/topics/topics-85.html).

**IMW 2025 abstract (verbatim key points)** — [IEEE Xplore 11026979](https://ieeexplore.ieee.org/document/11026979)
- "Since the high input voltage of Vpp for the word line (WL) driver circuit is externally supplied, the Vread for the WL voltage of unselected cells and the Vcc for supply voltage to circuits other than the WL driver can be reduced."
- "The power consumption during read operation of single level cell (SLC) is reduced by 56% at Vcc and 98% at Vpp."
- "Key vector data is stored in multiple blocks, and query vector data is input as WL voltage, and the on-current of each bit line (BL) is determined by the CC cell. No additional WL control circuit is required, and only one cell is used per data."
- "inner product (IP) … can be determined with sufficient accuracy for 128-dimensional vectors as well as for 8-dimensional ones."
- "energy consumption is significantly reduced by 99.4%, and the memory access energy becomes 0.17 pJ/bit."

**IMW 2025 figure captions** (public via IEEE; images not viewable) — [IEEE Xplore 11026979](https://ieeexplore.ieee.org/document/11026979)
- Fig. 2: Vread "reduced from 9 V to 3 V during read operation".
- Fig. 3: "Vpp (external input voltage for the circuit of WL side) is reduced from 12 V to 4 V".
- Fig. 4: "Vcc (supply voltage for the circuit on BL side) is reduced from 3.3 V to 2.3 V".
- Fig. 7: "energy consumption of Icc and Ipp when multiple blocks are activated sequentially".
- Fig. 8: "Key data is stored in 8 blocks along BL, and query data is selected cell WL voltage."
- Fig. 9: "The WL voltage of CC cell is smaller than Vth of CC cell."
- Fig. 10: "timing diagram for sequential multi-block activation".
- Fig. 11: "The sense time (T_SEN) and cumulative probability for 128 k (=131,073) BLs where key vector data is stored … the T_SEN versus the WL voltage of the CC cell (e).". The odd count 131,073 is as printed.
- Fig. 12: "Four different ways to place the key vector data (m=4 … or m=128 …) in memory array."
- Fig. 13: experimental results for 16-, 32-, 64- and 128-dimensional data.

**Kioxia's public schematic for 2025** (Fig. 1 on topic-85) — [Kioxia topic-85 Fig.1](https://www.kioxia.com/content/dam/kioxia/ja-jp/rd/technology/topics/img/topics-85_img_001.png)
- One bitline runs across BLK1, BLK2 and BLK3 to a single "S/A".
- Each string contains, in order: select-gate-drain, unselected cells, the selected cell (driven by the WL decoder at the query bias), Vread cells, the CC cell, and select-gate-source.
- A "Vpp" box feeds the WL decoder. The legend reads "Query: WL bias" and "Key: Stored data".
- The timing diagram labelled "Sequential block activation" shows the BLK1, BLK2 and BLK3 WL pulses **one after another, without overlap**.

**Kioxia's 2025 result plot** (topic-85 Fig. 2) — [Kioxia topic-85 Fig.2](https://www.kioxia.com/content/dam/kioxia/ja-jp/rd/technology/topics/img/topics-85_img_002.png)
- It plots cumulative probability against T_SEN (µs, log scale) for IP0, 1, 2, 4, 8, 16, 32, 64 and 128.
- Approximate positions, read off the figure by me: IP128 ≈ 0.15 µs, IP64 ≈ 0.6 µs, IP32 ≈ 1–1.5 µs, IP8 ≈ 5–7 µs, IP1 ≈ 20–35 µs, IP0 ≈ 800 µs.
- So the sense time at which the S/A flips falls roughly as 1/IP.

**Energy** — [Kioxia topic-85 (EN)](https://www.kioxia.com/en-jp/rd/technology/topics/topics-85.html); [Fig. 3 image](https://www.kioxia.com/content/dam/kioxia/ja-jp/rd/technology/topics/img/topics-85_img_003.png)
- Conventional read: 30 pJ/bit.
- Read at the low-voltage condition "COND5": 18 pJ/bit. Fig. 3 shows the WL bit-access part removed; the remaining parts are BL bit access and data transfer.
- In-memory computing: 0.17 pJ/bit.
- Kioxia's text: "fully compatible with conventional 3D flash memory".

**Paper 2 (IMW 2026)**
- Title: "Multi-level In-Memory Computing with 3D Flash Memory using Activation-Time-Modulated Sequential Multi-Block Access and Tightly Integrated Current Control Cell (CC Cell)".
- Authors: the same six. All are listed under "Frontier Technology R&D Institute, *Memory Div., Kioxia Corporation, Japan".
- Venue: 2026 IEEE IMW, pp. 1–4, conference 10–13 May 2026. DOI 10.1109/IMW68301.2026.11532787; IEEE article 11532787.
- Sources: [IEEE Xplore 11532787](https://ieeexplore.ieee.org/document/11532787); [DOI](https://doi.org/10.1109/IMW68301.2026.11532787).
- IMW 2026 was held in Leuven, Belgium — [imec IMW 2026 page](https://www.imec-int.com/en/events/ieee-international-memory-workshop).
- A search-engine excerpt of the now-removed program PDF listed "[8.2] Kana Kudo, Kioxia" in Session 8 "Advanced and Emerging Memories II" (Wed May 13, 10:35). The PDF now returns 404 — [IMW2026 Program.pdf (dead link)](https://ewh.ieee.org/soc/eds/imw/IMW2026%20Program.pdf).
- Kioxia topic-93, dated Sept 28, 2026 — [Kioxia topic-93 (EN)](https://www.kioxia.com/en-jp/rd/technology/topics/topics-93.html); [Kioxia topic-93 (JA)](https://www.kioxia.com/ja-jp/rd/technology/topics/topics-93.html).

**IMW 2026 abstract (verbatim key points)** — [IEEE Xplore 11532787](https://ieeexplore.ieee.org/document/11532787)
- The prior work "demonstrated 1-bit and 128-dimensional approximate search with one cell per bit".
- New in this work: "(1) … optimized the CC cell Vth distribution tightly and maintained normal Single Level Cell (SLC) operation in the data region. (2) … Assigning key values with different bit depths to each cell, we modulate the activation time according to the bit depths. The linearity between activation time and the number of multi block accesses allows bit depth representation."
- "demonstrated approximate search with sufficient accuracy using 3-bit and 128-dimensional data … energy consumption is significantly reduced when compared to the normal TLC read operation, and no additional WL control circuit is required."

**IMW 2026 figure captions** — [IEEE Xplore 11532787](https://ieeexplore.ieee.org/document/11532787)
- Fig. 1(c): "activation time of WL and the change in BL voltage".
- Fig. 4: "Vth distribution of the CC cell (a), and the cumulative probability of sensing time (b)".
- Fig. 5: "BL voltage drop is obtained as the inverse of the activation time (a). It increases linearly with the number of activated blocks (b)."
- Fig. 6: CC cell placed "at WL of the source side, middle of strings, or BL side".
- Fig. 7: effect of the adjacent cell being Er or A level.
- Fig. 8: waveforms for query values Q_d = 7, 1, 0.
- Figs. 10–11: 3-bit, 128-dimensional experimental results.

**Kioxia's public schematic for 2026** (topic-93 Fig. 1) — [Kioxia topic-93 Fig.1](https://www.kioxia.com/content/dam/kioxia/ja-jp/rd/technology/topics/img/topics-93_img_001.png)
- Encoding: key = 5 (101b) is stored one bit per block (BLK1 = MSB … BLK3 = LSB) on one bitline.
- Each block's WLs are activated for a duration of query value × bit weight. For query = 1 the pulses are ×4, ×2, ×1; for query = 7 they are ×28, ×14, ×7.
- The pulses are sequential and non-overlapping ("Activation-Time-Modulated Sequential Block Access"), and a single S/A sits at the end of the bitline.
- Kioxia's text: "The query data is applied to the selected word line as activation time."

**2026 result** (topic-93 Fig. 2) — [Kioxia topic-93 (EN)](https://www.kioxia.com/en-jp/rd/technology/topics/topics-93.html); [Fig.2 image](https://www.kioxia.com/content/dam/kioxia/ja-jp/rd/technology/topics/img/topics-93_img_002.png)
- Kioxia: "it is possible to select an inner product less than or equal to 49 with a probability of more than 99 percent. The target inner product is controlled by the selected word-line voltage of the CC cell, and the unit activation time of the word line, T_act."
- The figure plots cumulative probability against T_act (≈0.1–1000 µs) for IP = 0, 1, 2, 7, 14, 21, 49, 98, 147, 392, 784, 1568 and 6272, with a dotted threshold line near 1 µs.
- Kioxia's workflow: the flash extracts candidates in parallel across many bitlines, then "on the host side, the most similar data are determined from the extracted candidates … by majority voting."

**Precursor work by the same team** (Hasegawa et al., IMW 2023) — [IEEE Xplore 10145971](https://ieeexplore.ieee.org/document/10145971)
- Title: "Low Power and Thermal Throttling-less SSD with In-Package Boost Converter for 1000-WL Layer 3D Flash Memory". Authors include Aiba and Sanuki.
- "we fabricated a 3D flash memory with an in-package boost converter to replace the on-die charge pump circuit". Captions show a boost "from 3.3 V to 12 V", TLC Vth distributions, and operation "with one block … two blocks … and four blocks".
- The 2025 paper cites this work as the basis for supplying Vpp externally — [Kioxia topic-85](https://www.kioxia.com/en-jp/rd/technology/topics/topics-85.html).

**Coverage, citations and references**
- I found no independent press coverage of either paper. A PC Watch preview of IMW 2026 does not mention the Kudo talk — [PC Watch IMW2026 preview](https://pc.watch.impress.co.jp/docs/column/semicon/2106492.html).
- OpenAlex shows 1 citation of the 2025 paper and lists it as not open access — [OpenAlex record](https://api.openalex.org/works/doi:10.1109%2FIMW61990.2025.11026979).
- The 2025 reference list cites Gonugondla (ISCAS 2018), H.T. Lue (IEDM), P.H. Tseng (IMW 2024, Macronix filtering cube), Hasegawa (IMW 2023) and Sasaki (NEWCAS 2024) — [IEEE Xplore 11026979](https://ieeexplore.ieee.org/document/11026979).

### Inferences

**Silicon** [INFERENCE]
- No public source names the die (BiCS generation, layer count, product vs test chip).
- Clues:
  - The lead author's affiliation is the product "Memory Div."
  - A full 128k-bitline page was measured, which suggests a product-class die with full page buffers.
  - The SLC data region was tested against "normal TLC read".
  - Vpp was supplied externally at nominal 12 V, and Vcc was 3.3 V nominal.
- The likeliest reading: a standard Kioxia 3D-flash array and periphery driven by internal (non-public) test/control sequences, with an external Vpp pad as in the IMW 2023 setup.
- "No additional WL control circuit is required" means the WL drivers were not redesigned. It does not mean a stock command set can reach this mode. No public Kioxia datasheet exposes block-sequenced multi-block activation, CC-cell WL bias, Vread scaling or sense-time control.

**Sequential vs simultaneous** [INFERENCE from the captions and Kioxia schematics]
- Strings on one BL are not conducting at the same instant. Each block's on-strings discharge the precharged BL in turn, and the BL capacitance integrates charge = Σ (I_CC × t_act).
- That is Kirchhoff summation in time (charge-domain accumulation), not a parallel current sum of many strings.
- Parallelism comes from many bitlines (~128k) computing different key vectors at once.

**Readout** [INFERENCE]
- The output is a binary S/A decision at a programmable sense or activation time.
- A numerical IP was obtained by sweeping T_SEN or T_act (or the CC-cell WL voltage) and recording the flip point across 128k BLs (cumulative-probability plots).
- So it is time-domain quantisation by repeated sensing, not an on-die ADC. Each sense gives about 1 bit (above or below a target IP). The 2026 operating point is a threshold classifier ("IP ≤ 49") used to extract candidates.
- IEEE's auto-generated index terms for the 2025 paper include "Analog-to-digital Converter". This hints that the paper discusses ADC overhead, probably as something avoided; unverified because the full text is paywalled.

**Capability mapping** [INFERENCE]
- Demonstrated by Kioxia internally: WL bias control (1); per-block selection on one BL in time sequence (2); current summation via the CC cell plus BL charge integration, but sequential (3).
- Not demonstrated publicly: access to the analog sum (4). The only output is the S/A result. For (5), conversion is via sense timing or reference shifts.

### Gaps
- Full text, figure images and exact numbers (BL capacitance, I_CC value, T_SEN definition, block count per run, error rates) are in the paywalled IEEE PDFs. I did not access them.
- Not disclosed in any public source: the BiCS generation or die; whether the sequences used a hidden test mode, modified firmware or a probe station; the instrument used to collect S/A results; whether any peripheral circuit was modified.
- IMW 2026 slides, video or poster: not found. The IMW 2026 program PDF has been taken down (404). Wayback access was blocked from this environment.
- No Kioxia press release, beyond the two Technology Topics pages, was found for either paper.

---

## Q2. Related Kioxia / Toshiba Memory patents (inner product / MAC / multi-string current summation / search on NAND strings)

### Takeaway
USPTO full-text search (Patent Public Search) found a cluster of Kioxia filings from 2022–2025 on NAND-string inner-product and search operations.
- Several propose **simultaneous** conduction of multiple strings on one bitline with current summation and S/A sensing: Fukumura, Kawasumi, Komano, Sasaki and Enda.
- One proposes multi-WL search within a single string: Sanuki.

All are **[PATENT]** proposals, which require new control-circuit operating modes. None claims that a shipping product exposes these modes. I found **no** published US patent matching the CC-cell / sequential multi-block / activation-time scheme of the IMW papers, searching inventors Kudo, Aiba, Hasegawa, Li, Sano and Sanuki and the phrase "current control cell".

### Cited Findings

**US 12,562,221 B2** "Memory device configured to perform a search operation" — [USPTO PDF](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12562221)
- Kioxia; inventors Sanuki, Tomoya et al. Priority 2023-03-07; filed 2024-02-26; granted 2026-02-24. Pre-grant publication US 2024/0304239 A1.
- Claim 1: a control circuit "supplies voltages to a plurality of word lines respectively corresponding to the plurality of first memory cells based on the search data, and determines a similarity … based on a change in voltage of the bit line caused by current flowing between the bit line and the source line via the first string".
- Claim 1 also recites a normal read in which "a difference between the second read voltage and the source voltage is less than a difference between the first read voltage and the source voltage" (verbatim).
- Claim 3: complementary cell pairs (2k, 2k+1); one cell is OFF when stored data equals the search data.
- Topology: **multiple WLs inside one series string** (search/match), not summation across strings. Needs a new sense/search mode.

**US 2025/0299735 A1** "Semiconductor device and storage medium" — [USPTO PDF](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/20250299735)
- Kioxia; inventors Enda, Toshiyuki et al. JP priority 2024-03-21; filed 2025-03-10; published 2025-09-25.
- Claim 1: in a "logical operation", apply "a first voltage to the select transistors of **at least two strings**" on one bit line, a lower voltage to the other strings' select transistors, and a read voltage to at least two cells of each string (Vread to the rest).
- The description has the sense-amplifier unit latching whether "cell current Icell has flown in at least one NAND string", with XOR/XNOR built from sequential reads.
- Topology: multiple independently selected strings on one BL conducting **simultaneously**, but evaluated as a **binary wired-OR** current/no-current decision. Needs a new control-circuit mode.

**US 2026/0253637 A1** "Information processing apparatus and information processing system" — [USPTO PDF](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/20260253637)
- Kioxia; inventors Fukumura, Kotaro et al. Priority 2025-02-25; filed 2025-12-15; published 2026-08-27.
- Claims: strings whose transistor Vth is set by data 1 and whose gates take a voltage from data 2. Claim 2: "a sum of the current flowing through each of the plurality of strings flows through the first wiring as the inner product value". Claims 8–9: "inner product value … is obtained by a **one-time current** flowing through the plurality of strings".
- Description: "an example of using the string 1 of the NAND flash memory will be mainly described"; "All currents flowing through four strings 1 of the same block flow through a corresponding bit line … The sense amplifier determines whether a key and a query match based on the current flowing through each bit line."
- Topology: **simultaneous** multi-string current sum on one BL, n² strings for sparse vectors with n valid values, with a match/threshold decision at the S/A.

**US 2026/0169914 A1** "Information processing apparatus and memory system" — [USPTO PDF](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/20260169914)
- Kioxia; inventors Kawasumi, Atsushi et al. Priority 2024-12-17; filed 2025-09-11; published 2026-06-18.
- A string with complementary Vth pairs and complementary gate potentials: an XNOR-style product per cell pair within a string.

**US 12,315,566 B2** "Information processing device and memory system" — [USPTO PDF](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12315566)
- Kioxia; inventor Kawasumi. Priority 2022-08-31; filed 2023-03-15; granted 2025-05-27. Pre-grant publication US 2024/0071499.
- "first transistor having a threshold voltage corresponding to a first data, the second transistor … resistance value … corresponding to a second data … A current corresponding to a product of the first data and the second data flows through the string."

**US 2024/0427843 A1** "Information processing apparatus and memory system" — [USPTO PDF](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/20240427843)
- Kioxia; inventor Kawasumi. Priority 2023-06-22; filed 2024-06-14.
- A wiring line carries "a sum of currents each corresponding to a product of" (reference − k_i) × q_i; "a sense amplifier configured to sense a voltage on the wiring line; and a similarity detection circuit".
- Description: "The transistors in each string are, for example, NAND memory cell transistors"; "A current corresponding to the sum of currents flowing through the strings SR0 to SRm flows through the bit line BL."

**US 2026/0237442 A1** "Information processing apparatus and memory system" — [USPTO PDF](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/20260237442)
- Kioxia; inventor Komano, Yusuke. Priority 2025-02-10; filed 2025-12-11; published 2026-08-13.
- Two strings share one wiring line, with switching controllers that "control currents flowing through the first portion and the third portion" and the resistance of the other portions.
- Description: "a CIM that performs a multiply-accumulate operation by using a memory cell array of a non-volatile memory such as a NAND flash memory … in the CIM, a plurality of word lines is simultaneously selected"; the string current is proportional to an overdrive-voltage-encoded product.

**US 12,762,154 B2** "Information processing apparatus" — [USPTO PDF](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12762154)
- Kioxia; inventor Sasaki, Shinichi. Priority 2024-03-04; filed 2024-09-12; granted 2026-10-13. Pre-grant publication US 2025/0278413 A1.
- Claim 1: storage in which "each of the plurality of first wirings outputs a voltage level corresponding to an inner product value".
- Description: "The nonvolatile memory is, for example, a NAND flash memory"; "each bit line supplies a voltage corresponding to a signal obtained by performing wired-OR on the multiplication result"; "a plurality of strings SR1 to SRn are connected to one bit line".
- The claimed novelty is mainly the clustering (balanced soft clustering) that matches the NEWCAS 2024 paper.

**Older Toshiba Memory digital near-memory MAC patents** (not analog in-array)
- US 10,332,594 B2 (Miyashita et al.; priority 2017-09-20): read-circuit array → wide bus → multiply-accumulate operator array — [USPTO PDF](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10332594).
- US 10,802,799 B2 (Miyashita): plural multiplier/accumulator circuits — [USPTO PDF](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/10802799).

**Non-NAND Kioxia CIM patents**
- US 11,615,834 B2 (Kawasumi): wiring-pair ternary/binary product–sum, with no NAND strings described in the claims — [USPTO PDF](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11615834).
- US 2025/0299709 A1 (Kawasumi): sense amplifiers plus switches to an accumulation line — [USPTO PDF](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/20250299709).

### Inferences
[INFERENCE]
- Kioxia's patent work on **simultaneous** multi-string summation (Fukumura, Kawasumi, Komano, Enda) is broader than its **published silicon**, which uses **sequential** block activation (Kudo 2025/2026).
- A plausible reason: the CC cell plus sequential activation avoids the drawbacks of selecting many strings at once (BL IR drop, saturation, peak current, select-gate/WL drive), at the cost of time.
- Every patent describes new control-circuit behaviour: multi-string select, multi-WL search biasing, or time-modulated WL pulses. None should be taken as evidence that a commercial Kioxia part accepts such commands.
- Most descriptions keep a **binary S/A decision** ("match", "similarity detection", "wired-OR"). Numerical resolution comes from thresholds or repeated sensing, not an in-die ADC.

### Gaps
- No US publication was found for the CC-cell / sequential multi-block / activation-time-modulation scheme itself. It may exist as a JP application not yet published or not yet filed in the US, or under other inventor names.
- J-PlatPat, WIPO Patentscope, Espacenet, Google Patents and Justia were not reachable from this environment: rate limits (503), 403 blocks, or JS-only pages. JP/CN/KR/WO family members were therefore not checked.
- I did not inspect patent figures, only claims and text.

---

## Q3. Other Kioxia / Toshiba CIM or "memory-centric AI" publications and university collaborations

### Takeaway
Besides the two IMW papers, Kioxia's NAND-level CIM output found here is one item: a NEWCAS 2024 ANNS paper on "standard 3D flash memory" (binary inner-product top-k). Its experimental basis, silicon or simulation, is unclear from the public abstract and captions. Kioxia's other "memory-centric AI" work operates at the SSD/system level: XL-FLASH LSH search and RAG frameworks. I found no Kioxia–university paper measuring commercial NAND for inner-product computation.

### Cited Findings

**NEWCAS 2024 ANNS paper** — [IEEE Xplore 10666332](https://ieeexplore.ieee.org/document/10666332)
- Sasaki, Aiba, Komano, Iizuka, Fujimatsu, Kawasumi, Miyashita, Deguchi, Maeda, Miyano, Maruyama (Kioxia, Yokohama). "Mitigation of Accuracy Degradation in 3D Flash Memory Based Approximate Nearest Neighbor Search with Binary Tree Balanced Soft Clustering for Retrieval-Augmented AI", 2024 IEEE NEWCAS, pp. 238–242, DOI 10.1109/NewCAS58973.2024.10666332.
- Abstract: "we propose techniques to realize CIM using a standard 3D flash memory for approximate nearest neighbor search (ANNS) … achieved top-1 accuracy of 77.7%" on ImageNet-1k.
- Fig. 1 caption: "Binary inner product (BIP) top-k extraction architecture using the standard 3D flash memory". Fig. 4 caption: "Experimental setup".
- It shares authors and concepts with US 12,762,154 B2 (above).

**Kioxia system-level "AI/search" topics (not die-level)**
- E2LSH on Storage, using an XL-FLASH demo drive (EDBT 2023) — [Kioxia topic-46](https://www.kioxia.com/en-jp/rd/technology/topics/topics-46.html).
- Topic list including "Accessible Frameworks for … Memory-centric AI through Retrieval-Augmented Large Language Model" (topic-58) and "Image Classification System Deploying Memory-Centric AI with High-capacity Storage" (topic-39) — [Kioxia Technology Topics index](https://www.kioxia.com/en-jp/rd/technology/topics.html).

**Same team's earlier silicon work** (cryogenic and multi-bit-per-cell measurements on Kioxia 3D flash; shows the group's measurement capability)
- Aiba et al., IMW 2021 "Bringing in Cryogenics to Storage…" — [IEEE 9439594](https://ieeexplore.ieee.org/document/9439594).
- Tanaka et al., IMW 2022 "Toward 7 Bits per Cell…" — [IEEE 9779301](https://ieeexplore.ieee.org/document/9779301).

**University and industry ties**
- Kioxia's public academic-collaboration page lists Waseda University (2018 agreement), the University of Electro-Communications (2019, AI and semiconductor memory), MIT Media Lab and MIT (SSD-based data work), and the annual "KIOXIA 奨励研究" research grant. The FY2026 call is marked closed. No CIM or NAND-test-chip program is mentioned — [Kioxia 産学連携 (JA)](https://www.kioxia.com/ja-jp/rd/collaboration.html); [Academic Collaboration (EN)](https://www.kioxia.com/en-jp/rd/collaboration.html).
- FY2025 grant award winners were from the University of Tokyo (ISSP), NAIST and Tokyo University of Science; the topics were not NAND CIM — [Kioxia FY2025 award page](https://www.kioxia.com/ja-jp/rd/collaboration/award-fy2025.html).
- Kioxia joined Applied Materials' EPIC Center (announced Sept 29, 2026) to research memory cells, stacking, packaging and materials; in-memory computing is not mentioned — [Mynavi TECH+](https://news.mynavi.jp/techplus/article/20261001-5052442/).

### Inferences
[INFERENCE]
- Kioxia's die-level IMC research sits within the Frontier Technology R&D Institute and Memory Division group of Sanuki and Aiba (IMW 2025/2026), with a systems/algorithm group (Sasaki, Miyashita, Deguchi, Kawasumi) working in parallel.
- There is no sign of an external university measuring Kioxia NAND for CIM.

### Gaps
- Whether the NEWCAS 2024 "experimental setup" is real silicon or simulation is unclear (paywalled).
- Searches for Takeuchi-lab (Chuo / University of Tokyo) CIM measurements on Kioxia or Toshiba commercial NAND found only a 2017 IEDM "data-aware NAND for DNN" reliability paper (abstract not verified), not an inner-product demonstration.
- No J-STAGE or 東芝レビュー / Kioxia technical-review article on NAND CIM was found.
- Japanese trade-press searches (PC Watch, EE Times Japan, Mynavi) found no coverage of the Kudo papers.

---

## Q4. Public Kioxia / Toshiba raw-NAND datasheets: documented commands, and current purchasability

### Takeaway
The public Kioxia/Toshiba SLC parallel-NAND datasheets reviewed (BENAND TC58BVG0S3HTAI0 and TC58BVG1S3HTA00, plus raw TC58NVG2S0HTA00) document only conventional commands. None has Set/Get Features, read-retry/shift-read prefixes, or any WL-voltage or sense-time control. The 4 Gb part documents a two-"District" Multi Page Read that explicitly allows **at most one block per District**. Kioxia's own datasheet and SLC product URLs now redirect to a generic memory page, and Kioxia SLC NAND is being discontinued: distributors show "Obsolete", and downstream EOL notices cite last-time-buy dates in mid/late 2026.

### Cited Findings

**TC58BVG0S3HTAI0** (1 Gbit, 3.3 V, BENAND = on-chip ECC, 8 bits per 528 bytes), datasheet dated 2019-10-01C, "© 2012-2019 KIOXIA" — [Digi-Key-hosted Kioxia datasheet](https://media.digikey.com/pdf/Data%20Sheets/Toshiba%20PDFs/KIOXIA_TC58BVG0S3HTAI0_REV2.00_E20191001C.pdf)
- Feature list "Modes: Read, Reset, Auto Page Program, Auto Block Erase, Status Read, Page Copy, ECC Status Read" (p. 1).
- Table 3, Command table (HEX), p. 22. Commands as listed:

  | Operation | Bytes |
  |---|---|
  | Serial Data Input | 80 |
  | Read | 00–30 |
  | Column Address Change in Serial Data Output | 05–E0 |
  | Auto Page Program | 80–10 |
  | Column Address Change in Serial Data Input | 85 |
  | Read for Copy-Back | 00–35 |
  | Copy-Back Program | 85–10 |
  | Auto Block Erase | 60–D0 |
  | ID Read | 90 |
  | Status Read | 70 |
  | ECC Status Read | 7A |
  | Reset | FF |

- ECC Status Read timing diagram on p. 10: "ECC Status output should be read for all 4 sector information."

**TC58BVG1S3HTA00** (2 Gbit BENAND), same 2019-10-01C revision — [Digi-Key-hosted Kioxia datasheet](https://media.digikey.com/pdf/Data%20Sheets/Toshiba%20PDFs/KIOXIA_TC58BVG1S3HTA00_REV2.00_E20191001C.pdf)
- The command table (PDF p. 25) adds Multi Page Program 80–11 / 81–10 and "Status Read for Multi-Page Program or Multi Block Erase" 71. Otherwise it matches the 1 Gb part.
- No Set/Get Features, cache read or read-retry.

**TC58NVG2S0HTA00** (4 Gbit raw SLC, 4352-byte page, 2048 blocks)
- The copy reviewed is the Toshiba Memory revision 2018-12-14C, a distributor mirror of the official sheet; I could not obtain a Kioxia-hosted current revision — [LCSC/Flux mirror](https://storage.googleapis.com/graviton-electric-symbols/document_assets/lcsc/1912111437_KIOXIA-TC58NVG2S0HTA00_C438944.pdf).
- Modes include "Multi Page Program, Multi Block Erase, Multi Page Copy, Multi Page Read".
- Table 3 (p. 30) additionally lists Read with Data Cache 31, Read Start for Last Page with Data Cache 3F, Auto Page Program with Data Cache 80–15, Multi Page Program 80–11/81–15/81–10, Read for Page Copy (2) with Data Out 00–3A, page-copy program 8C–15/8C–10, and 71.
- Multi Page Read (pp. 33–35): sequence 60–addr–60–addr–30, then 00–addr–05–addr–E0 per District. "The device consists of 2 Districts", with even blocks in District 0 and odd blocks in District 1. Restriction: "**Maximum one block should be selected from each District**", and the same page address is required in both.
- No Set/Get Features or read-retry appears in the command table.

**Serial (SPI) SLC NAND TC58CVG1S3HRAIJ** (2 Gbit, 3.3 V, WSON8)
- A search-engine excerpt of Kioxia's 2019 datasheet states it has "Set Feature (1Fh)" and "Get Feature (0Fh)" and that after "Read Cell Array (13h), Get Feature (0Fh) reads the status (OIP, ECCS0 and ECCS1 bits)". I could not open the document to verify: the Kioxia URL now redirects to the memory top page — [Kioxia URL (now redirects)](https://europe.kioxia.com/content/dam/kioxia/newidr/productinfo/datasheet/201910/DST_TC58CVG1S3HRAIJ-TDE_EN_36002.pdf).
- On SPI NAND these feature registers handle status, ECC and protection. Nothing indicates analog or WL control [INFERENCE].

**Datasheet removal from Kioxia's site**
- As of 2026-10-17, Kioxia-hosted datasheet URLs and the SLC NAND product page redirect to the general memory page: kioxia.com/…/DST_TC58NVG0S3HTA00…pdf, which search results showed as a 2025-01-15C revision; americas.kioxia.com/en-us/business/memory/slc-nand.html; and the Europe datasheet links (checked with curl; effective URL = …/business/memory.html) — [example dead datasheet URL](https://www.kioxia.com/content/dam/kioxia/newidr/productinfo/datasheet/202502/DST_TC58NVG0S3HTA00-TDE_EN_31435.pdf).

**Discontinuation and availability**
- Delkin EOL notice 412-0114-00 (Apr 29, 2026): "Due to the discontinuation of Kioxia SLC NAND flash components … supply of SLC NAND is highly constrained"; LTB 06/30/26, last ship 12/17/28 (for Delkin's own SD cards) — [Delkin EOL PDF](https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/8921/EOL_412-0114-00%20_RevA.pdf).
- A distributor blog citing "Kioxia's TSOP EOL notice (Ref. HQ-SBD0315KAI)" gives LTB September 15, 2026 and last-time-ship March 15, 2027 for TC58BVG1S3HTAI0, TC58BVG0S3HTAI0 and TC58NVG1S3HTAI0. This is a secondary source; I did not see the Kioxia notice itself — [Win-Source blog](https://blog.win-source.net/tutorials/tc58xvg-series-slc-nand-selection-guide-1gb-or-2gb-1-8v-or-3-3v/).
- Digi-Key, fetched 2026-10-17:
  - TC58NVG1S3HTA00: "Obsolete and no longer manufactured". Suggested substitute TC58BVG1S3HTAI0, 32 in stock at $4.34 — [Digi-Key TC58NVG1S3HTA00](https://www.digikey.com/en/products/detail/kioxia-america-inc/TC58NVG1S3HTA00/5226320).
  - TC58CVG0S3HRAIJ (1 Gb SPI): "Obsolete"; suggested substitute Winbond W25N01GVZEIG TR — [Digi-Key TC58CVG0S3HRAIJ](https://www.digikey.com/en/products/detail/kioxia-america-inc/TC58CVG0S3HRAIJ/11609599).
- Mouser lists TC58NVG1S3HTAI0 as "End of Life" according to a search snippet; the page itself returned 503 to the fetch tool — [Mouser listing](https://www.mouser.com/ProductDetail/Kioxia-America/TC58NVG1S3HTAI0?qs=T3IxTwwp%2B0tSagI4Fxc%2B2g%3D%3D).

### Inferences
[INFERENCE]
- Through documented commands, none of these public parts offers:
  - (1) a WL bias setting;
  - (2) selection of several blocks or strings on the same BL at once (the 4 Gb Multi Page Read selects one block per District/plane, and District 0 and District 1 hold different blocks with separate page registers);
  - (4) analog access;
  - (5) reference or sense-time trimming (no Set/Get Features or read-retry on the parallel SLC parts).
- These 24 nm-class planar SLC parts are also not the 3D BiCS silicon used in the IMW papers.
- Small quantities of BENAND remain purchasable in late 2026 (e.g., 32 pcs at about $4.34), but the line is ending.

### Gaps
- Not obtained: a current Kioxia-hosted revision of any TC58NVG/TC58CVG datasheet, the TC58CVG serial-NAND command and feature tables (only search excerpts), and the Kioxia primary EOL notice (HQ-SBD0315KAI).
- Current Mouser pricing was not captured (503).
- I did not check whether any Kioxia BiCS-generation raw-NAND datasheet is public. None appeared, and Kioxia's BiCS datasheets are normally distributed under NDA, so I did not pursue them.

---

## Q5. Toshiba / Kioxia sense-amplifier and bitline-sensing circuits: could internal sensing act as an ADC?

### Takeaway
The public Toshiba and Toshiba/SanDisk literature describes the following, all built for fast binary or multi-level reads, not for exporting an analog value:
- shielded-bitline voltage sensing (Toshiba, 1994);
- the switch to all-bit-line (ABL) current sensing (SanDisk, the Toshiba JV partner, 2008–09);
- shielded-BL current sensing on BiCS (2017);
- small-swing WL control for read energy (Kioxia/WD, 2025).

Kioxia's own IMC papers show the practical way to get numbers out of these sense amplifiers: sweep the sense or activation time (and WL references) and record the flip point.

### Cited Findings

**Tanaka et al. (Toshiba), JSSC Nov 1994** — [IEEE 328638](https://ieeexplore.ieee.org/document/328638)
- "A quick intelligent page-programming architecture and a shielded bitline sensing method for 3 V-only NAND flash memory".
- The shielded bitline sensing method reduces "bitline-bitline capacitive coupling noise from 700 mV to 35 mV … 2.5-µs random access time with a 2.7-V power supply."

**Cernea et al. (SanDisk NAND Design), JSSC Jan 2009** — [IEEE 4735566](https://ieeexplore.ieee.org/document/4735566)
- "A 34 MB/s MLC Write Throughput 16 Gb NAND With All Bit Line Architecture on 56 nm Technology".
- "The newly introduced All Bit Line (ABL) architecture … was made possible by adopting the 'current sensing' (as opposed to the mainstream 'voltage sensing') technique."
- Captions include "ABL: current sensing for faster verify" and "ABL sensing: energy saving".

**Yamashita et al. (Toshiba/WD), ISSCC 2017 11.1** — [IEEE 7870328](https://ieeexplore.ieee.org/document/7870328)
- "A 512Gb 3b/cell flash memory on 64-word-line-layer BiCS technology".
- Implements "(1) four-block even-odd-combined row decoding … (2) unselected string pre-charge operation … (3) shielded BL current sensing to enhance read throughput".
- Captions: "4 Strings in a block and USP sequence"; "FBC vs BL settling time".

**Yanagidaira et al. (Kioxia/WD), ISSCC 2025** — [IEEE 10904509](https://ieeexplore.ieee.org/document/10904509)
- "A 1Tb 3b/cell 3D-Flash Memory with a 29%-Improved-Energy-Efficiency Read Operation and 4.8Gb/s Power-Isolated Low-Tapped-Termination I/Os".
- "high read performance via small-voltage-swing WL control"; caption "Reduced WL voltage swing: (a) operational waveforms, (b) tREAD′ (c) energy".

**Kioxia IMC readouts** (as in Q1) — [IEEE 11026979](https://ieeexplore.ieee.org/document/11026979); [IEEE 11532787](https://ieeexplore.ieee.org/document/11532787)
- Reported as "sense time (T_SEN) and cumulative probability for 128 k … BLs", "T_SEN versus the WL voltage of the CC cell", and "cumulative probability of sensing time".

### Inferences
[INFERENCE]
- A BiCS block holds several strings per BL, selected by separate SGD lines (4 strings per block on 64L BiCS). Many blocks share each BL. So the array topology for summing strings on one BL exists physically. Product logic, though, selects one block and one string unit per plane.
- ABL current sensing integrates cell current on a sense node for a set time and compares it to a trip point. Used as an "ADC", it is a 1-bit comparator per strobe.
- About 6–10 bits would need 2^n time strobes or reference steps (or a binary search via repeated reads). The time-to-flip spread in Kioxia's own data, cumulative distributions spanning ×1.5–2 per IP level, also limits resolution. The 2026 multi-level demonstration resolves coarse IP classes (thresholding IP ≤ 49 out of a 0–6272 range), not 6–10-bit values.

### Gaps
- I did not retrieve full-text Toshiba/Kioxia ISSCC papers describing sense-node capacitance, strobe-time granularity, or whether sense time is user-programmable. Public product datasheets expose no sense-time control (Q4).

---

## Q6. Legitimate access routes: evaluation, collaboration or research-contact programs

### Takeaway
I found **no** public Kioxia evaluation or test-chip program for in-memory computing or raw NAND characterisation. The public routes that exist:
- the academic-collaboration framework (Waseda, UEC agreements);
- the annual KIOXIA 奨励研究 grant for researchers at Japanese academic institutions;
- the business-product inquiry channel;
- contacting the IMW authors directly.

### Cited Findings
- Kioxia's academic-collaboration page lists tie-ups (Waseda 2018; UEC 2019, covering "AI-based production technology and semiconductor memory"), joint research with MIT, and the annual KIOXIA 奨励研究 grant. The 2026 call is shown as "終了しました" (closed). No hardware-access program is described — [Kioxia 産学連携](https://www.kioxia.com/ja-jp/rd/collaboration.html); [Academic Collaboration (EN)](https://www.kioxia.com/en-jp/rd/collaboration.html).
- OpenAlex lists Kana Kudo as the corresponding author of the 2025 IMW paper — [OpenAlex record](https://api.openalex.org/works/doi:10.1109%2FIMW61990.2025.11026979).
- The 2026 paper's affiliation is Frontier Technology R&D Institute / Memory Div., Kioxia Corporation — [IEEE 11532787](https://ieeexplore.ieee.org/document/11532787).
- Kioxia's public site routes "technical questions, document requests, samples and purchases" for business products through its corporate contact page. This appears as boilerplate on Kioxia's Japanese memory pages (observed while fetching the pages above), e.g. [Kioxia memory page (JA)](https://www.kioxia.com/ja-jp/business/memory.html).

### Inferences
[INFERENCE]
- The realistic legitimate paths are:
  - (a) a research collaboration proposal to the Frontier Technology R&D Institute via the IMW corresponding author, or a joint-research agreement for a Japanese university group;
  - (b) applying to KIOXIA 奨励研究 (funding, not silicon) when the next call opens;
  - (c) a business inquiry for BiCS samples and datasheets, which would normally come under NDA. Note: material obtained under NDA could not be used in public reporting.
- Nothing indicates the special sequences used in the IMW papers are available outside Kioxia.

### Gaps
- I found no public statement on whether Kioxia shares test-mode-enabled samples with external researchers.

---

## Q7. Synthesis: does Kioxia/Toshiba evidence show a commercially manufactured NAND die computing y = Σ wᵢxᵢ through existing circuitry with ~6–10-bit numerical readout?

### Takeaway
**Partially, and only inside Kioxia.**
- Kioxia's IMW 2025/2026 papers are the closest real-silicon evidence from any vendor's own team. They compute a 1-bit (2025) and 3-bit (2026) × 128-dimension inner product on what Kioxia calls conventional-compatible 3D flash with "no additional WL control circuit".
- The method uses **sequential** block activation with charge integration on the bitline, **not** simultaneous parallel string-current summation.
- Results come out as **threshold decisions** from the on-chip S/A at swept sense or activation times, not as a 6–10-bit number.
- The sequences rely on non-public control: external Vpp, scaled Vread/Vcc, CC-cell WL bias, and time-modulated multi-block activation.
- No public Kioxia/Toshiba datasheet exposes any of capabilities (1)–(5).

### Cited Findings
**(1) WL bias control**
- Demonstrated internally: query applied as WL voltage (2025) or as WL activation time (2026); CC-cell WL voltage tuned; Vread lowered 9 → 3 V — [IEEE 11026979](https://ieeexplore.ieee.org/document/11026979); [Kioxia topic-93](https://www.kioxia.com/en-jp/rd/technology/topics/topics-93.html).
- Not in public datasheets — [TC58BVG0S3HTAI0 datasheet](https://media.digikey.com/pdf/Data%20Sheets/Toshiba%20PDFs/KIOXIA_TC58BVG0S3HTAI0_REV2.00_E20191001C.pdf).

**(2) Independent block/string selection on one BL**
- Demonstrated as sequential block activation on one BL: 8 blocks (8-dim) and placements for m = 4 or 128 — [IEEE 11026979](https://ieeexplore.ieee.org/document/11026979).
- Simultaneous multi-string selection appears only in patents — [US 2025/0299735](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/20250299735); [US 2026/0253637](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/20260253637).
- Public Multi Page Read permits only one block per District — [TC58NVG2S0HTA00 mirror](https://storage.googleapis.com/graviton-electric-symbols/document_assets/lcsc/1912111437_KIOXIA-TC58NVG2S0HTA00_C438944.pdf).

**(3) Current summation of 2..128 strings on one sense node**
- Achieved as time-sequential accumulation over up to 128 blocks; "BL voltage drop … increases linearly with the number of activated blocks" — [IEEE 11532787](https://ieeexplore.ieee.org/document/11532787).

**(4) Access to the summed analog signal**
- Not reported. Outputs are S/A results; analysis is by cumulative probability of T_SEN/T_act across 128k BLs — [IEEE 11026979](https://ieeexplore.ieee.org/document/11026979).

**(5) Numerical conversion**
- Via sweeping T_SEN or T_act and the CC-cell WL voltage; 3-bit-key IP thresholding at IP ≤ 49 with >99% probability — [Kioxia topic-93](https://www.kioxia.com/en-jp/rd/technology/topics/topics-93.html).

### Inferences
[INFERENCE]
- To replicate on purchasable parts, someone would need, at minimum: a per-block WL bias/timing sequencer, CC-cell biasing, and fine sense-time control. None is available on current public Kioxia SLC datasheets, and those parts are planar SLC being discontinued.
- Kioxia's "fully compatible with conventional 3D flash" claim should be read as "no new array or WL-driver hardware", not "accessible via the standard command set".

### Gaps
- Unresolved: the exact die, the control path used for the measurements, any modification of peripheral or firmware logic, and whether simultaneous multi-string summation was ever measured by Kioxia (no publication found).
