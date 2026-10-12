# Kimi K3 on non-volatile compute-in-memory: what would it take?

A reproducible, first-principles feasibility study of running the **complete, publicly released
Kimi K3** (2.78 T parameters, 104 B active, MXFP4 experts + BF16 dense weights, 1M context) at
**100–1,000 single-stream generated tokens/s** (target 500) on low-cost non-volatile-memory
compute architectures, compared with GPUs.

**Read first:** [`results/final_verdict.md`](results/final_verdict.md) ·
[`results/first_principles.md`](results/first_principles.md) ·
[`results/workload.md`](results/workload.md) · [`results/gpu_comparison.md`](results/gpu_comparison.md)

## Headline results (details and caveats in `results/final_verdict.md`)

| question | answer (realistic scenario, volume silicon at normalized prices, packaging unknown) |
|---|---|
| Commodity NAND (digital or analog on commodity planes)? | 0.2-25 tok/s: the commodity plane's 10-50 µs access sits on a 698-deep dependency chain |
| Redesigned small-plane analog 3D NAND + attention engine, 128K context | 100 tok/s for ~$880; 500 tok/s for $1,477 (marginal precision) / $2,182 (within budget); ~1,000 tok/s only with optimistic array physics |
| 1M context at 500 tok/s | infeasible in every scenario (2.6 PFLOP/s + 7-15 TB/s of attention) |
| Accuracy on real K3 tensors | 1-2-bit cells + calibrated unit-LSB ADC reproduce exact integer sums under SONOS-class noise; 4-bit cells need ~4x tighter programming; no 3D-NAND string measurement exists |
| Under $500? | only at 32K context with three unproven levers; ~$850 floor at 128K (attention engine ~$430) |
| GPU reference | 101 tok/s measured on 8x B300 (188 with speculation); ~330 tok/s software ceiling; 28-34 J/token vs 0.3-0.7 J/token for the CIM designs |

## What is in here

| path | content |
|---|---|
| `k3cim/workload.py` | Op-level K3 decode graph (3,155 ops, true dependencies) built from the released config; parameter counts verified against all 497,220 checkpoint tensors |
| `k3cim/formats.py` | Exact MXFP4 (E2M1/E8M0, compressed-tensors packing) and MXFP8-E4M3 numerics, BF16 rounding |
| `k3cim/analog.py` | Vectorised analog-CIM MVM model (cell slicing, differential/offset sign, contributors per conversion, input passes, ADC, programming/read noise, drift, temperature, BL compression, calibration, spot-checking); cross-validated against CrossSim AnalogCore |
| `k3cim/devices.py` | CrossSim measured device models (SONOS 128K-device data, RRAM Milo/Wan) plugged into the simulator |
| `k3cim/scheduler.py` | Deterministic single-stream scheduler: per-op latency/energy, critical path, resource bounds, speculative decoding, prefill |
| `k3cim/architectures.py` | Architectures A0–A2 (digital NAND), B–E (analog 3D NAND), F (3D RRAM), G (FeNAND), H (GPU) × pessimistic/realistic/optimistic |
| `k3cim/params.py` | Every physical parameter with evidence class and source → `results/physical_assumptions.csv` |
| `k3cim/cost.py` | Area / die / wafer-based volume silicon cost (normalized 2025 vs 2026-shortage prices), unknowns explicit |
| `scripts/` | Data acquisition, real K3 forward pass, simulators, sweeps, DSE, report generation, plots |
| `data/sources/` | Sourced databases (physical parameters, costs, GPU systems, measured K3/LLM decode benchmarks) built by literature search, every row cited |
| `data/sim_outputs/` | Raw outputs of 3D-FPIM NVSim, NeuroSim V1.4 and CrossSim runs |
| `results/` | Deliverables (CSV/MD) and `results/plots/` |
| `tests/` | Unit tests (`pytest tests`) |

## Reproduce

```bash
pip install -r requirements.txt
git clone https://github.com/sandialabs/cross-sim ext/cross-sim && pip install -e ext/cross-sim
git clone https://github.com/SNU-HPCS/3D-FPIM ext/3D-FPIM            # NVSim-based NAND PIM simulator
# NeuroSim: see data/sim_outputs/neurosim/README.md (branch 2DInferenceV1.4, run_neurosim_sweep.sh)

python scripts/fetch_k3_manifest.py          # config + safetensors headers only (~60 MB), builds tensor manifests
python scripts/k3_real_forward.py            # real K3 layers 0-3 on real text (downloads ~15 GB of selected tensors)
python scripts/sims/crosssim_baseline.py     # CrossSim published-tutorial reproduction
python scripts/sims/crosssim_seed_spread.py
python scripts/sims/crosssim_crossval.py     # k3cim.analog vs CrossSim AnalogCore
python scripts/sims/run_fpim.py --fpim ext/3D-FPIM/3DFPIM-NVSim   # 3D-FPIM baseline + K3 plane configs
python scripts/precision_sweep.py            # real-tensor analog precision sweep -> results/precision_sweep.csv
python scripts/precision_sweep_calibrated.py # same with ADC range calibrated on held-out tokens (merged into the CSV)
python scripts/precision_device_grid.py      # device-only error grid
python scripts/analyze_k3_numerics.py        # MX-scale statistics, BF16 re-quantisation, activation stats
python scripts/noise_propagation.py          # analog-like noise through real layers 0-3 (routing stability)
#   (cases can be split: --only <case,...> --out part.csv, then --merge part1.csv part2.csv ...)
python scripts/dse.py                        # design-space exploration -> data/dse_results.csv
python scripts/requirements_table.py         # cheapest design per target/context/scenario -> results/what_it_takes.csv
python scripts/summarize_dse.py              # per-family fastest / cheapest summary -> results/dse_summary.csv
python scripts/run_all.py                    # all results/*.csv, workload.md, gpu_comparison.md
python scripts/first_principles.py           # floors + step ladder -> results/first_principles.md, step_ladder.csv
python scripts/make_plots.py                 # results/plots/*.png
pytest tests
```

All steps are deterministic (fixed seeds). Downloads come from the pinned HuggingFace revision
`moonshotai/Kimi-K3@f831ab66814297da540d832a5235f8e904f29d06` via HTTP byte ranges; nothing
beyond the tensors actually used is fetched.

## Evidence discipline

Every number carries one of: *measured silicon*, *vendor spec*, *peer-reviewed simulation*,
*preprint simulation*, *simulator run in this repo*, *derived*, *assumption*, *speculative*, or is
reported as *unknown*. Costs without a manufacturing basis (packaging, assembly, NRE of custom
NAND lots) are reported as unknown, never invented. See `results/physical_assumptions.csv` and
`data/sources/*.csv`.
