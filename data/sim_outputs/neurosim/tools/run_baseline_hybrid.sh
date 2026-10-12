#!/usr/bin/env bash
# HYBRID-trace C++ re-run for one Table VII config whose faithful (--inference 1) wrapper run produced all conv-layer
# traces but was killed in the FC layer: conv-layer traces from the --inference 1 copy, FC traces from the
# --inference 0 copy (weights are identical in both; only activations differ). Runs the HEAD C++ (from the _inf0
# copy) and the original-upload C++ (6a6073d build made by run_baseline_oldcode.sh).
# Usage: run_baseline_hybrid.sh <ext dir> <output dir> [tag=rram22_pr64]
set -euo pipefail
EXT=${1:?ext}; OUT=${2:?out}; TAG=${3:-rram22_pr64}
C=$EXT/wrap_copies; L=$OUT/logs/baseline; H=$C/${TAG}_hyb
rm -rf "$H"; mkdir -p "$H/layer_record_VGG8"
cp "$C/${TAG}_inf0/layer_record_VGG8/"* "$H/layer_record_VGG8/"
for l in Conv0 Conv1 Conv3 Conv4 Conv6 Conv7; do
  cp "$C/$TAG/layer_record_VGG8/weight${l}_.csv" "$C/$TAG/layer_record_VGG8/input${l}_.csv" "$H/layer_record_VGG8/"
done
mem=${TAG%%_*}   # rram22 / sram22
run () {  # $1 = log tag, $2 = main binary dir
  local tag=$1 d=$2 cmd start
  cmd=$(sed "s#\./layer_record_VGG8/#$H/layer_record_VGG8/#g; s#\./NeuroSIM/main#$d/main#; s#\./NeuroSIM/NetWork_VGG8.csv#$d/NetWork_VGG8.csv#" "$H/layer_record_VGG8/trace_command.sh")
  start=$(date +%s)
  ( echo "# HYBRID traces: --inference 1 traces for the 6 conv layers from $C/$TAG, --inference 0 traces for FC0/FC1 from $C/${TAG}_inf0; C++ = $d/main"
    echo "# command: $cmd"; cd "$d" && bash -c "$cmd"; echo "# exit=$? wall_seconds=$(( $(date +%s) - start ))" ) > "$L/$tag.log" 2>&1
}
run ${TAG}_hyb "$C/${TAG}_inf0/NeuroSIM" &
run ${TAG}_hyb_code6a6073d "$EXT/neurosim_v14_6a6073d_${mem}" &
wait
