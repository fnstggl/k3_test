# RUN_STATE

# Mission
Determine in software whether a Kimi K3 inference accelerator built on commodity 3D NAND
(weights stay in NAND; weight-heavy dot products computed at/near the plane) can achieve a
structural >10x advantage in joules/token or tokens/$ vs GPU deployment, and find the minimum
NAND-internal primitive set required. Falsification-driven; outputs feed a later BABOL
real-NAND experiment on Micron MT29F1T08EELEEJ4-R:E.

# Current Gate
Gate 1 — writing sim/ modules (units, nand, arithmetic, plane done; next: mapping,
scheduler, architecture, workload, energy + tests).

# Gate Status
- Gate 0 (env + sources): PASSED (commit gate0-source-audit)
- Gate 1 (Python simulator): IN PROGRESS
- Gate 2 (Palm reproduction): NOT STARTED
- Gate 3 (K3 workload): NOT STARTED
- Gate 4 (primitive search): NOT STARTED
- Gate 5 (design-space sweep): NOT STARTED
- Gate 6 (power/economics): NOT STARTED
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
- Paper's effective period/page ≈ tR + ~0.4us x dies_per_channel (fit from capacity-sensitivity
  TPOTs; implies per-die distinct input broadcast + channel command overhead). To be derived
  properly in Gate 2, not hardcoded.
- K3 active ~104B params/token at 4.25 bit/param (MXFP4+scales) ⇒ ~55GB NAND reads/token ⇒
  commodity TLC/QLC plane counts/tR look challenging; SLC-mode/plane-count/tR sweep is decisive.

# Key Numbers
See references/llm_on_the_palm_parameters.yaml (with page citations) once written.

# Decisions Made
- Use pdftotext extraction of the paper (references/llm_on_the_palm_fulltext.txt) + targeted
  page images for figures.
- Analytic transparent Python simulator first (Gate 1); MQSim/DRAMsim3/FEMU as cross-checks.

# Experiments Completed
(none yet)

# Active Problems
- /dev/kvm absent → FEMU KVM mode impossible here; TCG attempt pending (Gate 0 item 4 / Gate 8).

# Next Actions
1. Write references/llm_on_the_palm_parameters.yaml + notes with citations.
2. Fetch + validate Kimi K3 architecture from MoonshotAI public sources → configs/k3.yaml.
3. configs/nand/mt29f1t08eeleej4_r_e.yaml (knowns only; unknowns explicit).
4. Clone third_party repos (FEMU, MQSim, DRAMsim3, vllm, Kimi-K3, verilator?, yosys?) + LOCK.md.
5. Attempt FEMU build + TCG run.
6. reports/00_environment_and_sources.md; commit gate0-source-audit.

# External Dependencies / Blockers
- None yet. Anticipated: KVM absence (evidence above) — will document after real build/run attempt.

# Important Files
- CLAUDE.md (mission/rules), RUN_STATE.md (this file)
- references/LLM-on-the-Palm.pdf + llm_on_the_palm_fulltext.txt

# Last Updated
2026-08-30, pre-first-commit (branch claude/k3-nand-inference-arch-2fspi1).
