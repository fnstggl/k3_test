"""Architecture definitions (A-G + baselines) x scenarios (pess / real / opt).

Each builder returns a flat dict consumed by k3cim.scheduler.Scheduler and by
k3cim.cost.  Silicon classes (requested distinction for NAND):

  commodity          unmodified, shipping silicon used through standard commands
  modified_periphery commodity-like array/plane geometry, new peripheral circuits
                     (multi-block WL activation, ADCs, near-plane logic)
  redesigned_array   new plane geometry (small planes, short BLs/WLs, many ADCs,
                     TSV/hybrid-bonded high-bandwidth die interface)
  research_device    device technology without volume products (3D RRAM CIM, FeNAND)
  existing_product   GPUs (measured)

Capacity is derived from the real K3 tensor list (k3cim.workload): every stored
weight is mapped to cells according to the representation (slices,
differential pairs, alignment bits) and a spare/redundancy factor.
"""
from __future__ import annotations

import math

from . import params as PR
from .scheduler import adc_area_m2
from .workload import K3Workload

SCEN = ("pess", "real", "opt")


def g(pid, s):
    return PR.get(pid, s)


# ----------------------------------------------------------------------------- common pieces
ATTN_ENGINES = {
    # name: sustained attention FLOP/s, KV bandwidth, KDA-state location/bandwidth, silicon basis
    "edge": dict(orch_static_w=2.0, attn_flops=50e12, kv_bw_Bps=136e9, kda_state_bw_Bps=136e9, kda_state_pj_per_bit=6.0,
                 kv_pj_per_bit=6.0, kda_flops=5e12, kv_mem="LPDDR5X x2ch", kda_in="DRAM"),
    "mid": dict(orch_static_w=10.0, attn_flops=200e12, kv_bw_Bps=1.0e12, kda_state_bw_Bps=4e12, kda_state_pj_per_bit=0.5,
                kv_pj_per_bit=4.0, kda_flops=20e12, kv_mem="LPDDR5X x16ch or 1 HBM3E stack", kda_in="SRAM 449MB"),
    "mid2": dict(orch_static_w=25.0, attn_flops=600e12, kv_bw_Bps=3.0e12, kda_state_bw_Bps=8e12,
                 kda_state_pj_per_bit=0.5, kv_pj_per_bit=3.5, kda_flops=50e12, kv_mem="3 HBM3E stacks",
                 kda_in="SRAM 449MB"),
    "mid3": dict(orch_static_w=50.0, attn_flops=1500e12, kv_bw_Bps=6.0e12, kda_state_bw_Bps=10e12,
                 kda_state_pj_per_bit=0.5, kv_pj_per_bit=3.5, kda_flops=100e12, kv_mem="5 HBM3E stacks",
                 kda_in="SRAM 449MB"),
    "high": dict(orch_static_w=150.0, attn_flops=1000e12, kv_bw_Bps=8e12, kda_state_bw_Bps=8e12, kda_state_pj_per_bit=3.5,
                 kv_pj_per_bit=3.5, kda_flops=100e12, kv_mem="HBM3E (B200-class)", kda_in="HBM"),
    "xhigh": dict(orch_static_w=600.0, attn_flops=4000e12, kv_bw_Bps=32e12, kda_state_bw_Bps=32e12, kda_state_pj_per_bit=3.5,
                  kv_pj_per_bit=3.5, kda_flops=400e12, kv_mem="HBM3E (4x B200-class)", kda_in="HBM"),
}


def orchestrator(s, engine=None):
    d = _orchestrator_base(s)
    if engine:
        d.update({k: v for k, v in ATTN_ENGINES[engine].items()})
        d["attn_engine"] = engine
    else:
        d["attn_engine"] = {"pess": "edge", "real": "mid", "opt": "high"}[s]
        d.update({k: v for k, v in ATTN_ENGINES[d["attn_engine"]].items()})
    return d


def _orchestrator_base(s):
    return dict(
        orch_op_latency_s=g("orch_op_latency_s", s), orch_vec_ops=g("orch_vec_ops", s),
        orch_pj_per_op=g("orch_pj_per_op", s), attn_flops=g("attn_flops", s),
        attn_pj_per_flop=g("attn_pj_per_flop", s), kv_bw_Bps=g("kv_bw_Bps", s),
        kv_pj_per_bit=g("kv_pj_per_bit", s), kda_state_bw_Bps=g("kda_state_bw_Bps", s),
        kda_state_pj_per_bit=g("kda_state_pj_per_bit", s), kda_flops=g("kda_flops", s),
        embed_latency_s=g("embed_latency_s", s), host_latency_s=g("host_latency_s", s),
        orch_in_bw_bps=g("orch_in_bw_bps", s), digital_scale_latency_s=g("digital_scale_latency_s", s),
        htree_levels=g("htree_levels", s), t_htree_hop_s=g("t_htree_hop_s", s),
        e_shiftadd_per_conv_j=g("e_shiftadd_per_conv_j", s),
        fold_norm_scale=(s == "opt"), kv_bytes=2.0 if s != "opt" else 1.0, kda_state_bytes=4.0,
        fused_mla_attention=True, nvm_die_static_w=g("nvm_die_static_w", s),
        dies_per_package=g("dies_per_package", s),
    )


def links(s, kind="die_link"):
    if kind == "onfi":
        bw, lat, e = g("onfi_bw_bps_per_die", s), g("onfi_latency_s", s), g("onfi_pj_per_bit", s)
    else:
        bw, lat, e = g("die_link_bw_bps", s), g("die_link_latency_s", s), g("die_link_pj_per_bit", s)
    lat = lat + g("pkg_hop_latency_s", s)          # die link + one package hop each way
    return dict(die_in_bw_bps=bw, die_in_latency_s=lat, die_in_pj_per_bit=e,
                die_out_bw_bps=bw, die_out_latency_s=lat, die_out_pj_per_bit=e)


def adc_params(s):
    return dict(adc_fom_j_per_step=g("adc_fom_j_per_step", s), adc_bit_cycle_s=g("adc_bit_cycle_s", s),
                adc_area_fixed_m2=g("adc_area_fixed_m2", s), adc_area_per_level_m2=g("adc_area_per_level_m2", s),
                adc_overhead_cycles=2)


def weight_cells(wl: K3Workload, expert_bits, dense_bits, cell_bits, differential):
    """Total cells to store all K3 linear weights (+embedding handled digitally)."""
    diff = 2 if differential else 1
    tot = 0
    for o in wl.linear_ops():
        b = expert_bits if o.wdtype == "mxfp4" else dense_bits
        tot += o.stored_weights * math.ceil(b / cell_bits) * diff
    return tot


def stored_bits_digital(wl: K3Workload, dense_bytes):
    tot = 0
    for o in wl.linear_ops():
        tot += o.stored_weights * (4.25 if o.wdtype == "mxfp4" else 8 * dense_bytes)
    return tot


def structured_expert_rounds(n_active, tiles_per_expert, n_arrays, n_experts, trials=400, seed=0):
    """Experts placed in 'slots' of tiles_per_expert distinct arrays; conflicts = several active
    experts sharing a slot. Returns E[max active experts per slot] (>=1)."""
    import numpy as np
    slots = max(1, n_arrays // max(1, tiles_per_expert))
    if slots >= n_experts:
        return 1.0
    rng = np.random.default_rng(seed)
    owner = np.arange(n_experts) % slots
    m = []
    for _ in range(trials):
        act = rng.choice(n_experts, n_active, replace=False)
        m.append(np.bincount(owner[act]).max())
    return float(np.mean(m))


# ============================================================================= analog NAND (B-E)
def analog_nand(s, encoding="B", silicon="redesigned_array", contributors=None, cell_bits=4,
                adcs_per_plane=None, adc_bits=None, dense_bits=8, name=None):
    wl = K3Workload(fold_mla=(s == "opt"))
    C = contributors or g("pim_contributors", s)
    bpp = {"B": 1, "C": 2, "D": 4, "E": 8}[encoding]
    expert_bits = 4 if C <= 32 else (5 if C <= 128 else 6)     # alignment bits measured on real K3 scales
    rows, cols, stacks = g("pim_plane_rows", s), g("pim_plane_cols", s), g("pim_plane_stacks", s)
    if silicon == "modified_periphery":
        # commodity-like plane geometry: long WLs / BLs -> commodity-class timing for every op
        cols = 16384 * 8
        rows = 1024
        t_wl = 20e-6 if s == "pess" else (10e-6 if s == "real" else 5e-6)
        t_step = 5e-6 if s == "pess" else (2e-6 if s == "real" else 1e-6)
    else:
        t_wl = g("pim_t_wl_s", s)
        t_step = g("pim_t_step_fixed_s", s)
    cells = weight_cells(wl, expert_bits, dense_bits, cell_bits, True) * 1.08   # 8% spare/calibration columns
    cells_per_plane = rows * cols * stacks
    planes = math.ceil(cells / cells_per_plane)
    adcs = adcs_per_plane or g("pim_adcs_per_plane", s)
    if adc_bits is None:
        adc_bits = {"B": 9, "C": 10, "D": 11, "E": 12}[encoding]
    # tiles per expert (stage B: w1 + w3), structured placement over all planes
    tiles_per_expert = math.ceil(2 * 3584 * 3072 * math.ceil(expert_bits / cell_bits) * 2 / (C * cols))
    rounds = structured_expert_rounds(16, tiles_per_expert, planes, 896)
    d = dict(
        family="analog_cim", tech="nand3d", encoding=encoding, silicon=silicon, scenario=s,
        name=name or f"{encoding}_nand_analog_{bpp}b_per_step_{silicon}",
        contributors=C, array_cols=cols, array_rows=rows, array_stacks=stacks, cell_bits=cell_bits,
        expert_w_mag_bits=expert_bits, dense_w_mag_bits=dense_bits, signed_mode="differential",
        analog_subtract=True, x_mag_bits=8, bits_per_pass=bpp, input_sign_phases=True,
        analog_accumulate_passes=(encoding == "E"), time_encoded_input=True,
        t_unit_s=g("pim_t_unit_s", s), t_dac_settle_s=50e-9, t_wl_s=t_wl, t_step_fixed_s=t_step,
        wl_exposed_frac_dense=0.0 if silicon == "redesigned_array" else 1.0, wl_exposed_frac_expert=1.0,
        adcs_per_array=adcs, adc_bits=adc_bits, psum_bits=adc_bits + 8,
        i_cell_max_a=g("pim_i_cell_max_a", s), v_bl=g("pim_v_bl", s), avg_level_frac=0.25, avg_input_bit_frac=0.3,
        e_wl_per_op_j=g("pim_e_wl_per_op_j", s), e_bl_per_step_j=g("pim_e_bl_per_step_j", s),
        e_input_driver_per_bit_j=g("pim_e_input_driver_j", s),
        arrays_total=planes, arrays_per_stage_limit=planes, expert_arrays_per_layer=planes,
        expert_rounds_override=rounds, dies_per_op=max(1, planes // 256),
        dies_total=max(1, math.ceil(planes / (256 if silicon != "modified_periphery" else 4))),
        bcast_fanout_share=1.0, cells_total=cells, planes=planes, planes_per_die=256 if silicon != "modified_periphery" else 4,
        density_gb_mm2=g("pim_density_gb_mm2", s), adc_util_max=0.5,
        static_power_w=2.0 + 0.002 * planes / 256,
        **adc_params(s), **orchestrator(s), **links(s, "die_link" if silicon == "redesigned_array" else "onfi"),
    )
    d["fold_mla"] = (s == "opt")
    return d


# ============================================================================= digital NAND (A)
def digital_nand(s, variant="A1"):
    wl = K3Workload(fold_mla=False)
    dense_bytes = 2.0
    bits = stored_bits_digital(wl, dense_bytes) * 1.12    # ECC/spare ~12%
    if variant == "A0":
        silicon, page = "commodity", g("nand_page_bytes", s)
        t_read = g("nand_tR_tlc", s)
        bits_per_cell = 3
        planes_per_die = g("nand_planes_per_die", s)
        die_bits = 1024 ** 4 * 8 / 8 * 1  # 1 Tb
        lk = links(s, "onfi")
        mac = 1e18          # external accelerator: compute is not the bound, I/O is
        e_page = g("e_page_read_j", s)
    elif variant == "A1":
        silicon, page = "modified_periphery", g("nand_page_bytes", s)
        t_read = g("nand_tR_slc", s) if s != "opt" else g("nand_tR_lowlat", s)
        bits_per_cell = 1
        planes_per_die = g("nand_planes_per_die", s) if s != "opt" else 16
        die_bits = 1024 ** 4 / 3 if s != "opt" else 256e9   # 1Tb TLC die used as SLC / XL-FLASH-class
        lk = links(s, "onfi")
        mac = g("plane_mac_rate", s)
        e_page = g("e_page_read_j", s)
    else:  # A2 redesigned: many small SLC planes (256 rows x 2048 BLs x S stacks), TSV-stacked, near-plane MAC
        silicon = "redesigned_array"
        cols = 2048
        stacks = {"pess": 128, "real": 64, "opt": 32}[s]
        page = cols // 8
        t_read = {"pess": g("nand_tR_lowlat", "pess"), "real": g("nand_tR_lowlat", "real"),
                  "opt": 0.5e-6}[s]   # opt: WL-reuse / BLS-scan sequential sensing (hypothetical)
        bits_per_cell = 1
        planes_per_die = 256
        die_bits = planes_per_die * 256 * cols * stacks
        lk = links(s, "die_link")
        # MAC rate sized to consume one page per t_read (BF16 worst case)
        mac = max(g("plane_mac_rate", s), (page / 2.0) / t_read)
        e_page = g("e_page_read_j", s) * page / 16384
    dies = math.ceil(bits / die_bits)
    planes = dies * planes_per_die
    d = dict(family="digital_nvm", tech="nand3d_digital", variant=variant, silicon=silicon, scenario=s,
             name=f"{variant}_digital_nand_{silicon}", page_bytes=page, t_read_s=t_read, planes_total=planes,
             dies=dies, planes_per_die=planes_per_die, bits_per_cell=bits_per_cell, plane_mac_rate=mac,
             e_mac_j=g("e_mac_j", s), e_page_read_j=e_page, dense_bytes_per_weight=dense_bytes,
             dense_read_exposed_frac=0.0, page_buffers_per_plane=2, psum_bits=24, dies_per_op=dies,
             stored_bits=bits, static_power_w=1.0 + 0.05 * dies, sa_count=planes * page * 8,
             dies_total=dies, sa_area_m2=g("sa_area_m2", s), cell_density_g_mm2=g("a2_cell_density_g_mm2", s),
             **orchestrator(s), **lk)
    if variant == "A0":
        d["weights_cross_io"] = True
    return d


# ============================================================================= 3D RRAM (F) / FeNAND (G)
def rram_3d(s):
    """3D/stacked RRAM CIM calibrated to NeuroSim V1.4 (22nm 1T1R, 256x256 subarrays).

    RRAM accepts bipolar read voltages, so signed inputs need no second phase (unlike NAND).
    pess/real: NeuroSim subarray density incl. per-array ADCs (no pooling);
    opt: crossbar (3D XPoint-class) density with a die-level ADC pool (speculative).
    """
    wl = K3Workload(fold_mla=(s == "opt"))
    cell_bits = 2 if s != "opt" else 3
    C = 256
    expert_bits = 6
    cells = weight_cells(wl, expert_bits, 8, cell_bits, True) * 1.08
    rows, cols = 256, 256
    arrays = math.ceil(cells / (rows * cols))
    t_op = g("rram_t_op_s", s)
    tiles_per_expert = math.ceil(2 * 3584 * 3072 * math.ceil(expert_bits / cell_bits) * 2 / (C * cols))
    dens = g("rram_cells_per_mm2", s)
    die_mm2 = 100.0
    dies = max(1, math.ceil(cells / dens / die_mm2))
    d = dict(family="analog_cim", tech="rram3d", silicon="research_device", scenario=s, name="F_3d_rram_crossbar",
             contributors=C, array_cols=cols, array_rows=rows, cell_bits=cell_bits, expert_w_mag_bits=expert_bits,
             dense_w_mag_bits=8, signed_mode="differential", analog_subtract=True, x_mag_bits=8, bits_per_pass=1,
             input_sign_phases=False, analog_accumulate_passes=False, time_encoded_input=False,
             t_unit_s=1e-9, t_dac_settle_s=0.0, t_wl_s=0.0, t_step_fixed_s=t_op / 8 * 0.5,
             adcs_per_array=cols // 8, adc_bits=8, psum_bits=16,
             i_cell_max_a=20e-6, v_bl=0.2, avg_level_frac=0.3, avg_input_bit_frac=0.3,
             e_array_op_j=g("rram_e_op_j", s), e_wl_per_op_j=0.0, e_bl_per_step_j=0.0, e_input_driver_per_bit_j=0.0,
             arrays_total=arrays, arrays_per_stage_limit=arrays, expert_arrays_per_layer=arrays,
             expert_rounds_override=structured_expert_rounds(16, tiles_per_expert, arrays, 896),
             dies_per_op=dies, dies_total=dies, bcast_fanout_share=1.0, cells_total=cells,
             cells_per_mm2=dens, density_gb_mm2=dens * cell_bits / 1e9, adc_util_max=0.5, static_power_w=5.0,
             adc_sharing="per_plane" if s != "opt" else "die_pool", adc_pool_per_die=4096,
             **adc_params(s), **orchestrator(s), **links(s, "die_link"))
    d["fold_mla"] = (s == "opt")
    return d


def fenand(s):
    d = analog_nand(s, encoding="E", silicon="redesigned_array", name="G_3d_fenand_analog")
    d.update(tech="fenand3d", silicon="research_device", t_wl_s=g("fenand_t_wl_s", s),
             density_gb_mm2=g("fenand_density_gb_mm2", s), e_wl_per_op_j=g("pim_e_wl_per_op_j", s) * 0.4)
    return d


# ============================================================================= baselines
def gpu(s, system="8xB300"):
    """Calibrated single-stream GPU model (no speculative decoding).

    Calibration: OpenZeka DGX B300 TP8, K3, concurrency 1, short prompts, vLLM:
    101 tok/s (ITL 9.5-9.9 ms) [llm_decode_benchmarks_sourced.csv].  With HBM
    efficiency eta the residual per-layer overhead is fitted:
        t_layer = (9.9 ms - 137 GB / (64 TB/s * eta)) / 93
    real: eta=0.70 -> 84 us/layer reproduces 101 tok/s in this graph model; pess 0.5/110 us; opt 0.8/45 us.
    """
    specs = {"8xB300": dict(bw=8 * 8e12, flops=8 * 4.5e15, tdp=8 * 1200.0, price=325000.0),
             "8xGB300": dict(bw=8 * 8e12, flops=8 * 5e15, tdp=8 * 1400.0, price=550000.0)}[system]
    eta = {"pess": 0.5, "real": 0.7, "opt": 0.8}[s]
    t_layer = {"pess": 110e-6, "real": 84e-6, "opt": 45e-6}[s]
    o = orchestrator(s)
    o.update(attn_flops=specs["flops"] * 0.25, kv_bw_Bps=specs["bw"] * eta, kda_state_bw_Bps=specs["bw"] * eta,
             kda_flops=specs["flops"] * 0.02, orch_op_latency_s=0.5e-6, orch_vec_ops=1e13, embed_latency_s=1e-6,
             kv_pj_per_bit=4.0, kda_state_pj_per_bit=4.0, fold_norm_scale=False, kv_bytes=2.0,
             attn_engine="on-GPU")
    return dict(family="gpu", silicon="existing_product", scenario=s, name=f"H_gpu_{system}",
                gpu_mem_bw_Bps=specs["bw"], gpu_bw_efficiency=eta, gpu_flops=specs["flops"],
                gpu_flop_efficiency=0.4, gpu_kernel_latency_s=0.0, gpu_nonlin_kernel_frac=0.0,
                gpu_mem_pj_per_bit=4.0, gpu_pj_per_flop=0.4, dense_bytes_per_weight=2.0,
                per_layer_sync_s=t_layer, static_power_w=specs["tdp"] * 0.3, system_price_usd=specs["price"],
                **o)


def all_architectures(s):
    return [
        digital_nand(s, "A0"), digital_nand(s, "A1"), digital_nand(s, "A2"),
        analog_nand(s, "B"), analog_nand(s, "C"), analog_nand(s, "D"), analog_nand(s, "E"),
        analog_nand(s, "B", silicon="modified_periphery"),
        rram_3d(s), fenand(s), gpu(s),
    ]


def adc_area_total_m2(arch):
    if arch["family"] != "analog_cim":
        return 0.0
    return arch["arrays_total"] * arch["adcs_per_array"] * adc_area_m2(arch["adc_bits"], arch)
