#!/usr/bin/env bash
# Cross-check: subarray_driver vs. the stock NeuroSim main.cpp chip flow, same Param.cpp
# (RRAM 22 nm 1T1R, 128x128, 5-bit flash ADC, 1b cells, 8b weights/inputs).
#
# The stock floorplanner refuses a layer that fits in one subarray ("SubArray Size is too large,
# which break the chip hierarchey"), so the stock run uses one FC layer of 1024 inputs x 128
# outputs = 1024 x 1024 cells = 64 full 128x128 subarrays, with uniform-random 8b weights and
# Bernoulli(0.5) input bits (same statistics the driver uses, different random draws).
# Comparable quantities:
#   * sensing clock period (data independent)          -> must match exactly
#   * chip "ADC (...) readDynamicEnergy" = sum over subarrays of SubArray::readDynamicEnergyADC
#     (no PE/tile/chip-level contribution)              -> /64 should be close to driver's value
#   * chip "Total ADC Area" / #subarrays on chip         -> should match driver areaADC
# Usage: crosscheck_main.sh <driver build dir> <pristine Param.cpp> <NeuroSim repo> <out dir>
set -euo pipefail
B=$1; PRISTINE=$2; REPO=$3; OUT=$4
TOOLS=$(cd "$(dirname "$0")" && pwd)
W=$B/crosscheck; rm -rf "$W"; mkdir -p "$W"
LOG=$OUT/logs/crosscheck_driver_vs_main.log
cd "$B/src"
python3 "$TOOLS/set_param.py" "$PRISTINE" Param.cpp memcelltype=2 technode=22 numRowSubArray=128 numColSubArray=128 levelOutput=32 cellBit=1 > "$LOG"
g++ -c -fopenmp -O3 -std=c++0x -w Param.cpp -o Param.o
cp "$TOOLS/subarray_driver.cpp" . && g++ -c -fopenmp -O3 -std=c++0x -w subarray_driver.cpp -o subarray_driver.o
OBJS=$(ls *.o | grep -v -e '^Param.o$' -e '^subarray_driver.o$')
g++ -fopenmp -O3 -std=c++0x -w $OBJS subarray_driver.o Param.o -o "$W/driver"
git -C "$REPO" show HEAD:Inference_pytorch/NeuroSIM/main.cpp > "$W/main.cpp"
g++ -c -fopenmp -O3 -std=c++0x -w -I. "$W/main.cpp" -o "$W/main.o"
g++ -fopenmp -O3 -std=c++0x -w $OBJS "$W/main.o" Param.o -o "$W/main"
echo "1,1,1024,1,1,128,0,1" > "$W/NetWork_FC1024x128.csv"   # 8th column = stride (Chip.cpp netStructure[l][7])
python3 - "$W" <<'EOF'
import sys, numpy as np
w = sys.argv[1]; rng = np.random.default_rng(1)
v = rng.integers(0, 256, size=(1024, 128))            # 8b weight integers, Chip.cpp maps round(128*(f+1)) -> v
np.savetxt(w + '/fc_weight.csv', v / 128.0 - 1.0, delimiter=',', fmt='%.7f')
np.savetxt(w + '/fc_input.csv', (rng.random((1024, 8)) < 0.5).astype(int), delimiter=',', fmt='%d')
EOF
{ echo "=== driver (128x128, one subarray) ==="; "$W/driver";
  echo; echo "=== stock main: ./main NetWork_FC1024x128.csv 8 8 128 128 fc_weight.csv fc_input.csv ===";
  cd "$W" && ./main NetWork_FC1024x128.csv 8 8 128 128 fc_weight.csv fc_input.csv; } >> "$LOG" 2>&1
python3 - "$LOG" <<'EOF' | tee -a "$LOG"
import json, re, sys
t = open(sys.argv[1]).read()
d = json.loads(re.search(r'RESULT_JSON (\{.*\})', t).group(1))
m = t.split('=== stock main')[1]
clk = float(re.search(r'clkPeriod: ([0-9.eE+-]+)', m).group(1)) * 1e9
eadc = float(re.search(r'ADC \(or S/As and precharger for SRAM\) readDynamicEnergy is : ([0-9.eE+-]+)pJ', m).group(1))
aadc = float(re.search(r'Total ADC \(or S/As and precharger for SRAM\) Area on chip : ([0-9.eE+-]+)um\^2', m).group(1))
aarr = float(re.search(r'Chip total CIM array : ([0-9.eE+-]+)um\^2', m).group(1))
nsub = aarr / d['area_breakdown_um2']['array']
print('\n=== CROSS-CHECK SUMMARY ===')
print('sensing clock period: driver %.6f ns | stock main %.6f ns | diff %.4f %%' % (d['sensingCycle_ns'], clk, 100 * (clk - d['sensingCycle_ns']) / d['sensingCycle_ns']))
print('subarrays on chip (CIM array area / driver array area): %.2f' % nsub)
print('ADC area per subarray: driver %.3f um2 | stock main %.3f um2' % (d['area_breakdown_um2']['neurosim_cat_ADC'], aadc / nsub))
print('subarray "ADC" energy category per subarray (64 subarrays hold the 1024x1024-cell matrix): driver %.3f pJ | stock main %.3f pJ (= %.3f / 64) | diff %.2f %% (different random draws, same statistics)'
      % (d['energyADCcat_pJ'], eadc / 64, eadc, 100 * (eadc / 64 - d['energyADCcat_pJ']) / d['energyADCcat_pJ']))
EOF
echo "wrote $LOG"
