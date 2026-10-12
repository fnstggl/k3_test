"""Single registry of every physical / economic parameter used by the models.

Each entry: id -> dict(pess, real, opt, unit, evidence, source, note).
`evidence` classes:
  measured_silicon | vendor_spec | peer_reviewed_sim | preprint_sim | derived |
  sim_run (produced by a simulator run in this repo) | assumption | speculative
results/physical_assumptions.csv is generated from this table
(scripts/run_all.py), so every number in the architecture models is visible.
`None` = unknown (the models refuse to use it).
"""
from __future__ import annotations

import csv

P = {}


def reg(pid, pess, real, opt, unit, evidence, source, note=""):
    P[pid] = dict(pess=pess, real=real, opt=opt, unit=unit, evidence=evidence, source=source, note=note)


# =============================================================================== NAND (commodity)
reg("nand_tR_tlc", 50e-6, 40e-6, 34e-6, "s", "measured_silicon",
    "ISSCC 2021-23 dies via ComputerBase: Kioxia BiCS6 50, Samsung V7 40, SK hynix 238L 45, >300L 34 us",
    "commodity TLC page read latency (physical_parameters_sourced.csv)")
reg("nand_tR_slc", 30e-6, 22.5e-6, 15e-6, "s", "measured_silicon",
    "Flash-Cosmos (MICRO 2022, 160 real 48L chips): SLC-mode tR 22.5 us; tR = precharge 24 + sense 5 + discharge 10 us per sensing (Park ASPLOS 2021)")
reg("nand_tR_lowlat", 4e-6, 3e-6, 2e-6, "s", "measured_silicon",
    "Cheong ISSCC 2018 (Z-NAND 3 us); Kouchi ISSCC 2020/JSSC 2021 (XL-FLASH 128Gb SLC, 4 us)",
    "low-latency SLC NAND; Z-NAND areal density only 0.6 Gb/mm2")
reg("nand_page_bytes", 16384, 16384, 16384, "B", "vendor_spec", "commodity 3D NAND page")
reg("nand_planes_per_die", 4, 6, 6, "-", "vendor_spec", "commodity 1Tb TLC dies 4-6 planes")
reg("nand_qlc_density_gb_mm2", 20.0, 28.5, 28.5, "Gb/mm2", "measured_silicon",
    "Jung ISSCC 2024 280-layer 1Tb QLC 28.5 Gb/mm2 (cited in LLM-on-the-Palm ref [9])")
reg("onfi_bw_bps_per_die", 3.6e9 * 8 / 4, 4.8e9 * 8 / 2, 4.8e9 * 8, "bit/s", "vendor_spec",
    "ONFI 5.x / Toggle 3600-4800 MT/s x8 shared by 4/2/1 dies per channel")
reg("onfi_latency_s", 200e-9, 100e-9, 50e-9, "s", "assumption", "command/protocol overhead per transfer")
reg("onfi_pj_per_bit", 10.0, 5.0, 3.0, "pJ/bit", "assumption", "NAND I/O energy (to be replaced by sourced value)")

# =============================================================================== NAND analog PIM array
reg("pim_plane_rows", 256, 256, 256, "BLS rows", "preprint_sim", "Jang et al. arXiv 2511.12860 (plane 256x2048x128)")
reg("pim_plane_cols", 2048, 2048, 2048, "BLs", "preprint_sim", "arXiv 2511.12860")
reg("pim_plane_stacks", 128, 128, 128, "WL layers", "preprint_sim", "arXiv 2511.12860")
reg("pim_contributors", 128, 128, 256, "rows/conversion", "preprint_sim",
    "arXiv 2511.12860 uses 128 BLSs; 3D-FPIM limits QLC to 256 cells per BL")
reg("pim_density_gb_mm2", 6.0, 12.84, 12.84, "Gb/mm2 (QLC)", "preprint_sim",
    "arXiv 2511.12860: 12.84 Gb/mm2 for 256x2048x128; pess halves it for ADC/periphery overflow")
reg("pim_t_op_8b_s", 20e-6, 2e-6, 1e-6, "s", "preprint_sim",
    "arXiv 2511.12860 Fig.6a ~2us for 8b input 8b weight QLC; pess ~ commodity-geometry PIM",
    "used for cross-checking the component model below")
reg("pim_t_wl_s", 2.0e-6, 0.80e-6, 0.30e-6, "s", "sim_run",
    "3D-FPIM NVSim with sourced geometry: RowDec(SR)-RowDec(CR) = 869-64 ns for 256x2048x128 (data/sim_outputs/fpim); "
    "opt = Shim MEMSYS 2020 WL setup 303 ns; pess = 2.5x NVSim (geometry confidence low)")
reg("pim_t_step_fixed_s", 500e-9, 64e-9, 32e-9, "s", "sim_run",
    "3D-FPIM NVSim RowDec(CR)/InputPrecision = 64 ns/bit-step for 256x2048x128; pess = Shim MEMSYS 2020 "
    "source-line settling 530-750 ns; opt = half of NVSim")
reg("pim_t_unit_s", 2e-9, 1e-9, 0.5e-9, "s", "peer_reviewed_sim", "3D-FPIM InputDuration 1 ns (MICRO 2022)")
reg("pim_i_cell_max_a", 50e-9, 50e-9, 200e-9, "A", "peer_reviewed_sim", "3D-FPIM cell file MaxCellReadCurrent 50 nA")
reg("pim_v_bl", 0.5, 0.2, 0.2, "V", "peer_reviewed_sim", "3D-FPIM PrechargeVoltage 0.2 V")
reg("pim_e_wl_per_op_j", 2.0e-9, 0.78e-9, 0.3e-9, "J", "sim_run",
    "3D-FPIM NVSim Row Decoder Energy (SR) 779.6 pJ per op (printed with a 'fJ' label; value is pJ)")
reg("pim_e_bl_per_step_j", 50e-15, 25e-15, 10e-15, "J/BL", "sim_run",
    "3D-FPIM NVSim 'CELL + Others' 51.2 pJ per 1-bit step / 2048 BL")
reg("pim_e_input_driver_j", 3e-12, 1.4e-12, 0.5e-12, "J/BLS toggle", "sim_run",
    "3D-FPIM NVSim Row Decoder Energy (CR) 22.1 pJ per step / (256 rows x 0.0625 activity)")
reg("pim_adcs_per_plane", 64, 128, 512, "-", "assumption",
    "arXiv 2511.12860 implies 512 (2048 BL / 4:1 mux); area-limited designs use fewer")

# =============================================================================== ADC
reg("adc_fom_j_per_step", 23e-15, 6.5e-15, 1.8e-15, "J/conv-step", "measured_silicon/sim_run",
    "pess: Murmann survey 5-8b SAR <=40nm up to 6 pJ/conv; real: ISAAC 8b 1.67 pJ (6.5 fJ/step); "
    "opt: NeuroSim V1.4 22nm SAR 8b 0.47 pJ/conv (data/sim_outputs/neurosim)",
    "thermal floor 8kT*SNR = 3.2 fJ per conversion at 8 bits (Murmann ISSCC 2022 SC)")
reg("adc_bit_cycle_s", 5e-9, 2e-9, 1e-9, "s/bit", "measured_silicon", "SAR ADC 50-200 MS/s class at 22-28nm")
reg("adc_area_fixed_m2", 300e-12, 200e-12, 100e-12, "m2", "measured_silicon/sim_run",
    "pess anchored to ISAAC Table I (8b SAR 0.0012 mm2 @32nm, 1.2 GS/s); opt anchored to NeuroSim V1.4 22nm SAR "
    "(5/6/8b: 124/143/180 um2); real = between")
reg("adc_area_per_level_m2", 3.5e-12, 1.0e-12, 0.3e-12, "m2/level", "measured_silicon/sim_run",
    "CDAC growth per LSB level: 8b -> pess 1196, real 456, opt 177 um2; 12b -> 14.6k / 4.3k / 1.3k um2")

# =============================================================================== die / package interconnect
reg("die_link_bw_bps", 28.8e9, 512e9, 4e12, "bit/s per die", "vendor_spec/assumption",
    "pess ONFI-class; real TSV stacked NAND (HBF-like, 1024-bit @ 4 Gb/s per 8 dies); opt hybrid bonding")
reg("die_link_latency_s", 200e-9, 30e-9, 10e-9, "s", "assumption", "link + protocol latency per transfer")
reg("die_link_pj_per_bit", 8.0, 0.5, 0.05, "pJ/bit", "vendor_spec/assumption",
    "pess = ONFI-class (energy unknown, assumed); real = UCIe 0.25-0.5 pJ/b; opt = hybrid bonding <0.05 pJ/b (vendor claim)")
reg("pkg_hop_latency_s", 200e-9, 50e-9, 20e-9, "s", "assumption",
    "inter-package SerDes/retimer hop between memory packages and the orchestrator (per direction)")
reg("orch_in_bw_bps", 200e9, 4e12, 20e12, "bit/s", "assumption", "aggregate ingress bandwidth of orchestrator die")
reg("htree_levels", 10, 8, 8, "-", "preprint_sim", "H-tree across 256 planes (arXiv 2511.12860)")
reg("t_htree_hop_s", 4e-9, 2e-9, 1e-9, "s", "preprint_sim", "RPU at 250 MHz in arXiv 2511.12860 (4 ns)")

# =============================================================================== orchestrator / attention engine
reg("orch_op_latency_s", 300e-9, 80e-9, 30e-9, "s", "assumption",
    "fixed latency of one global reduction/elementwise op incl. gather & sync")
reg("orch_vec_ops", 2e11, 1e12, 4e12, "op/s", "assumption", "vector unit throughput")
reg("orch_pj_per_op", 2.0, 1.0, 0.5, "pJ/op", "measured_silicon", "Horowitz ISSCC 2014 scaled (BF16 add/mul)")
reg("attn_flops", 50e12, 200e12, 1000e12, "FLOP/s", "vendor_spec/assumption",
    "attention engine: edge NPU (pess) / mid ASIC (real) / B200-class (opt)")
reg("attn_pj_per_flop", 1.0, 0.5, 0.3, "pJ/FLOP", "measured_silicon", "BF16/FP8 tensor math incl. SRAM")
reg("kv_bw_Bps", 136e9, 1.0e12, 8e12, "B/s", "vendor_spec",
    "LPDDR5X 2ch / 16ch-or-1 HBM3E stack / B200-class HBM")
reg("kv_pj_per_bit", 6.0, 4.0, 3.5, "pJ/bit", "measured_silicon", "LPDDR5X ~4-6 pJ/b, HBM3E ~3.5-4 pJ/b")
reg("kda_state_bw_Bps", 136e9, 2e12, 20e12, "B/s", "assumption",
    "KDA state (449 MB fp32) in DRAM (pess) / large SRAM (opt)")
reg("kda_state_pj_per_bit", 6.0, 1.0, 0.3, "pJ/bit", "measured_silicon", "DRAM vs SRAM access energy")
reg("kda_flops", 5e12, 20e12, 100e12, "FLOP/s", "assumption", "KDA recurrence vector throughput")
reg("embed_latency_s", 30e-6, 200e-9, 100e-9, "s", "assumption",
    "embedding row fetch: NAND page read (pess) vs DRAM (real/opt)")
reg("host_latency_s", 10e-6, 1e-6, 0.2e-6, "s", "assumption", "per-token sampling/host loop")

# =============================================================================== digital near-array logic
reg("plane_mac_rate", 0.4e9, 2e9, 16e9, "MAC/s per plane", "peer_reviewed_sim",
    "LLM-on-the-Palm: 1 BF16 MAC @400 MHz per plane (pess); wider SIMD for real/opt")
reg("e_mac_j", 1.5e-12, 1.0e-12, 0.32e-12, "J/MAC", "measured_silicon/derived",
    "TPUv4i Table 2 (7nm): BF16 mul 0.21 + add 0.11 pJ = 0.32 pJ (opt, CBA-bonded advanced CMOS); x3-5 for NAND CuA CMOS")
reg("e_page_read_j", 2.0e-6, 0.6e-6, 0.1e-6, "J/16KB page", "derived",
    "VCC 3.3V x ICC 70mA (LLM-on-the-Palm Table I) x tR / planes; short-BL designs lower")
reg("e_shiftadd_per_conv_j", 0.5e-12, 0.2e-12, 0.05e-12, "J", "assumption", "digital shift-add per ADC sample")
reg("digital_scale_latency_s", 20e-9, 8e-9, 4e-9, "s", "assumption", "MX scale multiply + accumulate")
reg("a2_cell_density_g_mm2", 0.6, 3.21, 3.21, "Gcell/mm2 (SLC)", "measured_silicon/preprint_sim",
    "pess = Samsung Z-NAND (only shipped 3us-tR SLC NAND) 0.6 Gb/mm2; real/opt = small-plane geometry of arXiv 2511.12860 "
    "(12.84 Gb/mm2 QLC -> 3.21 Gcell/mm2)")
reg("sa_area_m2", 40e-12, 15e-12, 5e-12, "m2/sense amp", "assumption",
    "page buffer + SA per BL in CuA (to be replaced by sourced value)")

# =============================================================================== RRAM / FeNAND
reg("rram_density_gb_mm2", 0.2, 0.6, 2.0, "Gb/mm2", "measured_silicon/speculative",
    "embedded 1T1R RRAM macros (~0.2-0.6); 2-deck 3D XPoint 0.62; vertical RRAM only up to 8 layers demonstrated (opt speculative)",
    "NeuRRAM: 1-40 uS, post-program relaxation sigma 2.8 uS -> 3-4 effective bits")
reg("rram_t_op_s", 817e-9, 261e-9, 110e-9, "s", "sim_run",
    "NeuroSim V1.4 22nm 1T1R 256x256, 8-bit bit-serial MVM: SAR-8b 817 ns (pess), flash-8b 261 ns (real), flash-5b 110 ns (opt)")
reg("rram_e_op_j", 1.27e-9, 2.51e-9, 0.47e-9, "J per 256x256 MVM", "sim_run",
    "NeuroSim V1.4 22nm: SAR-8b 1.27 nJ, flash-8b 2.51 nJ, flash-5b 0.47 nJ per 8-bit-input MVM (incl. ADC, shift-add)")
reg("rram_cells_per_mm2", 3.4e6, 3.4e6, 0.6e9, "cells/mm2 incl. periphery", "sim_run/measured_silicon",
    "NeuroSim 22nm 1T1R subarray 256x256 (2-bit) = 0.0188-0.0193 mm2 incl. ADC/periphery (pess/real); "
    "opt = 2-deck 3D XPoint array density 0.62 Gb/mm2 with pooled ADCs (speculative for analog CIM)")
reg("fenand_t_wl_s", 2e-6, 0.4e-6, 0.2e-6, "s", "speculative", "assumed similar to NAND PIM, lower Vpass")
reg("fenand_density_gb_mm2", 3.0, 10.0, 12.84, "Gb/mm2", "speculative", "no product; research FeNAND arrays")

reg("nvm_die_static_w", 0.02, 0.005, 0.002, "W/die", "assumption",
    "active-idle power of a memory die with charge pumps kept up for us-scale ops (standby ICC2 is uA-level)")
reg("dies_per_package", 8, 16, 16, "dies", "vendor_spec/assumption", "BGA316 allows up to 32 dies (arXiv 2511.12860); HBM-like stacks 8-16")

# =============================================================================== SRAM-KV attention engines (hypothetical)
reg("sram_kv_pj_per_bit", 0.2, 0.2, 0.2, "pJ/bit", "assumption",
    "on-die SRAM read incl. local wiring, 0.1-0.3 pJ/bit typical for 5/3nm macros; used by engines sram_a/b/c")
reg("sram_leak_w_per_gb", 5.0, 5.0, 5.0, "W/GB", "assumption",
    "retention-biased HD SRAM leakage ~5 mW/MB (unsourced); charged per GB of KV+KDA state held on die")
reg("fp8_attn_pj_per_flop", 0.25, 0.25, 0.25, "pJ/FLOP", "assumption",
    "FP8 attention math at half the BF16 energy; FP8 KV/attention unvalidated for K3")
reg("fp8_attn_area_factor", 0.5, 0.5, 0.5, "x", "assumption",
    "FP8 tensor datapath area per FLOP/s relative to BF16 (B200: FP8 dense = 2x BF16 dense throughput)")

# =============================================================================== costs (USD) -- unknown unless sourced
reg("nand_wafer_cost_usd", None, None, None, "USD/300mm wafer", "unknown", "filled from cost_parameters_sourced.csv")
reg("nand_cost_per_gb_usd", None, None, None, "USD/GB", "unknown", "filled from cost_parameters_sourced.csv")


def get(pid, scen):
    v = P[pid][scen]
    if v is None:
        raise ValueError(f"parameter {pid} is unknown for scenario {scen}")
    return v


def export_csv(path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["param_id", "pessimistic", "realistic", "optimistic", "unit", "evidence_class", "source", "note"])
        for k, d in P.items():
            w.writerow([k, d["pess"], d["real"], d["opt"], d["unit"], d["evidence"], d["source"], d["note"]])
