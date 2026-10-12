from k3cim.workload import K3Workload, manifest_check


def test_parameter_counts_match_checkpoint():
    wl = K3Workload()
    m = manifest_check(wl)
    assert m["mxfp4_match"] and m["bf16_match"]
    assert m["checkpoint"]["mxfp4"] == 2_722_740_830_208


def test_layer_composition():
    wl = K3Workload()
    assert len(wl.kda_layers) == 69 and len(wl.mla_layers) == 24
    assert 0 in wl.kda_layers and 3 in wl.mla_layers and 92 in wl.mla_layers
    assert len(wl.moe_layers) == 92


def test_active_params_match_model_card():
    a = K3Workload().active_params()
    tot = a["bf16"] + a["mxfp4"]
    assert abs(tot / 1e9 - 104.17) < 0.05      # model card: 104B activated


def test_critical_path_depth():
    wl = K3Workload()
    d, path = wl.sequential_linear_depth()
    assert d == 698
    assert path[0] == "embed" or path[0].startswith("L0")
    assert K3Workload(fold_mla=True).sequential_linear_depth()[0] == 674


def test_kv_cache_sizes():
    wl = K3Workload()
    assert wl.kv_cache_bytes(1) == 576 * 24 * 2
    assert abs(wl.kv_cache_bytes(1048576) / 1e9 - 28.99) < 0.01
    assert abs(wl.kda_state_bytes_total() / 1e6 - 449.4) < 0.5


def test_ops_topologically_ordered():
    wl = K3Workload()
    seen = set()
    for o in wl.ops:
        for d in o.deps:
            assert d in seen
        seen.add(o.name)
