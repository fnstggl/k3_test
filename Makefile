# K3-on-NAND feasibility study — reproduction entry points.
# Each target regenerates its results from a fresh checkout (see README.md).

PY := python3
SCRATCH ?= /tmp/k3nand-scratch

.PHONY: setup test reproduce-palm k3 primitive sweep economics rtl femu-smoke report all

setup:
	$(PY) -m pip install -r requirements.txt
	bash scripts/clone_third_party.sh
	$(MAKE) -C third_party/MQSim -j4 || true
	@echo "Optional (Gate 7/8): sudo apt-get install verilator yosys busybox-static nvme-cli zstd"

test:
	$(PY) -m pytest tests/ -q

reproduce-palm:
	$(PY) experiments/reproduce_palm.py

k3:
	$(PY) experiments/k3_baseline.py

primitive:
	$(PY) experiments/primitive_search.py

sweep:
	$(PY) experiments/sweep.py

economics:
	$(PY) experiments/economics.py

mqsim:
	cd experiments/mqsim && ../../third_party/MQSim/MQSim -i ssdconfig_znand.xml -w workload_seqread.xml

rtl:
	cd rtl && verilator --lint-only -Wall k3_nand_reducer.sv
	cd rtl && verilator --cc --exe --build -O3 -Wall k3_nand_reducer.sv tb/tb_reducer.cpp -o tb_reducer
	mkdir -p $(SCRATCH)
	cd rtl && for seed in 1 2 3; do \
	  $(PY) golden_model.py 400000 $$seed $(SCRATCH)/vec_$$seed.txt && \
	  ./obj_dir/tb_reducer $(SCRATCH)/vec_$$seed.txt || exit 1; done
	cd rtl/synth && test -s sky130_hd_tt.lib || curl -sSL -o sky130_hd_tt.lib \
	  https://raw.githubusercontent.com/The-OpenROAD-Project/OpenROAD-flow-scripts/master/flow/platforms/sky130hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib
	cd rtl/synth && yosys -q synth.ys && tail -5 stat.txt

femu-build:
	cd third_party/FEMU && mkdir -p build-femu && cd build-femu && \
	  cp ../femu-scripts/femu-copy-scripts.sh . && ./femu-copy-scripts.sh . >/dev/null && \
	  sudo ./pkgdep.sh && ./femu-compile.sh

femu-guest:
	bash scripts/femu_guest_run.sh

report: test reproduce-palm k3 primitive sweep economics
	@echo "All simulation results regenerated under results/."

all: setup test reproduce-palm k3 primitive sweep economics rtl
