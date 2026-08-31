#!/usr/bin/env bash
# Reproducible third-party clones pinned to third_party/LOCK.md SHAs.
set -euo pipefail
cd "$(dirname "$0")/../third_party"
clone() { # url sha [sparse_dirs...]
  local url=$1 sha=$2 name; name=$(basename "$url" .git); shift 2
  if [ -d "$name/.git" ]; then echo "exists: $name"; return; fi
  if [ $# -gt 0 ]; then
    git clone --depth=1 --filter=blob:none --sparse "$url"
    (cd "$name" && git sparse-checkout set "$@")
  else
    git clone --depth=1 "$url"
  fi
  (cd "$name" && git fetch --depth=1 origin "$sha" 2>/dev/null && git checkout "$sha" 2>/dev/null) || \
    echo "note: $name at $(cd "$name" && git rev-parse HEAD); LOCK.md pin $sha (update LOCK.md if drifted)"
}
clone https://github.com/MoatLab/FEMU.git            34bbe45fa74b0be22e93e3602f1c26a0f121fa9e
clone https://github.com/CMU-SAFARI/MQSim.git        51f0f2d3fed92d88ef4a0fa61a38024b07bf9d16
clone https://github.com/umd-memsys/DRAMsim3.git     29817593b3389f1337235d63cac515024ab8fd6e
clone https://github.com/MoonshotAI/Kimi-K3.git      3cb39dfd32e51c3328e2e4b4af21341247d06c43
clone https://github.com/vllm-project/recipes.git    497730755c756cbcfd7420540e4bea9d62360cfe
clone https://github.com/vllm-project/vllm.git       7ab29234890b29b005e46b53037309e597425095 vllm/model_executor vllm/models
