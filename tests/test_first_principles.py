import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import first_principles as fp  # noqa: E402

from k3cim.workload import K3Workload  # noqa: E402


def test_invariants_match_checkpoint_scale():
    inv = fp.workload_invariants(K3Workload())
    assert abs(inv["expert_weights"] / 2.7227e12 - 1) < 0.01
    assert inv["depth"] == 698 and inv["sync"] == 1396
    assert abs(inv["kv_bytes_per_ctx_token"] - 576 * 24 * 2) < 1


def test_only_nand_class_storage_fits_500_usd():
    inv = fp.workload_invariants(K3Workload())
    bits, rows = fp.storage_floor(inv)
    cost = {name.split(" ")[0]: c for name, _mm2, c, _s in rows}
    assert cost["3D"] < 500 < cost["DRAM"] < cost["HBM3E"] < cost["SRAM"]
    assert 1.45e12 < bits / 8 < 1.55e12


def test_stream_sense_amp_floor_scales_with_rate_and_tR():
    inv = fp.workload_invariants(K3Workload())
    a = fp.stream_floors(inv, 500, 3e-6)["sense_amps"]
    b = fp.stream_floors(inv, 1000, 3e-6)["sense_amps"]
    c = fp.stream_floors(inv, 500, 0.5e-6)["sense_amps"]
    assert abs(b / a - 2) < 1e-9 and abs(a / c - 6) < 1e-9
