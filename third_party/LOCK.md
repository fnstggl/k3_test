# Third-party repository lock file

All external repos are cloned by `scripts/clone_third_party.sh` (shallow, then pinned
to these exact commits). Do not vendor-copy their code into ours; do not modify them
except where a documented patch file in `patches/` is applied.

| Repo | URL | Pinned commit | Cloned |
|---|---|---|---|
| FEMU | https://github.com/MoatLab/FEMU | 34bbe45fa74b0be22e93e3602f1c26a0f121fa9e | 2026-08-30 |
| MQSim | https://github.com/CMU-SAFARI/MQSim | 51f0f2d3fed92d88ef4a0fa61a38024b07bf9d16 | 2026-08-30 |
| DRAMsim3 | https://github.com/umd-memsys/DRAMsim3 | 29817593b3389f1337235d63cac515024ab8fd6e | 2026-08-30 |
| Kimi-K3 (report/README only; no weights) | https://github.com/MoonshotAI/Kimi-K3 | 3cb39dfd32e51c3328e2e4b4af21341247d06c43 | 2026-08-30 |
| vllm-project/recipes | https://github.com/vllm-project/recipes | 497730755c756cbcfd7420540e4bea9d62360cfe | 2026-08-30 |
| vllm (sparse: vllm/models, vllm/model_executor) | https://github.com/vllm-project/vllm | 7ab29234890b29b005e46b53037309e597425095 | 2026-08-30 |

Toolchain provenance (host packages, not vendored):
- verilator / yosys: to be installed for Gate 7; versions recorded in reports/05_rtl_fallback.md
- OpenROAD-flow-scripts: decision deferred to Gate 7 (full ORFS build is hours; may use
  yosys+sky130 standalone for area/timing class estimate). Rationale recorded there.
