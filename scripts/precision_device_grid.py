#!/usr/bin/env python3
"""Device-only analog error on real K3 tensors for every (device, cell bits, C, bits/pass).

ADC is made effectively ideal (enough bits for the exact range) so the
result isolates device non-idealities; quantisation/ADC error comes from
results/precision_sweep.csv (sweep A).  Both are combined in
k3cim/precision_model.py as independent error terms (root-sum-square),
validated against the direct joint simulation in sweep B.
Writes data/sim_outputs/crosssim/device_grid.json
"""
import itertools
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import precision_sweep as ps  # noqa: E402

from k3cim.analog import AnalogConfig, analog_mvm, error_stats  # noqa: E402
from k3cim.formats import dequant_mx, quantize_mxfp8  # noqa: E402

DEVICES = {
    "SONOS_t0": dict(device_model="SONOS", device_time_days=0.0),
    "SONOS_t1d": dict(device_model="SONOS", device_time_days=1.0),
    "SONOS_t5d": dict(device_model="SONOS", device_time_days=5.0),
    "RRAMMilo": dict(device_model="RRAMMilo"),
    "generic_0.5pct": dict(sigma_prog_abs=0.005, sigma_read_abs=0.0025),
    "generic_1pct": dict(sigma_prog_abs=0.01, sigma_read_abs=0.005),
    "generic_2pct": dict(sigma_prog_abs=0.02, sigma_read_abs=0.01),
}


def main():
    acts = dict(np.load(ps.ACT))
    R = 96
    topk = acts["L1.moe.topk_idx"]
    expert = int(np.bincount(topk.ravel()).argmax())
    v, e, X = ps.expert_operands(1, expert, "w1", R, acts)
    q, se = quantize_mxfp8(X)
    Xq = dequant_mx(q, se)
    vd, ed, Xd, _ = ps.dense_operands(f"{ps.P}layers.0.self_attn.q_proj.weight", "L0.kda.in", R, acts)
    qd, sed = quantize_mxfp8(Xd)
    Xdq = dequant_mx(qd, sed)
    out = {}
    for tname, (vv, ee, XX) in {"expert": (v, e, Xq), "dense": (vd, ed, Xdq)}.items():
        for C in (32, 64, 128, 256):
            extra = 0 if C <= 32 else (1 if C <= 128 else 2)
            Wint, wexp, wbits = ps.map_weights(vv, ee, C, extra)
            Xi, xexp = ps.map_inputs(XX, C, 8)
            y_ideal, y_ex = analog_mvm(Wint, Xi, AnalogConfig(cell_bits=4, w_mag_bits=wbits, contributors=C,
                                                                x_mag_bits=8, bits_per_pass=8, adc_bits=24), wexp, xexp)
            for (dname, dkw), cb, bpp in itertools.product(DEVICES.items(), (1, 2, 3, 4), (1, 2, 4, 8)):
                cfg = AnalogConfig(cell_bits=cb, w_mag_bits=wbits, contributors=C, x_mag_bits=8, bits_per_pass=bpp,
                                   adc_bits=28, seed=5, **dkw)
                y, _ = analog_mvm(Wint, Xi, cfg, wexp, xexp)
                st = error_stats(y, y_ex)
                out[f"{tname}|{dname}|{cb}|{C}|{bpp}"] = st["rel_rms_err"]
            print(tname, C, "done", flush=True)
    path = os.path.join(ROOT, "data", "sim_outputs", "crosssim", "device_grid.json")
    json.dump(out, open(path, "w"), indent=0)
    print("wrote", path, len(out))


if __name__ == "__main__":
    main()
