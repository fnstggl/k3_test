#!/usr/bin/env bash
# Supplementary Table VII runs with IDEAL-forward traces (--inference 0).
#
# The faithful flow (--inference 1) emulates ADC/partial-parallel effects in PyTorch with thousands of full-size
# masked convolutions per layer; on a shared 4-core CPU a parallelRead=32 run needs >2 h for ONE image.
# With --inference 0 the wrapper runs the plain 8-bit WAGE forward (seconds) and still dumps the same 16 trace
# files and calls the same ./NeuroSIM/main (hook.hardware_evaluation is registered regardless of --inference).
# Only the layer-2..8 activation VALUES differ (no ADC quantisation in the forward pass). In synchronous mode the
# C++ chip area, cycle counts and sensing clock do not depend on trace values, so area / TOPS / TOPS/mm2 are
# expected to be identical to the faithful flow; energy (TOPS/W) changes slightly. This is checked on RRAM pr64,
# for which both flows were run (see parse_baseline.py / baseline_reproduction.csv).
#
# Usage: run_baseline_ideal_traces.sh <NeuroSim_V1.4 checkout> <venv python> <output dir>
set -euo pipefail
REPO=${1:?repo}; PY=${2:?python}; OUT=${3:?out}
THREADS=${THREADS:-2}
TOOLS=$(cd "$(dirname "$0")" && pwd)
EXT=$(dirname "$REPO")
COPIES=$EXT/wrap_copies
PRISTINE=$EXT/Param.cpp.pristine
LOGS=$OUT/logs/baseline
mkdir -p "$LOGS" "$COPIES"
git -C "$REPO" show HEAD:Inference_pytorch/NeuroSIM/Param.cpp > "$PRISTINE"

prep_copy () {   # $1 = tag, rest = Param.cpp knobs
  local tag=$1; shift
  local d=$COPIES/$tag
  rm -rf "$d"; mkdir -p "$d"
  (cd "$REPO/Inference_pytorch" && tar --exclude=./layer_record_VGG8 --exclude=./log/default --exclude='*.o' --exclude=./NeuroSIM/main -cf - .) | tar -xf - -C "$d"
  python3 "$TOOLS/set_param.py" "$PRISTINE" "$d/NeuroSIM/Param.cpp" "$@" > "$LOGS/$tag.build.log"
  (cd "$d/NeuroSIM" && make -j"$THREADS" 2>&1 | tail -1) >> "$LOGS/$tag.build.log"
}
run_wrapper0 () {  # $1 = tag, $2 = parallelRead, $3 = onoffratio
  local tag=$1 pr=$2 onoff=$3 start; start=$(date +%s)
  ( cd "$COPIES/$tag" && "$PY" -W ignore::SyntaxWarning "$TOOLS/run_wrapper.py" --threads "$THREADS" --n_images 1 \
      --dataset cifar10 --model VGG8 --mode WAGE --inference 0 --cellBit 1 --subArray 128 \
      --parallelRead "$pr" --ADCprecision 4 --onoffratio "$onoff" --batch_size 1; echo "# exit=$? wall_seconds=$(( $(date +%s) - start ))" ) > "$LOGS/$tag.log" 2>&1
}
rerun_cpp () {     # $1 = tag, $2 = trace tag, rest = Param knobs
  local tag=$1 ttag=$2; shift 2
  prep_copy "$tag" "$@"
  local cmd start; cmd=$(sed "s#\./layer_record_VGG8/#$COPIES/$ttag/layer_record_VGG8/#g" "$COPIES/$ttag/layer_record_VGG8/trace_command.sh")
  start=$(date +%s)
  ( cd "$COPIES/$tag" && echo "# command (C++ only, traces from $ttag): $cmd" && bash -c "$cmd"; echo "# exit=$? wall_seconds=$(( $(date +%s) - start ))" ) > "$LOGS/$tag.log" 2>&1
}

for spec in "rram22_pr64 2 64 17" "rram22_pr32 2 32 17" "sram22_pr64 1 64 inf" "sram22_pr32 1 32 inf"; do
  set -- $spec
  tag=${1}_inf0
  prep_copy "$tag" memcelltype=$2 technode=22 levelOutput=16 cellBit=1
  run_wrapper0 "$tag" "$3" "$4"
done
for pr in 32 64; do
  rerun_cpp sram5_pr${pr}_inf0 sram22_pr${pr}_inf0 memcelltype=1 technode=5 levelOutput=16 cellBit=1
  rerun_cpp sram1_pr${pr}_inf0 sram22_pr${pr}_inf0 memcelltype=1 technode=1 levelOutput=16 cellBit=1
done
echo "ideal-trace runs done"
