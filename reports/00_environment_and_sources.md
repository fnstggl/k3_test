# Gate 0 — Environment and Source Audit

Date: 2026-08-30. Branch: `claude/k3-nand-inference-arch-2fspi1`.

## 1. Host environment (FACT — measured)

| Item | Value |
|---|---|
| Kernel | Linux 6.18.44-fc-v22 x86_64 |
| Virtualization | Container (systemd-detect-virt: docker) inside a KVM hypervisor (`hypervisor` CPU flag, "Hypervisor vendor: KVM") |
| CPU | 4 × Intel Xeon @ 2.10GHz (family 6 model 207 = Emerald Rapids class; AVX-512, AMX, VAES flags present) |
| RAM | 15 GiB (14 GiB free) |
| Disk | 252G volume, ~30G free for this session |
| `/dev/kvm` | **ABSENT** — no KVM acceleration available; nested virt not exposed to this container |
| OS userspace | Ubuntu 24.04 (noble) |
| Toolchain | gcc 13.3.0, clang 18.1.3, make 4.3, cmake 3.28.3, ninja 1.11.1, python 3.11.15, pip 24.0, git 2.43.0, docker 29.3.1 |
| Missing (installable) | qemu (building FEMU's own), meson (via pip), flex, verilator, yosys |

Implications:
- FEMU with KVM acceleration is **impossible here** (no `/dev/kvm`). Per project rules this is
  established by direct inspection; the actual build/run attempt (TCG software emulation) is
  performed anyway — results in §4 and reports/06_femu.md.
- Python analytic simulation, MQSim, DRAMsim3, Verilator, and Yosys all run fine on this host.

## 2. LLM-on-the-Palm paper (FACT — read in full)

`references/LLM-on-the-Palm.pdf` (ICCAD 2025, DOI 10.1109/ICCAD66269.2025.11240826) was read
completely. All extracted parameters with per-section citations:
`references/llm_on_the_palm_parameters.yaml`; discrepancies and ambiguities (Table I "56GB"
typo, 117 GB/s vs 174.8 GB/s theoretical, M-NAND tR unspecified, GPT-3 "30B" naming):
`references/llm_on_the_palm_notes.md`.

Calibration anchors for Gate 2: TPOT 105/109/114/118 ms (6.7B, four in/out configs; avg 112),
215/495 ms (13B/30B avg), 117 GB/s effective internal bandwidth, capacity-sensitivity TPOTs
(185/112/75/56 ms at 128/256/512/1024 planes), energy 1.5 J/token (6.7B, NAND only,
splits 76.9% cell read / 21.8% I/O / 1.3% P/E), PU area 0.05% of die.

## 3. Kimi K3 architecture (FACT — validated against primary sources)

Sources: MoonshotAI tech report (`references/k3_tech_report.pdf`, pinned repo
`third_party/Kimi-K3` @ 3cb39df), HF `moonshotai/Kimi-K3` config.json (fetched 2026-08-30),
vLLM K3 implementation (`third_party/vllm` @ 7ab2923, `vllm/models/kimi_k3/`).

Every value in the project brief was verified (configs/k3.yaml carries per-field citations):

| Brief claim | Verified value | Source |
|---|---|---|
| 2.8T total params | 2.78T | TR Table 1 |
| ~104B active/token | 104.2B | TR Table 1 |
| 93 layers, 1 dense | 93, first_k_dense_replace=1 | TR Table 1, HF |
| 69 KDA + 24 Gated MLA | 69 + 24 (3:1 pattern + final MLA) | TR §2.1, HF layer lists |
| hidden 7168, 96 heads | 7168, 96 | TR Table 1, HF |
| latent MoE dim 3584 | 3584 ("0.5×") | TR Table 1 |
| expert hidden 3072 | 3072 | TR Table 1, HF |
| 896 routed / 16 active / 2 shared | 896 / 16 / 2 | TR Table 1, HF |
| MXFP4 weights / MXFP8 activations | **routed-expert weights only** (QAT from SFT onward); attention projections, LatentMoE W↓/W↑, shared experts, routers stay higher precision | TR §4.1.4 |

Additional findings material to the study:
- **Quantization split is decisive**: routed experts = 2.72T params (97.8% of weights) in MXFP4
  (4.25 bits/param incl. E8M0 scale per 32-block); dense-active path ≈ 55.6B params/token in
  BF16 (deployment FP8 an option) — the dense-active path alone is ~110 GB/token of weight
  traffic if unquantized, vs ~25.8 GB/token for the 16 routed experts. Where each pool lives
  (NAND vs DRAM) is a first-class design axis for Gates 3/5.
- Derived accounting reproduces published totals: 2.78T total / ~104B active (Gate 3 asserts).
- K3 has 1 MTP layer (EAGLE-3-style draft) — speculative decoding is optional and excluded
  from the baseline single-token decode workload (listed as a sensitivity).
- vLLM path confirms routed-expert GEMM = `fp8_fp4_mega_moe` (DeepGEMM), UE8M0 block scales,
  w13/w2 expert layout — i.e. genuine block-microscaled MXFP4×MXFP8 dot products with FP32
  accumulation, not plain INT4/INT8 (Gate 3/4 model this faithfully).
- E2M1 element magnitudes are {0, .5, 1, 1.5, 2, 3, 4, 6}: a weight-side multiply is a 2-bit
  shift + one conditional add — central to the Gate 4 minimum-primitive search and Gate 7 RTL.

## 4. FEMU compatibility check

- FEMU pinned @ 34bbe45 (QEMU 10.x-era fork). Official build procedure
  (`femu-copy-scripts.sh` + `pkgdep.sh` + `femu-compile.sh`) executed on this host:
  **build SUCCEEDED** (2932/2932 targets, exit 0).
- KVM mode: **blocked by hardware** — `/dev/kvm` does not exist in this container and cannot be
  created without host cooperation (evidence §1). This is an environment fact, not an assumption.
- TCG (software emulation) smoke test: **PASSED** — `qemu-system-x86_64 -accel tcg -device
  femu,femu_mode=4,...` runs; device prints
  `[FEMU] Log: vCSD0,CSD mode initialized: fdm=64MB, nr_cu=4, nr_thread=4` and the machine
  stays up (SeaBIOS loop absent an OS image). Conclusion: FEMU's device model is FUNCTIONAL on
  this host under TCG; full guest boot + K3 trace happens in Gate 8 (wall-clock slow under TCG,
  but measurements use FEMU's modeled device timing, never host wall clock).
- FEMU CSD mode note: `pls_per_lun=1` ("no multiplanes support") — plane-level parallelism will
  be represented by mapping planes onto FEMU LUNs (documented in Gate 8).

## 5. Micron target part (configs/nand/mt29f1t08eeleej4_r_e.yaml)

Publicly confirmable: Micron TLC 3D NAND, 1 Tb, x8, 132-VBGA dual-die package, catalog page
exists but publishes no spec table; part is EOL. All geometry/timing/ECC/read-retry fields are
recorded as `unknown` with sweep ranges — nothing invented.

## 6. Third-party sources pinned

See `third_party/LOCK.md` (FEMU, MQSim, DRAMsim3, Kimi-K3, vllm sparse, recipes; exact SHAs).
verilator/yosys/OpenROAD decision deferred to Gate 7 with rationale recorded there.

## 7. Gate 0 conclusion

All Gate 0 objectives met; no blockers for Gates 1–7. FEMU KVM execution is the single
environment-limited item (evidence above), with the TCG attempt continuing in Gate 8.
