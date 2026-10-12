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


def test_spec_decoding_fit_and_calibration():
    from k3cim.scheduler import fit_alpha, spec_tokens_per_step, speculative_tok_per_s
    a = fit_alpha(3.84, 7)
    assert abs(spec_tokens_per_step(a, 7) - 3.84) < 1e-6
    t, _ = speculative_tok_per_s(Scheduler(gpu("real")), 2048, 7)
    assert abs(t - 188.0) / 188.0 < 0.05          # measured DSpark result on DGX B300


def test_prefill_grows_superlinearly_with_prompt():
    from k3cim.scheduler import prefill_seconds
    sc = Scheduler(gpu("real"))
    t1, _ = prefill_seconds(sc, 32768)
    t2, _ = prefill_seconds(sc, 131072)
    assert t2 > 4 * t1                             # causal attention is quadratic


def test_attention_engine_costs_ordered():
    from k3cim.cost import orchestrator_cost
    costs = []
    for e in ("edge", "mid", "mid2", "mid3", "high", "xhigh"):
        a = analog_nand("real", "E")
        a.update(orchestrator("real", e))
        costs.append(orchestrator_cost(a, 131072, "normalized")[0])
    assert costs == sorted(costs)


def test_rram_neurosim_density_is_capacity_prohibitive():
    from k3cim.architectures import rram_3d
    c = cost_estimate(rram_3d("real"))
    assert c["dies"] > 10000                       # ~3.4 M cells/mm2 incl. periphery (NeuroSim)


def _e_design(s="real", engine="mid", pool=2048):
    a = analog_nand(s, "E", contributors=128, cell_bits=2, adc_bits=8)
    a.update(adc_sharing="die_pool", adc_pool_per_die=pool, int_cap_area_m2=8e-12)
    a.update(orchestrator(s, engine))
    return a


def test_speculative_cim_k0_like_baseline_and_replicas_help():
    from k3cim.scheduler import speculative_cim, with_dense_replicas
    from k3cim.workload import K3Workload
    wl = K3Workload()
    a = _e_design()
    base = Scheduler(a, wl).evaluate(32768)["tok_per_s"]
    r0 = speculative_cim(Scheduler(a, wl), 32768, 0)        # no drafts: one token per step
    assert abs(r0["tok_per_s"] - base) / base < 0.02
    one = speculative_cim(Scheduler(a, wl), 32768, 3, dense_replicas=1)
    b = with_dense_replicas(a, 4)
    four = speculative_cim(Scheduler(b, wl), 32768, 3, dense_replicas=4)
    assert four["t_critical_path_s"] < one["t_critical_path_s"]
    assert b["planes"] > a["planes"] and cost_estimate(b)["memory_silicon_usd"] > cost_estimate(a)["memory_silicon_usd"]


def test_measured_routing_locality_is_worse_than_random_for_cim():
    from k3cim.scheduler import speculative_cim
    from k3cim.workload import K3Workload
    wl = K3Workload()
    a = _e_design()
    meas = speculative_cim(Scheduler(a, wl), 32768, 7, routing="measured")
    rand = speculative_cim(Scheduler(a, wl), 32768, 7, routing="random")
    assert meas["max_load"] > rand["max_load"]


def test_sram_kv_engine_cost_scales_with_context_and_uses_fp8_kv():
    a = _e_design(engine="sram_b")
    c128 = cost_estimate(a, 131072)["orchestrator_and_kv_usd"]
    c1m = cost_estimate(a, 1048576)["orchestrator_and_kv_usd"]
    assert c1m > 3 * c128
    sc = Scheduler(a)
    assert abs(sc.kv_bytes_at(131072) - 576 * 24 * 131072 * 1.0) < 1.0
    # leakage of the on-die KV SRAM is charged: static share grows with context
    r1, r2 = sc.evaluate(32768), sc.evaluate(1048576)
    assert r2["e_static_j"] / r2["t_token_s"] > r1["e_static_j"] / r1["t_token_s"]
