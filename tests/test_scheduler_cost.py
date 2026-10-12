import math

from k3cim.architectures import analog_nand, digital_nand, gpu, orchestrator
from k3cim.cost import WAFER_GROSS_MM2, cost_estimate, nand_usd_per_mm2, poisson_yield
from k3cim.scheduler import Scheduler, adc_time_s


def test_gpu_calibration_matches_measurement():
    r = Scheduler(gpu("real")).evaluate(2048)
    assert abs(r["tok_per_s"] - 101.0) / 101.0 < 0.05      # OpenZeka DGX B300, K3, conc 1, no spec decode


def test_critical_path_not_below_bounds():
    a = analog_nand("real", "E", adc_bits=8)
    a.update(adc_sharing="die_pool", adc_pool_per_die=1024)
    r = Scheduler(a).evaluate(131072)
    assert r["t_token_s"] >= max(r["bounds"].values()) and r["t_token_s"] >= r["t_critical_path_s"]


def test_fewer_adcs_is_slower_but_smaller():
    out = []
    for pool in (128, 2048):
        a = analog_nand("real", "B", adc_bits=8)
        a.update(adc_sharing="die_pool", adc_pool_per_die=pool)
        out.append((Scheduler(a).evaluate(32768)["tok_per_s"], cost_estimate(a)["total_mm2"]))
    assert out[0][0] < out[1][0] and out[0][1] < out[1][1]


def test_longer_context_never_faster():
    a = analog_nand("real", "E", adc_bits=8)
    a.update(adc_sharing="die_pool", adc_pool_per_die=1024)
    sc = Scheduler(a)
    t = [sc.evaluate(L)["tok_per_s"] for L in (32768, 131072, 1048576)]
    assert t[0] >= t[1] >= t[2]


def test_digital_sense_bound_formula():
    a = digital_nand("real", "A2")
    r = Scheduler(a).evaluate(32768)
    wl = Scheduler(a).wl
    bytes_tok = sum(o.K * o.N * o.count * (0.53125 if o.wdtype == "mxfp4" else 2.0) for o in wl.linear_ops())
    expect = bytes_tok / a["page_bytes"] * a["t_read_s"] / a["planes_total"]
    assert math.isclose(r["bounds"]["nvm_sense_throughput"], expect, rel_tol=1e-6)


def test_cost_basis():
    assert math.isclose(nand_usd_per_mm2("normalized"), 8240.11 / WAFER_GROSS_MM2)
    assert 0.1 < nand_usd_per_mm2("normalized") < 0.15
    assert poisson_yield(100, 0.1) == math.exp(-0.1)


def test_adc_time():
    assert adc_time_s(8, {"adc_bit_cycle_s": 2e-9}) == 20e-9
