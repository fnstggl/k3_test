#!/usr/bin/env bash
# Rebuild DNN+NeuroSim V1.4 from scratch and regenerate the per-subarray RRAM sweep CSVs.
#
#   ./run_neurosim_sweep.sh                 # clone/verify + build + driver sweep (~10-20 min on 4 cores)
#   ./run_neurosim_sweep.sh --with-baseline # + Table VII with ideal (--inference 0) traces, C++ at HEAD and at the
#                                           #   original V1.4 upload 6a6073d (~1 h on 4 cores)
#   ./run_neurosim_sweep.sh --with-baseline-faithful
#                                           # + the manual's --inference 1 flow for all configs and the hybrid re-run
#                                           #   (>2 h of CPU per config on a 4-core host, see README section 4)
#   ./run_neurosim_sweep.sh --quick         # tiny sweep subset (smoke test)
#
# Environment overrides: EXT (default /home/user/ext), NEUROSIM_COMMIT (default 8a88abf8...).
# Everything is built under $EXT; outputs go next to this script.
set -euo pipefail
OUT=$(cd "$(dirname "$0")" && pwd)
TOOLS=$OUT/tools
EXT=${EXT:-/home/user/ext}
COMMIT=${NEUROSIM_COMMIT:-8a88abf85844c0e1ba17cc771ea535fff6040456}   # tip of branch 2DInferenceV1.4 used for the published CSVs
REPO=$EXT/NeuroSim_V1.4
BUILD=$EXT/neurosim_driver_build
WITH_BASELINE=0; QUICK=""
for a in "$@"; do
  case $a in
    --with-baseline) WITH_BASELINE=1 ;;
    --with-baseline-faithful) WITH_BASELINE=2 ;;
    --quick) QUICK=--quick ;;
    *) echo "unknown option $a"; exit 2 ;;
  esac
done
mkdir -p "$EXT" "$OUT/logs"

# 1. Source: branch 2DInferenceV1.4 of github.com/neurosim/NeuroSim at a pinned commit.
if [[ ! -d $REPO/.git ]]; then
  git clone --branch 2DInferenceV1.4 --single-branch https://github.com/neurosim/NeuroSim.git "$REPO" \
   || { git init "$REPO" && git -C "$REPO" fetch https://github.com/neurosim/NeuroSim.git refs/heads/2DInferenceV1.4 && git -C "$REPO" checkout -B v14 FETCH_HEAD; }
fi
if [[ $(git -C "$REPO" rev-parse HEAD) != "$COMMIT" ]]; then
  git -C "$REPO" cat-file -e "$COMMIT^{commit}" 2>/dev/null || git -C "$REPO" fetch https://github.com/neurosim/NeuroSim.git refs/heads/2DInferenceV1.4
  git -C "$REPO" checkout -q "$COMMIT"
fi
echo "[run] NeuroSim commit: $(git -C "$REPO" rev-parse HEAD)" | tee "$OUT/logs/source_commit.log"
git -C "$REPO" show HEAD:Inference_pytorch/NeuroSIM/Param.cpp > "$EXT/Param.cpp.pristine"

# 2. Stock build of the C++ core (unmodified sources, shipped Param.cpp).
cp "$EXT/Param.cpp.pristine" "$REPO/Inference_pytorch/NeuroSIM/Param.cpp"
(cd "$REPO/Inference_pytorch/NeuroSIM" && make clean >/dev/null && make) > "$OUT/logs/build_stock_neurosim.log" 2>&1
git -C "$REPO" checkout -- Inference_pytorch/NeuroSIM/.depend   # make regenerates this tracked file
echo "[run] stock build OK: $REPO/Inference_pytorch/NeuroSIM/main"

# 3. Driver build: unmodified NeuroSim objects (all except main.cpp/Param.cpp) + tools/subarray_driver.cpp.
rm -rf "$BUILD"; mkdir -p "$BUILD/src"
git -C "$REPO" archive HEAD Inference_pytorch/NeuroSIM | tar -x -C "$BUILD/src" --strip-components=2
rm -f "$BUILD/src/main.cpp"; cp "$TOOLS/subarray_driver.cpp" "$BUILD/src/"
(cd "$BUILD/src" && ls *.cpp | grep -v '^Param.cpp$' | xargs -P"$(nproc)" -I{} sh -c 'g++ -c -fopenmp -O3 -std=c++0x -w {} -o $(basename {} .cpp).o') \
  > "$OUT/logs/build_driver.log" 2>&1
echo "[run] driver objects built in $BUILD/src"

# 4. Sweep (Param.cpp regenerated + Param.o recompiled + relinked per configuration).
python3 "$TOOLS/sweep.py" --build "$BUILD" --pristine "$EXT/Param.cpp.pristine" --out "$OUT" $QUICK 2>&1 | tee "$OUT/logs/sweep_driver_summary.log"

# 5. Optional: Table VII reproduction through the stock PyTorch wrapper + C++ main.
if [[ $WITH_BASELINE -ge 1 ]]; then
  VENV=$EXT/venv_neurosim
  [[ -x $VENV/bin/python ]] || { python3 -m venv "$VENV"; "$VENV/bin/pip" install --quiet torch torchvision --index-url https://download.pytorch.org/whl/cpu; "$VENV/bin/pip" install --quiet pyarrow; }
  NPZ=$EXT/datasets/hf_cifar10/cifar10_test_uint8.npz
  if [[ ! -f $NPZ ]]; then
    mkdir -p "$(dirname "$NPZ")"
    curl -sSL -o "$(dirname "$NPZ")/test-00000-of-00001.parquet" \
      https://huggingface.co/datasets/uoft-cs/cifar10/resolve/main/plain_text/test-00000-of-00001.parquet
    echo "841389e6f2d64f28bf17310e430aebac20ec3ba611a3c5e231dc93c645ce84de  $(dirname "$NPZ")/test-00000-of-00001.parquet" | sha256sum -c -
    "$VENV/bin/python" -I "$TOOLS/make_cifar_npz.py" "$(dirname "$NPZ")/test-00000-of-00001.parquet" "$NPZ"
  fi
  # CPU patch for the wrapper (see README / neurosim_changes.patch): hard-coded device='cuda'.
  sed -i "s/torch.full(remainderQ.size(),self.vari, device='cuda')/torch.full(remainderQ.size(),self.vari, device=remainderQ.device)/g" \
    "$REPO/Inference_pytorch/modules/quantization_cpu_np_infer.py"
  bash "$TOOLS/run_baseline_ideal_traces.sh" "$REPO" "$VENV/bin/python" "$OUT"
  bash "$TOOLS/run_baseline_oldcode.sh" "$REPO" "$OUT" _inf0
  if [[ $WITH_BASELINE == 2 ]]; then
    bash "$TOOLS/run_baseline.sh" "$REPO" "$VENV/bin/python" "$OUT" "${N_IMAGES:-1}"   # faithful --inference 1 runs
    bash "$TOOLS/run_baseline_oldcode.sh" "$REPO" "$OUT" ""
    [[ -f $EXT/wrap_copies/rram22_pr64/layer_record_VGG8/inputConv7_.csv ]] && bash "$TOOLS/run_baseline_hybrid.sh" "$EXT" "$OUT" rram22_pr64
  fi
  python3 "$TOOLS/parse_baseline.py" "$OUT/logs/baseline" "$OUT/baseline_reproduction.csv"
fi
echo "[run] done. CSVs in $OUT"
