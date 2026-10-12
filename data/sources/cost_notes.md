# Cost and GPU-performance notes for the Kimi K3 feasibility study

Compiled 2026-10-12. Every number here also appears, with its citation, date and evidence class, in one of these files:

- `cost_parameters_sourced.csv` (115 rows): memory, foundry, NRE and power parameters
- `gpu_systems_sourced.csv` (19 rows): accelerator and system specs and prices
- `llm_decode_benchmarks_sourced.csv` (99 rows): measured decode speeds

Row ids such as N01 and C06 refer to `cost_parameters_sourced.csv`.

Raw downloads and parsing scripts are in the session scratchpad, not in the repo:

- `research_cost/dl_inferencex/bench_*.json` holds the InferenceX API dumps that the benchmark rows were generated from.
- The extracted text of the MLPerf rules file is also there.

## 0. Read this first: 2026 is a memory-shortage year

Memory prices in Q3/Q4 2026 are 7 to 13 times their mid-2025 levels:

| Item | Mid-2025 | 2026 | Rows |
|---|---|---|---|
| 512Gb TLC NAND wafer spot | US$2.707 (Jun 2025) | US$19.40 (Sep 28 2026), after peaking around US$23 in Mar 2026 | N05, N01, N04 |
| DDR5 16Gb chip spot | US$6.01 (Jun 2025) | US$59.07 (Oct 12 2026) | D02, D01 |
| DDR4 8Gb chip spot | US$3.31 | US$42.50 | D06 |

TrendForce has contract prices still rising in 4Q26 (NAND +15-20%, DRAM +10-15% QoQ; N08, D07), and analysts expect the tightness to last into 2027-2028.

A feasibility model should therefore carry two price scenarios:

- **Shortage (now):** the 2026 numbers above.
- **Normalized:** the mid-2025 numbers. For NAND, these were roughly at manufacturing cost; Gartner estimated Micron 232L cost at 5-7 cents/GB (N28).

## (a) What 1.6 TB of NAND costs

Kimi K3's MXFP4 checkpoint is 1.56 TB (K02, vLLM recipe). The table uses 1,600 GB.

| Basis | 1.6 TB cost (USD) | Date | Row |
|---|---|---|---|
| TLC wafer spot (raw dies, no package/controller) | 430 to 550, typ 485 ($0.30/GB) | 2026-09-28 | C01 |
| TLC wafer spot, pre-shortage | about 68 ($0.042/GB) | 2025-06-11 | C02 |
| Phison-quoted 1Tb TLC chip ($4.80 to $10.70) | 60 to 134 | Jul-Nov 2025 | N07 |
| NAND component inside a 3.84TB enterprise SSD (TechInsights teardown, ~$46.6/TB) | about 75 | about 2023 | N14 |
| Gartner manufacturing-cost estimate, 5-7 cents/GB | 80 to 112 | 2022 | N28 |
| PC-OEM client SSD contract (1TB TLC, $265-385) | 424 to 616 | 3Q26 | C03 |
| Retail consumer NVMe, cheapest 2-4TB listings ($105-120/TB) | 168 to 192 | 2026-08 | C04 |
| Enterprise NVMe: QLC floor $117/TB, tracked average $364/TB | 187 to 582 | 2026-08 | C05 |

Notes:

- Retail "cheapest listing" prices in August 2026 were below the OEM contract price. They probably reflect older inventory or QLC drives. Treat about $0.30/GB as the 2026 marginal bit price and about $0.04-0.07/GB as the normalized cost.
- **Per die:** an SK hynix 321-layer 1Tb TLC die measures 43.54 mm², a density of 23.52 Gb/mm² (N17). Kioxia BiCS10 reaches 29 Gb/mm² and Samsung's 280-layer QLC reaches 28.5 Gb/mm² (N18, N19).
- **Per wafer (derived):** a 43.5 mm² die gives about 1,522 gross dies per 300 mm wafer, or about 195 TB of raw TLC capacity (N22a, N23). At Sep-2026 spot, that wafer's bits are worth about $59k; at Jun-2025 spot, about $8.2k (N25). These are market values, not costs.
- **1.56 TB in dies:** about 12-13 dies of 1Tb (2Tb QLC halves that). At 2026 spot, the bare dies for one K3 copy cost about $500. Before the shortage they cost under $100.
- **Controller:** about $12 in a 2023 enterprise SSD teardown (N15).
- **Package/assembly cost:** unknown (N31).

## (b) The same 1.6 TB in DRAM, HBM, GDDR or SRAM

| Memory | USD/GB | 1.6 TB cost (USD) | Rows |
|---|---|---|---|
| DDR5 chip spot (Oct 12 2026) | 22.0 to 35.3, typ 29.5 | 35k to 56k, typ 47k | D01, C06 |
| DDR5 client UDIMM spot / SO-DIMM contract | 14.9 / 16.6 | 24k to 27k | D03, D05, C07 |
| DDR5 server RDIMM 32GB spot | 67.6 | about 108k | D04, C07 |
| DDR5 chip spot, pre-shortage (Jun 2025) | 3.0 | about 4.8k | D02, C08 |
| LPDDR5/5X contract or LTA (2Q26, secondary source) | 7.8 to 21, typical about 19.5 | 12.5k to 33.6k | D08, C09 |
| HBM3E contract (DigiTimes, Jul 2026) | 12.0 to 12.8 | about 19-20k | D09 |
| HBM3E in Epoch's B200 cost model | 14 to 17 | about 24k | D12 |
| HBM3E resale spot ($2,100 per 36GB stack) | 58.3 | about 93k | D11 |
| HBM4 contract (H2-2026); 2027 forecast | 16; 32 to 40 | 25.6k; up to 64k | D10, C11 |
| GDDR7 (module quotes, low confidence) | 9 to 23 | 14k to 37k | D13, C12 |
| On-die SRAM, TSMC N3E (silicon only, derived) | 0.061 to 0.127 per MB | 98k to 203k | D15, C13 |

Per-GB ratios at 2026 prices, against NAND wafer spot ($0.30/GB):

- DDR5 chip spot: about 100x.
- LPDDR5X: about 64x.
- HBM3E contract: about 41x.
- Before the shortage, DDR5 to NAND was about 70x.

The SRAM derivation uses an N3E wafer at about $20k and 31.8 Mib/mm² HD SRAM macro density:

- Ideally, 1.6 TB of SRAM is about 5.4 full 300 mm wafers of pure SRAM.
- Cerebras' 44 GB of SRAM per WSE-3 wafer means about 36 wafers for the 1.56 TB of K3 weights.
- Groq's 230 MB of SRAM per chip means about 6,800 chips.

## (c) Best measured single-user decode speeds on big MoE models

### Kimi K3 (2.8T total, 104B active, MXFP4; released 2026-07-16)

**SemiAnalysis InferenceX, concurrency 1, MTP speculative decoding, agentic coding traces (median input about 170k-290k tokens):**

| Hardware | Per-user decode | Date |
|---|---|---|
| GB300 8 GPUs | 258 tok/s (TPOT 3.9 ms) | 2026-09-15 |
| B300 8 GPUs | 236 tok/s | 2026-08-16 |
| GB200 16 GPUs | 223 tok/s | 2026-09-19 |
| B200 16 GPUs | 216 tok/s | 2026-10-02 |
| MI355X 8 GPUs | 172 tok/s | 2026-09-30 |

**Without speculative decoding:**

- About 60 tok/s/user on GB200 16 GPUs at concurrency 8.
- OpenZeka, DGX B300 TP8, short prompts: 101 tok/s at concurrency 1 with vLLM (ITL 9.5 ms). With the DSpark draft model this rises to 188 tok/s (ITL 4.8 ms); vLLM reports a DSpark acceptance length of 3.84 tokens with 7 draft tokens.

**Throughput points:**

- About 1,130 tok/s aggregate at concurrency 96 on 16 B200/GB200, but only 11-12 tok/s per user.
- DGX B300 at concurrency 64: 1,759 tok/s aggregate.

**Hopper:**

- InferenceX, 32 H200: about 5 tok/s/user (no FP4 hardware, 330k-token contexts).
- Community report, 2x8 H200 with SGLang W4A16: 16.8 tok/s single-stream.

**API providers (Artificial Analysis, 10k-token input, fetched 2026-10-12):**

- Fastest: Inco FAST 404 tok/s and LithosAI ULTRA CHAT 398 tok/s, on undisclosed hardware.
- Typical: Nebius 194; Databricks, Baseten and Parasail 130-132; Fireworks 112; Bedrock 102.
- Moonshot's own API: 41 tok/s.
- LithosAI claims 800+ tok/s/user on 8xB200. This is unverified.
- No Cerebras, Groq or SambaNova K3 endpoint was found.

### Kimi K2.x (1T total, 32B active)

- Cerebras: 981 tok/s on K2.6 (May-Jun 2026, AA-style test; vendor-published).
- GPU API providers: at most about 258 tok/s.
- InferenceX on K2.5 without spec decoding: GB300 192, B300 single-node 173, MI355X 129 tok/s/user.

### DeepSeek-R1 (671B total, 37B active)

- InferenceX best: 380 tok/s/user on GB300 (58 GPUs, disaggregated, MTP). A single node of 4xB200 reaches 298 tok/s.
- NVIDIA reports 8xB200 at 250 tok/s (GTC 2025) and 368 tok/s (TRT-LLM min-latency).
- SambaNova: 198 tok/s on 16 SN40L (Feb 2025).
- **MLPerf v6.0** added a DeepSeek-R1 Interactive scenario with TPOT ≤ 15 ms, which means at least 66.7 tok/s per user, versus 12.5 tok/s in the Server scenario. GB300 NVL72 delivered 250,634 tok/s of system throughput under that constraint.
- Llama-3.1-405B Interactive allows TPOT up to 80 ms (12.5 tok/s).

### Other models

| Model | Results |
|---|---|
| Llama 4 Maverick (400B/17B), May 2025 | Cerebras 2,522; DGX B200 1,038 (AA-measured, EAGLE-3); SambaNova 794; Groq 549 tok/s |
| Qwen3-235B | Cerebras 1,500 tok/s (Jul 2025) |
| gpt-oss-120b | Cerebras 1,756 tok/s (AA, 2026) |
| Qwen3.5-397B-A17B | GB300 602 tok/s/user (InferenceX) |
| GLM-5.x (744B) | B200/MI355X (TileRT) 480-529 tok/s/user |

### Takeaways

- **Bandwidth floor (derived, K03):** K3 reads about 55 GB of active-expert weights per token. Without speculative decoding, that requires about 5.5 TB/s of effective weight bandwidth for 100 tok/s and about 55 TB/s for 1,000 tok/s, before KV-cache reads.
- **What GPUs do now:** they reach 200-260 tok/s/user on K3 only with spec decoding (about 3-4 tokens accepted per pass) on 8-16 Blackwell GPUs (64-128 TB/s of aggregate HBM bandwidth).
- **Above 1,000 tok/s:** so far shown only on Cerebras wafer-scale SRAM, and only for models of 1T parameters or fewer.
- **Energy (InferenceX, GPU board power only):** K3 single-stream on GB300 x8 draws about 3.7 kW (465 W/GPU), or 28 J per output token. B200 x16 draws 5.8 kW, or 49 J/token. Loaded systems get down to 8-10 J/token.
- **System power ratings:** DGX B200 is rated about 14.3 kW; GB200 NVL72 about 120-130 kW; GB300 NVL72 132-140 kW.
- **SSD power:** an enterprise QLC SSD draws 20-25 W maximum and 4-5 W idle. SSD-level read energy is about 208 pJ/bit (P14-P17).

### System prices (gpu_systems_sourced.csv)

| System | Price |
|---|---|
| B200 | $30-40k per GPU (Epoch estimates manufacturing cost at about $6.4k, of which HBM is about $2.9k) |
| H200 | about $31-34k |
| MI355X | about $23k average selling price |
| GB200 NVL72 | about $3M |
| GB300 NVL72 | just under $5M (purchase orders, Aug 2026) |
| RTX 5090 | $1,999 MSRP; $3.7-4.1k street in 2026 |
| RTX PRO 6000 | $8,565 MSRP; $11.5-16k street |
| Tenstorrent p150a | $1,399 (32 GB GDDR6, 512 GB/s) |

## (d) What is unknown or weakly sourced

- **Custom 3D NAND engineering lot or custom-array wafer run:** no public price. NAND makers offer no MPW or foundry access; a figure would need an NDA quote (N30).
- **Processed wafer cost and cost per Gb for 200+ layer NAND:** paywalled (Yole, TechInsights, SemiAnalysis). The only public figures are old: $2,000 per wafer in 2017 and 5-7 cents/GB in 2022 (N26-N28).
- **NAND fab capex per wafer-start:** current figure unknown. The only point found is a mid-2000s planar fab at about $65k per wpm (N29).
- **NAND package and assembly/test cost; current SSD controller price:** no 2025-26 figures. The only data point is $12 from a teardown (N15, N31).
- **NAND die-level read power:** unknown, with no vendor die specification found. Only SSD-level figures exist (P17, P18).
- **Analog or digital compute-in-memory die cost** (NAND-PIM, RRAM-CIM): no public cost data. TSMC 22/28/40nm eRRAM is in volume production (R01-R03), but there is no public $/die for CIM.
- **MPW and masks at 22nm:** no public TSMC 22nm (22ULL) MPW price and no 22nm mask-set figure (M02, M11).
- **Mask sets at 7nm and 3nm:** estimates disagree by 3-4x ($3.5M vs over $10M at 7nm; $15M vs about $40M at 3nm).
- **HBM:** all prices are NDA contracts. The figures above are press or analyst reports.
- **GDDR7:** $/GB comes from module quotes and a market-research projection only.
- **Undisclosed or unconfirmed prices:** Cerebras CS-3 (a $2-3M estimate), Groq card, SambaNova rack, AMD MI300X/MI325X, and B300 list prices.
- **Hardware behind the fastest K3 API endpoints** (Inco, LithosAI): undisclosed. LithosAI's 800+ tok/s claim is unverified.
- **Kimi K3 active parameters:** the 104B figure comes from a provider page (Parasail), not an official model card.
- **OpenRouter per-provider throughput:** not exposed by its API at fetch time; the fields were null.
