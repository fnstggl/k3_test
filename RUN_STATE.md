# RUN_STATE

# Mission
Determine in software whether a Kimi K3 inference accelerator built on commodity 3D NAND
(weights stay in NAND; weight-heavy dot products computed at/near the plane) can achieve a
structural >10x advantage in joules/token or tokens/$ vs GPU deployment, and find the minimum
NAND-internal primitive set required. Falsification-driven; outputs feed a later BABOL
real-NAND experiment on Micron MT29F1T08EELEEJ4-R:E.

# Current Gate
COMPLETE — all software-executable gates (0–8) passed; final deliverables written.
Only remaining work is physical (BABOL real-NAND experiment, spec'd). See audit below.

# Gate Status
- Gate 0 (env + sources): PASSED (commit gate0-source-audit)
- Gate 1 (Python simulator): PASSED (commit gate1)
- Gate 2 (Palm reproduction): PASSED (commit gate2-palm-calibrated)
- Gate 3 (K3 workload): PASSED (commit gate3-k3-workload)
- Gate 4 (primitive search): PASSED (commit gate4-minimum-primitive)
- Gate 5 (design-space sweep): PASSED (commit gate5-design-space)
- Gate 6 (power/economics): PASSED (commit gate6-economics)
- Gate 7 (fallback RTL): PASSED (commit gate7-rtl-fallback)
- Gate 8 (FEMU): PASSED (commit gate8-femu; TCG guest, PARTIALS PASS + modeled-ns match)
- Final deliverables: PASSED (FINAL_REPORT.md, GO_NO_GO.md, BABOL_TEST_SPEC.md, README, Makefile)

# Completion audit (verdict: software program COMPLETE; next step is physical/BABOL)
- Gate 0 audit: DONE (reports/00). LLM-on-Palm: reproduced ±1.1% (reports/01).
- K3 workload: modeled, 0.02% param err (reports/02). Primitive search: DONE (reports/03).
- Design sweep: DONE 14568 pts (reports/03b). Economics/go-no-go: DONE (reports/04).
- RTL fallback: designed+verified(40M cases)+synthesized (reports/05, results/rtl/).
- FEMU: built + TCG-run + PIM_GEMV integrated + 2 real bugs fixed (reports/06); KVM
  externally blocked (no /dev/kvm) but one-command repro works on any host.
- MQSim: integrated + cross-checked (reports/01, experiments/mqsim/). Tests: 21 pass.
- Provenance: every results/*.json carries git+timestamp+host. FACT/MODEL/HYPOTHESIS
  labeled throughout. RUN_STATE current. FINAL/GO_NO_GO/BABOL_TEST_SPEC complete.
- EXTERNAL BLOCKER (only remaining work): physical NAND. BABOL_TEST_SPEC.md E0/E2/E3
  states minimum capabilities, latency bounds (<=1us per 32-block count; <=tR reducer),
  command targets, and pass/fail. No fabricated measurements anywhere.

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
- FEMU @ gate8: PIM_GEMV (opcode 0x9A) in CSD mode with Gate-2 window timing; TCG guest
  (real 6.8 kernel + nvme-cli) run: 8 partials BIT-EXACT vs host + modeled ns 0x97b8=38840
  matches Python model exactly. Fixed 2 real FEMU bugs (CSD FTL-thread never started ->
  IO timeout; TCG msix_notify missing BQL). KVM blocked (no /dev/kvm). reports/06_femu.md,
  results/femu_guest_serial.log, patches/femu_pim_gemv_and_tcg_irq.patch.
- rtl/ @ gate7: k3_nand_reducer.sv (multiplier-free shift-add MX reducer, 8 retained rows);
  Verilator bit-exact vs golden over 40M element pairs (random suite caught+fixed a real
  e=15 shift bug); yosys+sky130: full lane 3362 cells/28038um2, element path 423 cells/
  3372um2/AIG209; 4-lane/plane ~0.002mm2 @2x-nm class ~0.03% of die => TINY confirmed;
  system assumption (4 lanes @400MHz) validated. results/rtl/synthesis_summary.json.
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
- None blocking software work. /dev/kvm absent → FEMU ran under TCG (functional, modeled
  time only); one-command KVM repro provided for a KVM host (scripts/femu_guest_run.sh).

# Next Actions (all remaining work is PHYSICAL — see BABOL_TEST_SPEC.md)
- Software program COMPLETE. Next step is the BABOL bench experiment on real
  MT29F1T08EELEEJ4-R:E: E0.2/E0.3 (measure tR + SLC-mode tR) then E2.2 (attempt a
  <=1us per-32-block fail-bit count). That decides firmware-only viability and pins the
  tR the economics depend on. Nothing further is doable in software without the part.
- (superseded — kept for history) Gate 4: configurable primitive model; Gate 5 sweep; economics
   (batched GPU comparison). 4. Gate 7 RTL. 5. Gate 8 FEMU guest. 6. Finals.

# External Dependencies / Blockers
- None active. KVM absence documented (FEMU runs TCG).

# Important Files
- CLAUDE.md (mission/rules), RUN_STATE.md (this file)
- configs/k3.yaml (validated K3 arch), references/llm_on_the_palm_parameters.yaml (+notes)
- sim/ (calibrated simulator; tests/), experiments/reproduce_palm.py, reports/00+01

# Last Updated
2026-08-31, all gates 0-8 PASSED + final deliverables written (FINAL_REPORT/GO_NO_GO/BABOL_TEST_SPEC).