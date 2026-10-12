# NeuroSim (DNN+NeuroSim V1.4) — RRAM CIM subarray / peripheral numbers for the K3 study

Everything here was produced in this container (4 vCPU shared with other jobs, no GPU, g++ 13.3, Python 3.13)
on 2026-10-12. Every number in the CSVs comes from a NeuroSim run whose stdout is in `logs/`.
Nothing was hand-entered except the Table VII "expected" values, which are cited.

## 1. Source and build

| item | value |
|---|---|
| repo | https://github.com/neurosim/NeuroSim (pre-cloned at `/home/user/ext/NeuroSim`, `main` branch = README only) |
| branch | `2DInferenceV1.4` (fetched as `refs/heads/2DInferenceV1.4`; the name is also a tag, so a plain `git fetch origin 2DInferenceV1.4` only fetches the tag) |
| commit | `8a88abf85844c0e1ba17cc771ea535fff6040456` (2025-10-26, "Implement warning for technode temperature") |
| working checkout | `/home/user/ext/NeuroSim_V1.4` |
| manual used | `Documents/User Manual of DNN simulator_V1.4_v3_updated_1229.pdf` (34 pp.) + 3 "Additional Update Note" PDFs |
| C++ build | `cd Inference_pytorch/NeuroSIM && make` (`g++ -fopenmp -O3 -std=c++0x -w`), 12 s, no errors (`logs/build_stock_neurosim.log`) |
| Python | venv `/home/user/ext/venv_neurosim`: torch 2.14.1+cpu, torchvision 0.29.1+cpu, numpy 2.5.2, pyarrow 26.0.0, pillow 12.3.0 |
| dataset | CIFAR-10 test split from the HuggingFace mirror `uoft-cs/cifar10` (`plain_text/test-00000-of-00001.parquet`, sha256 `841389e6…ce84de`) converted to `/home/user/ext/datasets/hf_cifar10/cifar10_test_uint8.npz` (`tools/make_cifar_npz.py`). The canonical toronto.edu tarball downloaded at ~50 KB/s and was abandoned. Labels[:10] = 3 8 8 0 6 6 1 6 3 1 (canonical order). |
| pretrained model | shipped `Inference_pytorch/log/VGG8.pth` (8-bit WAGE) |

V1.4 was used (it is the requested branch, it builds cleanly, and it has the 130→1 nm technology files,
SAR ADC, multilevel SA ADC, partial-parallel mode and XY bus). No other branch was needed.

## 2. What was run (chronological)

```bash
# source
git -C /home/user/ext/NeuroSim fetch origin refs/heads/2DInferenceV1.4:refs/remotes/origin/2DInferenceV1.4
git clone --no-checkout /home/user/ext/NeuroSim /home/user/ext/NeuroSim_V1.4
git -C /home/user/ext/NeuroSim_V1.4 fetch /home/user/ext/NeuroSim refs/remotes/origin/2DInferenceV1.4:refs/heads/v14
git -C /home/user/ext/NeuroSim_V1.4 checkout v14                       # -> 8a88abf8
# stock C++ build
cd /home/user/ext/NeuroSim_V1.4/Inference_pytorch/NeuroSIM && make -j4
# python env (CPU torch) + data
python3 -m venv /home/user/ext/venv_neurosim
/home/user/ext/venv_neurosim/bin/pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
/home/user/ext/venv_neurosim/bin/pip install pyarrow
curl -L -o .../hf_cifar10/test-00000-of-00001.parquet https://huggingface.co/datasets/uoft-cs/cifar10/resolve/main/plain_text/test-00000-of-00001.parquet
python -I tools/make_cifar_npz.py <parquet> /home/user/ext/datasets/hf_cifar10/cifar10_test_uint8.npz
# CPU patch to the wrapper (see §3)
sed -i "s/device='cuda')/device=remainderQ.device)/" Inference_pytorch/modules/quantization_cpu_np_infer.py
# Table VII baseline (§4): per config, Param.cpp knobs via tools/set_param.py, make, then in a per-config copy of Inference_pytorch/:
python tools/run_wrapper.py --threads 2 --n_images 1 --dataset cifar10 --model VGG8 --mode WAGE --inference 1 \
       --cellBit 1 --subArray 128 --parallelRead {32|64} --ADCprecision 4 --onoffratio {17|inf} --batch_size 1
#   (inference.py then runs ./NeuroSIM/main NetWork_VGG8.csv 8 8 128 {32|64} <16 trace files> itself)
# per-subarray sweep (§5): driver build + 660 configurations
python3 tools/sweep.py --build /home/user/ext/neurosim_driver_build --pristine /home/user/ext/Param.cpp.pristine --out .
python3 tools/sweep.py ... --collect-only          # regenerate CSVs from logs/sweep/*.log
# driver-vs-stock-main cross-check (§5.4)
bash tools/crosscheck_main.sh /home/user/ext/neurosim_driver_build /home/user/ext/Param.cpp.pristine /home/user/ext/NeuroSim_V1.4 .
```

`run_neurosim_sweep.sh` repeats all of this from scratch (`--with-baseline` adds the slow Table VII runs).
One attempted RRAM-pr32 wrapper run with 4 torch threads thrashed on the shared CPU and was aborted by me
after 18 min (`logs/baseline/rram22_pr32_ABORTED_4threads.log`); it was rerun with 2 threads.

## 3. Source modifications

* **Code change (wrapper only)** — `neurosim_changes.patch`: `Inference_pytorch/modules/quantization_cpu_np_infer.py`
  hard-codes `device='cuda'` in 5 `torch.full(...)` calls (conductance-variation noise), which crashes on a CPU-only
  host even with `--vari 0`. Replaced by `device=remainderQ.device`. Numerically identical.
* **No change to any NeuroSim C++ source.** Hardware knobs are set by rewriting the first assignment of each knob in a
  pristine copy of `Param.cpp` (`tools/set_param.py`, prints `Param.cpp:<line> old -> new` into every log), which is
  what the manual (§10.2) tells users to do. The working copy's `Param.cpp` is restored to the shipped file afterwards.
* **Runtime shims, no source change** (`tools/run_wrapper.py`): (a) `models.dataset.get_cifar10` is monkey-patched to
  read the first `--n_images` images of the local npz with the identical transforms; (b) `torch.load` defaults to
  `map_location='cpu'` because the shipped `VGG8.pth` contains CUDA tensors.
* **New code** (not a modification): `tools/subarray_driver.cpp`, linked against the *unmodified* NeuroSim objects
  (everything except `main.o`), see §5.

## 4. Baseline reproduction (manual Table VII)

BASELINE_SECTION_PLACEHOLDER

## 5. Per-subarray RRAM sweep (`rram_subarray_sweep*.csv`)

### 5.1 Method

`tools/subarray_driver.cpp` (one process per configuration, Param.cpp regenerated + `Param.o` recompiled + relinked):

1. Applies exactly what `main.cpp` applies from argv / derives (main.cpp:73-76, 79-82, 119-154): `synapseBit=8`,
   `numBitInput=8`, `numRowParallel=numRowSubArray` (all rows read in parallel), operation mode, `numColPerSynapse =
   ceil(8/cellBit)`, and the RRAM ≤14 nm guard of main.cpp:86-90 (bypassable only with `--force-unsupported`).
2. `ProcessingUnitInitialize(subArray, …, 1,1,1,1)` (ProcessingUnit.cpp:71-251): a PE holding one subarray. This is
   NeuroSim's own initialisation of the cell (Ron/Roff, 1T1R access-transistor sizing), technology and SubArray.
3. Synthetic traces: a rows×cols conductance matrix from uniform-random 8-bit weights, bit-sliced into `cellBit`
   cells exactly like `Chip.cpp::LoadInWeightData` (Chip.cpp:1399-1458), and **one** random 8-bit input vector as
   8 bit-planes, each bit Bernoulli(0.5) (seed 12345). Real ReLU activations are sparser (manual's VGG8 toggle rate
   0.18), so energy here is for 50 % input-bit density.
4. Synchronous mode (the shipped default, Param.cpp:116): pass 1 = `ProcessingUnitCalculatePerformance(...,
   CalculateclkFreq=true)` gives the sensing cycle; `clkFreq` is capped as in main.cpp:289-306. Pass 2 loops over the
   8 bit-planes with `GetInputVector` / `GetColumnResistance` / `SubArray::CalculateLatency` /
   `SubArray::CalculatePower` (identical loop body to ProcessingUnit.cpp:497-534) and sums them = **one bit-serial MVM,
   batch 1**. Latency = cycles × sensing cycle (main.cpp:321-326 does the same).
5. Also reports the 1-subarray PE totals from `ProcessingUnitCalculatePerformance(..., false)` (adds PE input/output
   DFF buffers, PE adder tree, PE buses) in `rram_subarray_sweep_detailed.csv` (`pe1.*` columns).

### 5.2 Knobs (Param.cpp line numbers of the shipped file)

| knob | Param.cpp | shipped | used |
|---|---|---|---|
| `operationmode` | 58 | 2 (conventionalParallel) | 2 |
| `memcelltype` | 61 | **1 (SRAM)** | **2 (RRAM)** |
| `accesstype` | 65 | 1 (1T1R, CMOS access) | 1 = 1T1R pseudo-crossbar; 4 = crossbar with ideal selector (`array=XBAR`) |
| `deviceroadmap` | 72 | 2 (LSTP) | 2 |
| `SARADC` / `currentMode` | 101 / 103 | false / true | false/true (flash = current-mode multilevel SA) or true (SAR) |
| `validated` (β=1.4 sensing-cycle factor) | 113, 373 | true | true |
| `synchronous` | 116 | true | true |
| `clkFreq` (upper bound) | 124 | 1e9 | 1e9 (actual = 1/sensing cycle when slower) |
| `technode` | 127 | 22 | 22 (7 only forced, §6) |
| `numRowSubArray` = `numColSubArray` | 203-204 | 128 | 128, 256, 512, 1024 (NeuroSim forces square: ProcessingUnit.cpp:152) |
| `numRowParallel` | 239 | = numRowSubArray | = numRowSubArray (full parallel) |
| `numColMuxed` (columns per ADC) | 249 | 8 | 8 (main CSV); 1, 2, 4, 16 in `_colmux_sensitivity.csv` |
| `levelOutput` (ADC levels) | 258 | 32 | 2^b, b = 4…10 |
| `cellBit` | 259 | 1 | 1, 2, 4 |
| `dumcolshared` (SAs per dummy ref. column) | 263 | = levelOutput | = levelOutput |
| 1T1R cell / crossbar cell | 339-342 | 4F×12F / 2F×2F | same |
| `resistanceOn` / `resistanceOff` | 344-345 | 100 kΩ / 1.7 MΩ (on/off 17) | same |
| `readVoltage` | 351-363 | 0.55 V @22 nm, 0.264 V @7 nm (fixed: ADC LUTs were fitted at these) | same |
| `readPulseWidth` | 365 | 10 ns | same (unused in synchronous parallel mode; only ShiftAdd.cpp:215-231 async path) |
| `accessVoltage` | 366 | 1.1 V | same |
| `writeVoltage` | 368 | 2 V (>1.5 V ⇒ write level shifters are instantiated and counted in area) | same |
| `synapseBit`, `numBitInput` | main.cpp:73-74 (argv) | — | 8, 8 |

### 5.3 Column definitions (`rram_subarray_sweep.csv`, 22 nm, 252 rows)

Rows = 4 sizes × 3 cell precisions × 7 ADC precisions (4-10 b) × {1T1R+flash, 1T1R+SAR, crossbar+flash}; input 8 b.
The array/ADC type and all other per-row context is in `notes` (`array=…; adc=…; numColMuxed=…`).

* `latency_ns_per_mvm` — 8 input bit-cycles × `numColMuxed` mux phases × sensing cycle. Sensing cycle =
  β·(max(WL switch-matrix delay, mux+mux-decoder delay) + ADC + encoder) (SubArray.cpp:1271-1380). Shift-add is
  pipelined/hidden in synchronous mode.
* `energy_pJ_per_mvm` — `SubArray::readDynamicEnergy` summed over the 8 bit-planes (SubArray.cpp:1855-1951): WL charging
  ×numColMuxed (`array_wl`), ADC, mux, mux decoder, WL switch matrix, input/weight shift-add. Excludes leakage energy,
  write/programming energy, PE adder tree, buffers and interconnect (PE values: detailed CSV `pe1.*`).
  `energy_breakdown_pJ.*` in the detailed CSV sums to this value exactly.
* `adc_energy_pJ_per_conversion` — ADC dynamic energy (MLSA or SAR) / (cols × 8 bit-planes); one conversion = one
  column digitised once. Flash: MultilevelSenseAmp.cpp:240-366 ((2^b−1) SAs switching + column/reference static
  current × LUT latency); SarADC.cpp:135-244 (fitted power × (b+1) ns). The flash encoder has **zero** dynamic energy by
  design (MultilevelSAEncoder.cpp:219-220).
* `adc_area_um2` — per ADC = (MLSA area incl. its share of dummy reference columns + encoder) / (cols/numColMuxed).
  MLSA area = 9 min-NMOS equivalents × (2^b−1) SAs (MultilevelSenseAmp.cpp:176) + reference columns
  (arrayheight×cellwidth×(2^b−1)×#ADC/dumcolshared); SAR: SarADC.cpp:81.
* `subarray_area_um2` — `SubArray::area` (floorplanned height×width, SubArray.cpp:734-787).
  `area_breakdown_json`: `array`, `adc_total` (= `adc_mlsa_incl_ref_cols` + `adc_encoder`, or `adc_sar`),
  `adc_ref_cols` (part of mlsa), `shift_add_input`, `shift_add_weight`, `psum_adder_dff` (0 at full parallel),
  `wl_switch_matrix` (the row drivers; there is no WL *decoder* in parallel mode), `sl_switch_matrix`, `mux`,
  `mux_decoder` (the only decoder in parallel mode), `level_shifters` (write path), `wl_repeater_buffers` (0 at 22 nm),
  `floorplan_empty`, and NeuroSim's own categories `neurosim_cat_ADC/Accum/Other`. PE-level input/output DFF buffers
  (outside the subarray) are in the detailed CSV as `pe1.io_buffer_area_um2`.
* `leakage_uW` — `SubArray::leakage` (switch matrices, mux decoder, SA encoder, shift-add; LSTP devices). NeuroSim
  assigns no leakage to RRAM cells or level shifters.

Extra files: `rram_subarray_sweep_detailed.csv` (all 660 runs, every field incl. energy breakdown, sensing-cycle
components, PE totals, and derived `macs_per_mvm`, `energy_fJ_per_mac`, `tops_per_w_subarray`, `tops_subarray`,
`tops_per_mm2_subarray`, `weight_density_Mb_per_mm2`); `rram_subarray_sweep_colmux_sensitivity.csv` (22 nm 1T1R
flash, numColMuxed ∈ {1,2,4,8,16}, ADC 4-8 b); `rram_subarray_sweep_7nm_forced_UNSUPPORTED.csv` (§6).

### 5.4 Driver validation against the stock flow

`tools/crosscheck_main.sh` (`logs/crosscheck_driver_vs_main.log`) runs the stock `main.cpp` on a 1024-input ×
128-output FC layer (= 64 full 128×128 subarrays, 22 nm RRAM 1T1R, 5-bit flash, same Param.cpp) with random
traces of the same statistics, and the driver on one subarray:

| quantity | driver | stock main | diff |
|---|---|---|---|
| sensing clock period | 1.663365 ns | 1.66336 ns | 0.0003 % (print precision) |
| ADC area per subarray | 839.224 µm² | 839.224 µm² (53 710.3 µm² chip ADC area ÷ 64 subarrays; 64 = 24 360.5 µm² CIM-array area ÷ 380.633 µm² per array) | 0 |
| subarray "ADC" energy category per subarray per MVM | 125.246 pJ | 123.943 pJ (7932.34 pJ / 64) | −1.0 % (different random draws) |

(The stock floorplanner rejects a layer that fits in one subarray — "SubArray Size is too large, which break the chip
hierarchey" — and the network CSV needs the 8th "stride" column, otherwise the run silently yields clkPeriod 0/NaN.)

### 5.5 Key numbers, 22 nm RRAM, 1T1R, flash (current-mode MLSA) ADC, numColMuxed = 8, 8-bit bit-serial input

Per subarray, one MVM (MACs = rows × cols/numColPerSynapse 8-bit weights). cellBit changes the number of weights per
subarray but hardly changes per-MVM latency/energy, because in parallel mode NeuroSim's ADC references depend only on
Ron/numRowParallel and the ADC level count (MultilevelSenseAmp.cpp:88-94), not on cellBit.

| rows=cols | ADC b | cell b | MACs/MVM | sensing cycle ns | latency ns/MVM | energy pJ/MVM | fJ/MAC | ADC pJ/conv | ADC µm²/ADC | subarray µm² | leak µW |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 128 | 4 | 1 | 2048 | 1.522 | 97.4 | 136.7 | 66.8 | 0.0348 | 33.4 | 6650 | 0.071 |
| 128 | 5 | 1 | 2048 | 1.663 | 106.5 | 181.5 | 88.6 | 0.0747 | 52.5 | 7026 | 0.086 |
| 128 | 6 | 1 | 2048 | 2.017 | 129.1 | 280.0 | 136.7 | 0.1675 | 103.2 | 7983 | 0.113 |
| 128 | 8 | 1 | 2048 | 5.305 | 339.6 | 1558.6 | 761.0 | 1.415 | 335.8 | 12096 | 0.261 |
| 256 | 5 | 2 | 16384 | 1.725 | 110.4 | 467.4 | 28.5 | 0.0792 | 62.0 | 14642 | 0.146 |
| 512 | 4 | 4 | 131072 | 1.957 | 125.3 | 1156.9 | 8.83 | 0.0449 | 61.1 | 31373 | 0.203 |
| 512 | 6 | 4 | 131072 | 2.179 | 139.5 | 1704.8 | 13.0 | 0.1757 | 132.2 | 36316 | 0.373 |
| 512 | 8 | 4 | 131072 | 3.494 | 223.6 | 4501.3 | 34.3 | 0.850 | 387.5 | 53863 | 0.962 |
| 1024 | 4 | 4 | 524288 | 2.803 | 179.4 | 3965.0 | 7.56 | 0.0542 | 97.9 | 80834 | 0.405 |
| 1024 | 6 | 4 | 524288 | 3.025 | 193.6 | 5138.4 | 9.80 | 0.1943 | 170.9 | 91169 | 0.745 |
| 1024 | 8 | 4 | 524288 | 3.868 | 247.6 | 9740.1 | 18.6 | 0.752 | 449.1 | 128081 | 1.923 |

Other findings (all from the CSVs):
* **ADC sharing dominates latency.** numColMuxed = 1 (one flash ADC per column) cuts latency 8.2-11.9× and energy
  1.1-4.7× (the WL re-drive per mux phase disappears; largest gain at low ADC precision) for 2.3-5.2× subarray area,
  e.g. 512×512, 6 b, 4 b/cell: 139.5 → 15.0 ns/MVM, 1705 → 835 pJ, 36 316 → 113 167 µm². numColMuxed = 16 behaves
  as expected (mux delay ≤0.44 ns). numColMuxed = 2 and 4 are **not usable** in this model: the 1- and 2-address-bit
  mux decoders (for 1 bit, RowDecoder.cpp:73-81 instantiates no NAND/NOR gates) report 0.6-49 ns delays that set the
  clock (sensing cycles up to 71 ns); these rows are flagged in `notes`.
* **SAR vs flash:** SAR is 2.4-5.3× slower per MVM (its conversion takes (b+1) ns, ×β = 1.4, vs 0.9-2.9 ns for
  the ≤8-b flash LUT), e.g. 128×128 5 b: 545.5 vs 106.5 ns/MVM. SAR energy/conversion is 1.3-17× the flash value at 4-6 b and
  0.2-4× at 7-8 b (crossover ≈7-8 b, later for larger arrays), e.g. 128×128: 0.18 vs 0.075 pJ at 5 b, 0.28 vs 1.42 pJ at 8 b.
* **Crossbar (accesstype 4) vs 1T1R:** latency within ±8 %, energy 10-60 % lower (no access-transistor gate load on
  the WL), area 0.71-1.38× (the 2F-pitch array forces a tall, narrow periphery-dominated floorplan for small arrays);
  it assumes an ideal two-terminal selector (manual §6.1, item 3).
* **At low ADC precision, energy is dominated by WL charging, not the ADC:** WL charging + WL switch matrix is 47-83 %
  of subarray energy at 4-5 b (e.g. 1024×1024, 6 b: array_wl 3027 + WL switch 274 pJ vs ADC 1592 pJ of 5138 pJ);
  the ADC is ≥60 % at 8 b for every size (≥72 % at 7 b for ≤256 rows). In NeuroSim the WL energy is re-spent for every
  column-mux phase (SubArray.cpp:1892-1899, `readDynamicEnergyArray *= numColMuxed`).
* **Write-path level shifters are the largest single area item** (writeVoltage = 2 V > 1.5 V): 23-62 % of the
  subarray area in the 22 nm 1T1R flash sweep, e.g. 256×256, 5 b, 4 b/cell: 7689 of 14 371 µm² (array 1523 µm², ADC 1983 µm²).
* **9-10-bit flash ADC rows are extrapolations** (sensing cycle 5.7-38 ns, nJ-scale energy): the reference resistances
  reach Ron·2^(b−1)/numRowParallel, far outside the default range of the Cadence-fitted LUTs
  (MultilevelSenseAmp.cpp:714-1158). Flagged in `notes`.
* Derived (arithmetic on CSV values, not a NeuroSim output): 512×512, 4 b/cell, 6 b ADC, 1T1R holds 3.6 M 8-bit
  weights/mm² of subarray (crossbar: 4.4 M) ⇒ ~7.8×10⁵ mm² of subarrays alone for 2.8×10¹² 8-bit weights at 22 nm,
  before any buffers, interconnect, accumulation, or the digital units an LLM needs.

## 6. 7 nm: not supported for RRAM

`main.cpp:86-90`: `if (memcelltype == 2 && technode <= 14) { "ERROR!: RRAM-CIM is not supported beyond 22 nm!"; exit(-1); }`
Confirmed by running both the stock `main` (exit 255) and the driver without the bypass (exit 3) with
`memcelltype=2, technode=7`: `logs/rram_7nm_guard_check.log`. The 7 nm technology card (Technology.cpp:906), 7 nm current-mode SA latency LUT (MultilevelSenseAmp.cpp:848) and 7 nm SAR fit (SarADC.cpp:223)
exist (they are used for SRAM/FeFET CIM), so the code *executes* for RRAM if the guard is bypassed. Those numbers are in
`rram_subarray_sweep_7nm_forced_UNSUPPORTED.csv` (168 rows, 1T1R and crossbar, flash ADC), every row marked
"UNSUPPORTED NODE". They are **outside NeuroSim's supported envelope** (1T1R access device sized in fins, read voltage
0.264 V chosen for SRAM-style sensing); do not treat them as validated. Example (forced): 512×512, 4 b/cell, 6 b,
1T1R: 103.5 ns/MVM, 1455 pJ/MVM, 0.041 pJ/conversion, 38.6 µm²/ADC, 14 865 µm²/subarray.
No other node between 22 and 7 nm is RRAM-enabled (14 and 10 nm are also blocked by the same guard).

## 7. Features confirmed in source **and** exercised in these runs

| feature | source | run here |
|---|---|---|
| RRAM (memcelltype 2) 1T1R pseudo-crossbar, parallel read | SubArray.cpp:337-365 (cell/access sizing), 424-470 (init), 734-787 (area), 1271-1380 (latency), 1855-1951 (energy/leakage) | sweep + Table VII |
| RRAM crossbar with ideal selector (accesstype 4, 2F×2F) | SubArray.cpp:177-191, 366-378; Param.cpp:341-342 | sweep (`array=XBAR`) |
| Flash ADC = current-mode multilevel SA, Cadence-fitted latency/power LUTs 130→1 nm | MultilevelSenseAmp.cpp:56-110 (references), 165-195 (area), 216-236 (latency), 240-366 (energy), 714-1158 (LUTs) | sweep + Table VII |
| SAR ADC | SarADC.cpp:56-244 | sweep (`adc=SAR`) |
| Multi-bit cells (cellBit) + weight shift-add | Chip.cpp:1427-1458; SubArray.cpp shiftAddWeight | sweep 1/2/4 b |
| Bit-serial input + input shift-add (no DAC) | ShiftAdd.cpp:199-240; manual §6.1 | sweep, Table VII |
| Column-mux ADC sharing (numColMuxed) | Param.cpp:249; SubArray.cpp:446-449 | sweep 1-16 |
| Partial parallel read (numRowParallel < rows) with partial-sum adders | Param.cpp:239; main.cpp:76; SubArray.cpp:457-462; MultilevelSenseAmp.cpp:88 | Table VII (32/64 rows) only |
| Synchronous clocking set by the sensing cycle | main.cpp:289-306, 321, 406; SubArray.cpp:1360-1371 | everywhere |
| Write level shifters (writeVoltage > 1.5 V) in area | SubArray.cpp:381-385, 674-678, 786-787 | everywhere |
| XY global bus (default) | Param.cpp:76 | Table VII |
| 130-1 nm technology cards | Technology.cpp:71-1300 | 22 nm (+7 nm forced; SRAM 5/1 nm in Table VII) |

Present in source but **not** exercised here: voltage-mode SA (`currentMode=false`), FeFET, sequential (row-by-row) mode,
BNN/XNOR modes, H-tree (`globalBusType=true`), `sync_data_transfer`, HP devices (≥22 nm only, main.cpp:92-96),
temperature ≠ 300 K (≥22 nm only).

## 8. NOT supported by NeuroSim V1.4 (2DInferenceV1.4)

* RRAM at ≤14 nm (incl. 7 nm) — main.cpp:86-90.
* 3D vertical RRAM (VRRAM), 3D NAND strings / NAND-flash CIM: no such cell or array type exists (memcelltype is only
  SRAM/RRAM/FeFET, Param.cpp:61-63; no VRRAM/NAND-string code anywhere in NeuroSIM/). The separate branch
  `3DInferenceV1.0` (based on V1.3) models heterogeneous/monolithic 3D *stacking* of tiers (H3D/M3D), not vertical
  RRAM or NAND strings; it was not built or run.
* Analog/DAC inputs (inputs are bit-serial only), non-square subarrays (ProcessingUnit.cpp:152), read-voltage changes
  without re-fitting the ADC LUTs (manual p.21), device noise/variation/drift in the PPA (only in the Python accuracy
  path), write/programming energy in inference mode (commented out, SubArray.cpp:1921-1937).
* Workloads: CNN layers only (conv/FC via NetWork.csv); no attention/softmax/LayerNorm/MoE routing units, no
  off-chip memory (weights are assumed to be fully on-chip, manual §5), no multi-token/batch scheduling.
* Accuracy for the ADC/partial-parallel settings is only obtainable through the PyTorch wrapper, which is
  impractically slow on CPU (see §4).

## 9. File index

| file | content |
|---|---|
| `baseline_reproduction.csv` | Table VII expected vs observed (config, metric, expected, expected_source, observed, pct_diff, notes) |
| `rram_subarray_sweep.csv` | requested schema, 22 nm, 252 rows |
| `rram_subarray_sweep_detailed.csv` | all 660 driver runs, every field + derived per-MAC metrics |
| `rram_subarray_sweep_colmux_sensitivity.csv` | numColMuxed 1/2/4/8/16 (22 nm 1T1R flash) |
| `rram_subarray_sweep_7nm_forced_UNSUPPORTED.csv` | 7 nm with the RRAM guard bypassed — not supported |
| `neurosim_changes.patch` | the only source change (wrapper CPU device fix) |
| `run_neurosim_sweep.sh` | rebuild from scratch + regenerate the sweep CSVs (`--with-baseline`, `--quick`) |
| `tools/subarray_driver.cpp` | single-subarray MVM driver (links unmodified NeuroSim objects) |
| `tools/sweep.py`, `tools/set_param.py` | sweep orchestration / Param.cpp knob rewriting |
| `tools/run_baseline.sh`, `tools/run_wrapper.py`, `tools/parse_baseline.py`, `tools/make_cifar_npz.py` | Table VII reproduction |
| `tools/crosscheck_main.sh` | driver vs stock main.cpp cross-check |
| `logs/sweep/*.log` | stdout of all 660 driver runs (knobs, command, full SubArray module report, RESULT_JSON) |
| `logs/baseline/*.log` | stdout of the wrapper + stock NeuroSim runs, per-config build logs |
| `logs/build_stock_neurosim.log`, `logs/crosscheck_driver_vs_main.log`, `logs/sweep_*.log` | build / cross-check / sweep summaries |
