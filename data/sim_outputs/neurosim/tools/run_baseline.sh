#!/usr/bin/env bash
# Reproduce Table VII ("Hardware Estimation Examples", V1.4 user manual p.32) with DNN+NeuroSim V1.4.
#
# Table VII settings: VGG8/CIFAR-10, 8b weight x 8b activation, 1 bit/cell, 128x128 subarray,
# 4-bit ADC, XY bus (globalBusType=false, the shipped default), RRAM on/off = 17, SRAM on/off = inf,
# "the rest of the parameters follow the default setting in the released code".
#
# Each (memory, parallelRead) config runs the stock PyTorch wrapper (inference.py via tools/run_wrapper.py,
# --inference 1, first N test images) in its own copy of Inference_pytorch/ (the wrapper writes traces to
# ./layer_record_VGG8, so concurrent runs must not share a directory); the wrapper itself then runs
# ./NeuroSIM/main through trace_command.sh.  SRAM-5nm / SRAM-1nm rows reuse the SRAM-22nm traces of the
# same parallelRead (the wrapper never sees technode) and only re-run the C++ binary rebuilt for that node.
#
# Usage: run_baseline.sh <NeuroSim_V1.4 checkout> <venv python> <output dir> [n_images]
#   env JOBS (default 2) = concurrent wrapper runs, THREADS (default 2) = torch threads per run.
set -euo pipefail
REPO=${1:?repo}; PY=${2:?python}; OUT=${3:?out}; NIMG=${4:-1}
JOBS=${JOBS:-2}; THREADS=${THREADS:-2}
TOOLS=$(cd "$(dirname "$0")" && pwd)
EXT=$(dirname "$REPO")
COPIES=$EXT/wrap_copies
PRISTINE=$EXT/Param.cpp.pristine
LOGS=$OUT/logs/baseline
mkdir -p "$LOGS" "$COPIES"
git -C "$REPO" show HEAD:Inference_pytorch/NeuroSIM/Param.cpp > "$PRISTINE"

prep_copy () {   # $1 = tag, rest = Param.cpp knobs  -> $COPIES/$tag with ./NeuroSIM/main built for the knobs
  local tag=$1; shift
  local d=$COPIES/$tag
  rm -rf "$d"; mkdir -p "$d"
  (cd "$REPO/Inference_pytorch" && tar --exclude=./layer_record_VGG8 --exclude=./log/default --exclude='*.o' --exclude=./NeuroSIM/main -cf - .) | tar -xf - -C "$d"
  python3 "$TOOLS/set_param.py" "$PRISTINE" "$d/NeuroSIM/Param.cpp" "$@" > "$LOGS/$tag.build.log"
  (cd "$d/NeuroSIM" && make -j"$THREADS" 2>&1 | tail -1) >> "$LOGS/$tag.build.log"
}

run_wrapper () {  # $1 = tag, $2 = parallelRead, $3 = onoffratio
  local tag=$1 pr=$2 onoff=$3
  local start; start=$(date +%s)
  ( cd "$COPIES/$tag" && "$PY" -W ignore::SyntaxWarning "$TOOLS/run_wrapper.py" --threads "$THREADS" --n_images "$NIMG" \
      --dataset cifar10 --model VGG8 --mode WAGE --inference 1 --cellBit 1 --subArray 128 \
      --parallelRead "$pr" --ADCprecision 4 --onoffratio "$onoff" --batch_size 1; echo "# exit=$? wall_seconds=$(( $(date +%s) - start ))" ) > "$LOGS/$tag.log" 2>&1
}

rerun_cpp () {    # $1 = tag, $2 = trace tag (a finished wrapper copy), rest = Param knobs
  local tag=$1 ttag=$2; shift 2
  prep_copy "$tag" "$@"
  local cmd; cmd=$(sed "s#\./layer_record_VGG8/#$COPIES/$ttag/layer_record_VGG8/#g" "$COPIES/$ttag/layer_record_VGG8/trace_command.sh")
  local start; start=$(date +%s)
  ( cd "$COPIES/$tag" && echo "# command (C++ only, traces from $ttag): $cmd" && bash -c "$cmd"; echo "# exit=$? wall_seconds=$(( $(date +%s) - start ))" ) > "$LOGS/$tag.log" 2>&1
}

declare -A PR=([rram22_pr32]=32 [rram22_pr64]=64 [sram22_pr32]=32 [sram22_pr64]=64)
declare -A ONOFF=([rram22_pr32]=17 [rram22_pr64]=17 [sram22_pr32]=inf [sram22_pr64]=inf)
declare -A MEM=([rram22_pr32]=2 [rram22_pr64]=2 [sram22_pr32]=1 [sram22_pr64]=1)
TAGS=${TAGS:-"rram22_pr32 rram22_pr64 sram22_pr32 sram22_pr64"}
for tag in $TAGS; do
  prep_copy "$tag" memcelltype=${MEM[$tag]} technode=22 levelOutput=16 cellBit=1
  run_wrapper "$tag" "${PR[$tag]}" "${ONOFF[$tag]}" &
  while (( $(jobs -rp | wc -l) >= JOBS )); do wait -n; done
done
wait
if [[ " $TAGS " == *" sram22_pr32 "* ]]; then
  rerun_cpp sram5_pr32 sram22_pr32 memcelltype=1 technode=5 levelOutput=16 cellBit=1
  rerun_cpp sram1_pr32 sram22_pr32 memcelltype=1 technode=1 levelOutput=16 cellBit=1
fi
if [[ " $TAGS " == *" sram22_pr64 "* ]]; then
  rerun_cpp sram5_pr64 sram22_pr64 memcelltype=1 technode=5 levelOutput=16 cellBit=1
  rerun_cpp sram1_pr64 sram22_pr64 memcelltype=1 technode=1 levelOutput=16 cellBit=1
fi
python3 "$TOOLS/parse_baseline.py" "$LOGS" "$OUT/baseline_reproduction.csv"
