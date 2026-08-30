"""Unit tests for dimensional calculations in sim/ (Gate 1 requirement)."""

import math

import pytest

from sim.units import ns, us, ms, to_us, to_ms, GBps, to_GBps, bits_to_bytes
from sim.nand import NandConfig, palm_znand
from sim.arithmetic import WFormat, PimConfig, elems_per_page
from sim.plane import window_timing
from sim.mapping import MappingPolicy, map_gemv, capacity_check
from sim.workload import GemvOp, DynOp, Step, TokenWorkload, gpt3_token_workload
from sim.architecture import SystemConfig, EnergyParams, DynSideConfig
from sim.scheduler import simulate_token, time_dyn_op
from sim.energy import token_energy, page_read_energy_J


def approx(a, b, tol=1e-9):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


# ---------- units ----------

def test_units():
    assert approx(us(3.0), 3e-6)
    assert approx(to_us(ns(3000)), 3.0)
    assert approx(to_ms(ms(112) ), 112.0)
    assert approx(GBps(3.2), 3.2e9)
    assert approx(to_GBps(GBps(4.2)), 4.2)
    assert approx(bits_to_bytes(4.25 * 32), 17.0)


# ---------- nand geometry ----------

def test_palm_geometry():
    n = palm_znand()
    n.validate()
    assert n.n_dies == 32
    assert n.n_planes == 256
    assert approx(n.capacity_bytes, 256 * 1024**3)
    # per-plane sense BW = 2KiB / 3us = 682.7 MB/s (decimal)
    assert approx(n.plane_read_bw_Bps, 2048 / 3e-6, 1e-6)
    # aggregate = 174.8 GB/s
    assert approx(n.aggregate_internal_bw_Bps / 1e9, 174.76, 1e-3)


def test_ecc_and_retry():
    n = NandConfig(page_bytes=16384, ecc_parity_overhead=0.10,
                   read_retry_expected_extra_reads=0.5, tR_us=50)
    assert approx(n.usable_page_bytes, 16384 * 0.9)
    assert approx(n.effective_tR_s, 75e-6)


# ---------- arithmetic / formats ----------

def test_wformat_bits():
    assert approx(WFormat.FP16.bits_per_param, 16)
    assert approx(WFormat.MXFP4.bits_per_param, 4.25)
    assert approx(WFormat.MXFP8.bits_per_param, 8.25)


def test_elems_per_page():
    assert approx(elems_per_page(2048, WFormat.FP16), 1024)
    assert approx(elems_per_page(16384, WFormat.MXFP4), 16384 * 8 / 4.25)


def test_pim_compute_time():
    p = PimConfig(lanes_per_plane=1, freq_MHz=400)
    # 1024 elems at 400MHz = 2.56us (paper rounds to 2.5us)
    assert approx(p.compute_time_per_page_s(1024), 1024 / 400e6)


# ---------- window timing ----------

def _no_cmd_nand(**kw):
    n = palm_znand()
    n.cmd_bytes_per_plane_read = 0.0
    for k, v in kw.items():
        setattr(n, k, v)
    return n


def test_window_sense_bound():
    n = _no_cmd_nand()
    p = PimConfig()
    t = window_timing(n, p, elems_per_page_val=1024,
                      input_bytes_per_window_per_scope=0.0, input_scope='die',
                      output_bytes_per_plane_window=0.0)
    assert t.bottleneck == 'sense'
    assert approx(t.period_s, 3e-6)


def test_window_compute_bound():
    n = _no_cmd_nand()
    p = PimConfig(freq_MHz=100)  # 1024/100MHz = 10.24us > 3us
    t = window_timing(n, p, 1024, 0.0, 'die', 0.0)
    assert t.bottleneck == 'compute'
    assert approx(t.period_s, 1024 / 100e6)


def test_window_channel_bound_scopes():
    n = _no_cmd_nand()
    p = PimConfig()
    # per-die input 2KB, 4 dies at 3.2GB/s = 2.56us < 3us -> sense bound
    t_die = window_timing(n, p, 1024, 2048, 'die', 0.0)
    assert t_die.bottleneck == 'sense'
    assert approx(t_die.traffic.input_bytes, 2048 * 4)
    # per-plane input: 32 * 2KB = 20.48us -> channel bound
    t_pl = window_timing(n, p, 1024, 2048, 'plane', 0.0)
    assert t_pl.bottleneck == 'channel'
    assert approx(t_pl.period_s, 2048 * 32 / 3.2e9)
    # channel scope counts once
    t_ch = window_timing(n, p, 1024, 2048, 'channel', 0.0)
    assert approx(t_ch.traffic.input_bytes, 2048)


def test_window_no_cache_register():
    n = _no_cmd_nand(cache_register=False)
    p = PimConfig()
    t = window_timing(n, p, 1024, 0.0, 'die', 0.0)
    assert approx(t.period_s, 3e-6 + 1024 / 400e6)


def test_window_no_overlap_serialization():
    n = _no_cmd_nand()
    p = PimConfig()
    t = window_timing(n, p, 1024, 2048, 'die', 0.0, channel_overlaps_sense=False)
    assert approx(t.period_s, 3e-6 + 2048 * 4 / 3.2e9)


# ---------- mapping ----------

def test_map_gemv_pages_and_latency():
    n = _no_cmd_nand()
    p = PimConfig()
    pol = MappingPolicy(plane_fraction=1.0, input_scope='die')
    op = GemvOp("fc", out_dim=4096, in_dim=4096)  # 16.78M weights FP16
    m = map_gemv(op, n, p, pol)
    assert m.planes_used == 256
    pages = math.ceil(4096 * 4096 / 1024)
    assert approx(m.windows_per_plane, pages / 256)
    assert approx(m.pages_sensed, pages)
    assert approx(m.latency_s, m.windows_per_plane * 3e-6 + 3e-6 + 1024/400e6, 1e-6)


def test_map_gemv_input_reuse():
    n = _no_cmd_nand()
    p = PimConfig()
    op = GemvOp("fc", 4096, 4096)
    m1 = map_gemv(op, n, p, MappingPolicy(rows_per_page=1))
    m4 = map_gemv(op, n, p, MappingPolicy(rows_per_page=4))
    assert approx(m4.timing.traffic.input_bytes, m1.timing.traffic.input_bytes / 4)
    assert approx(m4.timing.traffic.output_bytes, m1.timing.traffic.output_bytes * 4)


def test_capacity_check():
    n = palm_znand()
    assert capacity_check(200 * 1024**3, n)
    assert not capacity_check(260 * 1024**3, n)


# ---------- workload ----------

def test_gpt3_weight_bytes():
    wl = gpt3_token_workload(hidden=4096, n_layers=32, ctx=128, include_lm_head=False)
    per_layer = (3 * 4096 * 4096 + 4096 * 4096 + 2 * 4096 * 16384) * 2.0
    assert approx(wl.total_weight_bytes(), per_layer * 32)
    assert approx(wl.total_macs(), per_layer * 32 / 2.0)


# ---------- scheduler ----------

def test_scheduler_serial_and_overlap():
    sys_cfg = SystemConfig()
    sys_cfg.nand.cmd_bytes_per_plane_read = 0.0
    op = GemvOp("a", 1024, 1024)     # 1M weights -> 1024 pages -> 4 windows/plane
    dyn = DynOp("d", dram_bytes=50e9 * 0.001)  # exactly 1ms at 50GB/s
    wl_serial = TokenWorkload("t", [Step("s", [op], [dyn], overlap=False)])
    wl_overlap = TokenWorkload("t", [Step("s", [op], [dyn], overlap=True)])
    r_s = simulate_token(sys_cfg, wl_serial)
    r_o = simulate_token(sys_cfg, wl_overlap)
    assert r_s.latency_s > r_o.latency_s
    assert approx(r_o.latency_s, max(r_s.latency_s - 1e-3, 1e-3), 1e-3)


def test_scheduler_parallel_nand_disjoint():
    sys_cfg = SystemConfig()
    sys_cfg.nand.cmd_bytes_per_plane_read = 0.0
    sys_cfg.mapping.plane_fraction = 0.5
    a, b = GemvOp("a", 4096, 4096), GemvOp("b", 4096, 4096)
    wl_par = TokenWorkload("t", [Step("s", [a, b], parallel_nand=True)])
    wl_ser = TokenWorkload("t", [Step("s", [a, b], parallel_nand=False)])
    r_par = simulate_token(sys_cfg, wl_par)
    r_ser = simulate_token(sys_cfg, wl_ser)
    assert r_par.latency_s < r_ser.latency_s
    assert approx(r_par.pages_sensed, r_ser.pages_sensed)


def test_scheduler_parallel_overflow_asserts():
    sys_cfg = SystemConfig()
    sys_cfg.mapping.plane_fraction = 1.0
    a, b = GemvOp("a", 4096, 4096), GemvOp("b", 4096, 4096)
    wl = TokenWorkload("t", [Step("s", [a, b], parallel_nand=True)])
    with pytest.raises(AssertionError):
        simulate_token(sys_cfg, wl)


def test_dyn_roofline():
    sys_cfg = SystemConfig(dyn=DynSideConfig(dram_bw_Bps=100e9, npu_flops=10e12))
    assert approx(time_dyn_op(DynOp("m", dram_bytes=1e9), sys_cfg), 0.01)
    assert approx(time_dyn_op(DynOp("c", flops=1e12), sys_cfg), 0.1)
    assert approx(time_dyn_op(DynOp("b", dram_bytes=1e9, flops=1e12), sys_cfg), 0.1)


# ---------- energy ----------

def test_energy_accounting():
    sys_cfg = SystemConfig()
    sys_cfg.energy = EnergyParams(page_read_model="per_page", page_read_nJ=100.0,
                                  channel_pj_per_byte=10.0, mac_pj_per_op=1.0,
                                  dram_pj_per_byte=5.0, npu_pj_per_flop=0.5,
                                  static_W=1.0)
    sys_cfg.nand.cmd_bytes_per_plane_read = 0.0
    op = GemvOp("a", 1024, 1024)
    wl = TokenWorkload("t", [Step("s", [op], [DynOp("d", dram_bytes=1e6, flops=1e6)])])
    res = simulate_token(sys_cfg, wl)
    eb = token_energy(sys_cfg, res)
    assert approx(eb.cell_read_J, res.pages_sensed * 100e-9)
    assert approx(eb.dram_J, 1e6 * 5e-12)
    assert approx(eb.npu_J, 1e6 * 0.5e-12)
    assert approx(eb.static_J, res.latency_s)
    assert eb.total_J > 0


def test_energy_icc_model():
    sys_cfg = SystemConfig()
    sys_cfg.energy.page_read_model = "icc"
    # 3.3V * 70mA * 3us / 8 planes = 86.6 nJ/page
    assert approx(page_read_energy_J(sys_cfg), 3.3 * 0.070 * 3e-6 / 8)
