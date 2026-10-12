#!/usr/bin/env bash
# Re-run the Table VII C++ estimates with the ORIGINAL V1.4 upload of the C++ core (commit 6a6073d, 2024-10-04),
# i.e. before the later model changes on the branch:
#   4b95797 2024-10-31 SubArray.cpp  "area floor planning with less empty area" (WL switch matrix / level shifters
#                                    are now laid out along the full subarray height)
#   598879a 2025-02-26 MultilevelSenseAmp.cpp  clamp negative column power to 0
#   1c608ea 2025-04-15 ProcessingUnit.cpp      zero-conductance column -> 1e10 ohm
#   8a88abf 2025-10-26 main.cpp                temperature warning
# Table VII is dated 9/27/23 and the git history of the branch starts 2024-10-04, so 6a6073d is the oldest code
# available. Same Param.cpp knobs (Param.cpp is identical in both commits), same trace files.
#
# Usage: run_baseline_oldcode.sh <NeuroSim_V1.4 checkout> <output dir> <trace-suffix: "" or "_inf0">
set -euo pipefail
REPO=${1:?repo}; OUT=${2:?out}; SUF=${3-}
OLD=6a6073d
TOOLS=$(cd "$(dirname "$0")" && pwd)
EXT=$(dirname "$REPO")
COPIES=$EXT/wrap_copies
LOGS=$OUT/logs/baseline
build_old () {  # $1 = build dir, $2 = build log, rest = knobs   (skipped if already built)
  local d=$1 log=$2; shift 2
  if [[ ! -x $d/main ]]; then
    rm -rf "$d"; mkdir -p "$d"
    git -C "$REPO" archive $OLD Inference_pytorch/NeuroSIM | tar -x -C "$d" --strip-components=2
    git -C "$REPO" show $OLD:Inference_pytorch/NeuroSIM/Param.cpp > "$d/Param.cpp.pristine"
    { python3 "$TOOLS/set_param.py" "$d/Param.cpp.pristine" "$d/Param.cpp" "$@"; (cd "$d" && make -j2 2>&1 | tail -1); } > "$log"
  fi
}
run_old () {    # $1 = out tag, $2 = trace dir tag, $3 = build dir
  local tag=$1 ttag=$2 d=$3 cmd start
  [[ -f $COPIES/$ttag/layer_record_VGG8/trace_command.sh ]] || { echo "skip $tag: no traces in $ttag"; return 0; }
  grep -q "^# exit=0" "$LOGS/$ttag.log" 2>/dev/null || { echo "skip $tag: $ttag did not finish"; return 0; }
  grep -q "^# exit=0" "$LOGS/${tag}_code$OLD.log" 2>/dev/null && { echo "skip $tag: already done"; return 0; }
  cmd=$(sed "s#\./layer_record_VGG8/#$COPIES/$ttag/layer_record_VGG8/#g; s#\./NeuroSIM/main#$d/main#; s#\./NeuroSIM/NetWork_VGG8.csv#$d/NetWork_VGG8.csv#" "$COPIES/$ttag/layer_record_VGG8/trace_command.sh")
  start=$(date +%s)
  ( echo "# NeuroSim V1.4 C++ at commit $OLD (original upload), traces from $ttag"; echo "# command: $cmd"
    cd "$d" && bash -c "$cmd"; echo "# exit=$? wall_seconds=$(( $(date +%s) - start ))" ) > "$LOGS/${tag}_code$OLD.log" 2>&1
}
B=$EXT/neurosim_v14_${OLD}
build_old ${B}_rram22 "$LOGS/rram22_code$OLD.build.log" memcelltype=2 technode=22 levelOutput=16 cellBit=1
build_old ${B}_sram22 "$LOGS/sram22_code$OLD.build.log" memcelltype=1 technode=22 levelOutput=16 cellBit=1
build_old ${B}_sram5  "$LOGS/sram5_code$OLD.build.log"  memcelltype=1 technode=5  levelOutput=16 cellBit=1
build_old ${B}_sram1  "$LOGS/sram1_code$OLD.build.log"  memcelltype=1 technode=1  levelOutput=16 cellBit=1
for pr in 64 32; do
  run_old rram22_pr${pr}$SUF rram22_pr${pr}$SUF ${B}_rram22
  run_old sram22_pr${pr}$SUF sram22_pr${pr}$SUF ${B}_sram22
  run_old sram5_pr${pr}$SUF  sram22_pr${pr}$SUF ${B}_sram5
  run_old sram1_pr${pr}$SUF  sram22_pr${pr}$SUF ${B}_sram1
done
echo "old-code runs done ($SUF)"
