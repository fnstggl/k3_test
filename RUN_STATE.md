# RUN_STATE

# Mission
Determine in software whether a Kimi K3 inference accelerator built on commodity 3D NAND
(weights stay in NAND; weight-heavy dot products computed at/near the plane) can achieve a
structural >10x advantage in joules/token or tokens/$ vs GPU deployment, and find the minimum
NAND-internal primitive set required. Falsification-driven; outputs feed a later BABOL
real-NAND experiment on Micron MT29F1T08EELEEJ4-R:E.

# Current Gate
Gate 7 — fallback RTL: minimal MXFP4/MXFP8 reducer (rtl/k3_nand_reducer.sv).

# Gate Status
- Gate 0 (env + sources): PASSED (commit gate0-source-audit)
- Gate 1 (Python simulator): PASSED (commit gate1)
- Gate 2 (Palm reproduction): PASSED (commit gate2-palm-calibrated)
- Gate 3 (K3 workload): PASSED (commit gate3-k3-workload)
- Gate 4 (primitive search): PASSED (commit gate4-minimum-primitive)
- Gate 5 (design-space sweep): PASSED (commit gate5-design-space)
- Gate 6 (power/economics): PASSED (commit gate6-economics)
- Gate 7 (fallback RTL): NOT STARTED
- Gate 8 (FEMU): NOT STARTED
- Final deliverables: NOT STARTED

# Established Facts
- K3 validated from primary sources (configs/k3.yaml, all brief numbers confirmed; TR Table 1:
  2.78T total / 104.2B active). CRITICAL: MXFP4 covers ONLY routed-expert weights (2.72T params);
  attention/W↓W↑/shared/router stay higher precision (~55.6B dense-active params/token) [TR 4.1.4].
  vLLM: fp8_fp4_mega_moe + UE8M0 scales confirms real MX arithmetic.
- FEMU builds on this host (official scripts, exit 0) and its CSD device model initializes and
  runs under TCG ("vCSD0 CSD mode initialized"). /dev/kvm absent -> KVM impossible here (fact).
- Third-party pinned in third_party/LOCK.md (FEMU 34bbe45, MQSim 51f0f2d, DRAMsim3 2981759,
  Kimi-K3 3cb39df, vllm 7ab2923 sparse, recipes 4977307).
- Micron part: public info limited to TLC 3D NAND 1Tb x8 132-VBGA DDP; all geometry/timing
  unknown -> configs/nand/mt29f1t08eeleej4_r_e.yaml has explicit unknowns + sweep ranges.
- Host: x86_64 Ubuntu 24.04 container in cloud VM, 4 vCPU (Xeon, AVX-512/AMX flags), 15GB RAM,
  ~30GB free disk, root. gcc 13.3, clang 18, python 3.11.15, cmake 3.28, docker present.
- /dev/kvm ABSENT (container inside KVM hypervisor; no nested KVM exposed). QEMU not yet installed.
  FEMU will require TCG software emulation if it runs at all here.
- LLM-on-the-Palm (ICCAD 2025, DOI 10.1109/ICCAD66269.2025.11240826) fully read; parameters in
  references/llm_on_the_palm_parameters.yaml. Anchors: 256GB Z-NAND SLC tR=3us, 2KB page,
  256 planes (32 die x 8 planes, 8 ch x 4 die/ch), 1 MAC/plane (FP16 mul + FP32 add) @400MHz,
  1024 weights/page in 2.5us < 3us tR, 117 GB/s effective internal BW, avg TPOT 112ms (6.7B),
  215ms (13B), 495ms (30B); per-config and sensitivity numbers captured in the yaml.

# Current Hypotheses
- (RESOLVED in Gate 2) window period = max(tR, MAC, data) + dies/ch x 290ns ONFI cmd sequence
  (MQSim constants). Reproduces all 24 paper latency points within 1.1%.
- K3 active ~104B params/token at 4.25 bit/param (MXFP4+scales) ⇒ ~55GB NAND reads/token ⇒
  commodity TLC/QLC plane counts/tR look challenging; SLC-mode/plane-count/tR sweep is decisive.

# Key Numbers
See references/llm_on_the_palm_parameters.yaml (with page citations) once written.

# Decisions Made
- Use pdftotext extraction of the paper (references/llm_on_the_palm_fulltext.txt) + targeted
  page images for figures.
- Analytic transparent Python simulator first (Gate 1); MQSim/DRAMsim3/FEMU as cross-checks.

# Experiments Completed
- economics.py @ gate6: >10x claim FALSIFIED for throughput serving (GPU 8xB300 at B=256:
  1.9 J/tok, $0.96/Mtok beats NAND best 5.0 J/tok, $1.88/Mtok — GPU ~2-2.5x better; robust
  across sensitivity range). >10x HOLDS ONLY vs low-batch GPU (B<=8): x12-25 on $/tok. Root
  cause: per-bit read energy comparable (NAND 5-11 vs HBM 4-8 pJ/bit); GPUs amortize bytes/token
  23x via batch 256 while K3 MoE expert-union caps NAND batching at 4-8. NAND niche = capacity-$
  per stream (min deployment $3k/100W vs $550k/12kW). results/economics.json.
- sweep.py @ gate5: 14568 points; closed-form vs simulator gap 4.2%. Bottleneck = array sense
  BW (planes x page/tR) once lanes >= 4-8; arithmetic cheap; channel binds only at B>=16.
  Practical frontier: SLC-mode-on-commodity-TLC 16x8x6 (768 planes, 5.5TB raw) = 8 tok/s
  @125ms B=1; 22TB 64ch variant 50 tok/s @79ms B=4, ~5 J/token. Native TLC/QLC never reach
  useful latency. Batch sweet spot B=4-8 (MoE expert-union caps amortization). CSV+plots+summary.
- primitive_search.py @ gate4: stock (A0/A1) caps at 0.50 tok/s SLC / 0.136 TLC with 137GB/token
  exported; hypothetical count-primitive (A2) 25-2500x WORSE than export under MX 32-block scales;
  minimum in-NAND set = C_ADD/D_ACC (SIMD lateral shift+add @<=175ns/pass + 8x32b retained
  accumulators + multi-die broadcast cmd) = 5.76 tok/s, matches full MAC engine (sense-bound).
  Firmware-only K3 FALSIFIED structurally (no lateral datapath in stock page buffers).
  results/primitive_search.csv + reports/03_minimum_primitive.md.
- k3_baseline.py @ gate3: param check 2.7795T/104.18B (0.02% err). Best 2TB SLC-class config
  114.8ms/token (8.7 tok/s, 8.2 J/token); TLC-2TB 0.08-0.14 tok/s (planes deficit ~100x);
  dense-in-DRAM 0.95 tok/s. KEY: MXFP4 pages need >=4 lanes/plane; wide-striped serial experts
  beat grouped (collisions); dense-active pool (55.6B params, 111GB/tok BF16) dominates over
  experts (25.8GB/tok). results/k3_baseline.json + reports/02_k3_workload.md.
- reproduce_palm.py @ gate2 commit: 24/24 paper latency targets within ±1.1%; internal BW
  125.2 vs 117 GB/s (+7%); energy 1.49 vs 1.5 J. results/palm_reproduction.json.
- MQSim cross-check (experiments/mqsim/): stock read path 3.21 GB/s (host-bound, = paper
  baseline class); unthrottled internal ceiling 25.6 GB/s = paper ISP baseline (27 GB/s) ±5%.
- Energy coefficient calibration: 183 nJ/2KB-page sense (range 87-183 from ICC tension),
  200 pJ/B I/O receiver-weighted. Held fixed for K3 gates.

# Active Problems
- /dev/kvm absent → FEMU KVM mode impossible here; TCG attempt pending (Gate 0 item 4 / Gate 8).

# Next Actions
1. Gate 4: configurable primitive model (A_STOCKISH..E_MAC + combos); per-set K3 tok/s,
   traffic, accumulator width, passes; classify each capability (KNOWN STOCK /
   LITERATURE-DEMONSTRATED / VENDOR-POSSIBLE / NEW SILICON); Pareto CSV + report;
   commit gate4-minimum-primitive. NOTE: E2M1 weight-mul = 2-bit shift + conditional add
   (k3/mxfp.py e2m1_as_int_halves) — shift+add+accumulate may suffice; quantify.
2. Gate 5 sweep (incl. batch axis + expert-union amortization). 3. Gate 6 economics
   (batched GPU comparison). 4. Gate 7 RTL. 5. Gate 8 FEMU guest. 6. Finals.

# External Dependencies / Blockers
- None active. KVM absence documented (FEMU runs TCG).

# Important Files
- CLAUDE.md (mission/rules), RUN_STATE.md (this file)
- configs/k3.yaml (validated K3 arch), references/llm_on_the_palm_parameters.yaml (+notes)
- sim/ (calibrated simulator; tests/), experiments/reproduce_palm.py, reports/00+01

# Last Updated
2026-08-30, after gate2-palm-calibrated push.
