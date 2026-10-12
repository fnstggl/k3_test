#!/usr/bin/env python3
"""Cross-validate k3cim.analog (fast custom simulator) against CrossSim AnalogCore.

Same integer matrix (QLC full range [-15,15]) and integer inputs; differential
(balanced) mapping; no bit slicing; CrossSim's SONOS programming-error model.
Compares relative MVM error statistics over several seeds:
  (1) ideal device + finite ADC (quantisation only),
  (2) SONOS programming error, no ADC,
  (3) SONOS programming error + read noise, no ADC.
Writes data/sim_outputs/crosssim/crossval.json
"""
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from simulator import AnalogCore, CrossSimParameters  # noqa: E402
from simulator.backend import ComputeBackend  # noqa: E402

from k3cim.analog import AnalogConfig, analog_mvm, error_stats  # noqa: E402

ComputeBackend(use_gpu=False)
N, K, T = 128, 256, 32


def crosssim_params(device, read_noise, adc_bits):
    p = CrossSimParameters()
    p.core.style = "BALANCED"
    p.core.balanced.style = "ONE_SIDED"
    p.core.balanced.subtract_current_in_xbar = True
    p.core.rows_max = K
    p.core.cols_max = N
    p.core.weight_bits = 0
    p.core.mapping.weights.clipping = False
    p.core.mapping.weights.percentile = 1.0     # map max |W| to G_max
    d = p.xbar.device
    d.Rmin, d.Rmax, d.Vread = 62.5e3, 6.25e11, 0.1
    d.cell_bits = 0
    if device:
        d.programming_error.enable = True
        d.programming_error.model = device
    if read_noise:
        d.read_noise.enable = True
        d.read_noise.model = device
    p.core.mapping.inputs.mvm.min = -127
    p.core.mapping.inputs.mvm.max = 127
    p.xbar.dac.mvm.bits = 8
    p.xbar.dac.mvm.input_bitslicing = False
    if adc_bits:
        p.xbar.adc.mvm.bits = adc_bits
        p.xbar.adc.mvm.model = "QuantizerADC"
        p.core.mapping.inputs.mvm.min = -127
        p.xbar.adc.mvm.adc_range_option = "MAX"
    else:
        p.xbar.adc.mvm.bits = 0
    return p


def main():
    rng = np.random.default_rng(0)
    W = rng.integers(-15, 16, size=(N, K))
    X = rng.integers(-127, 128, size=(T, K))
    y_ex = X @ W.T
    out = {}
    cases = [("sonos_prog_noADC", "SONOS", False, 0), ("sonos_prog_read_noADC", "SONOS", True, 0)]
    for name, dev, rn, adcb in cases:
        cs, mine = [], []
        for seed in range(5):
            np.random.seed(100 + seed)
            core = AnalogCore(W.astype(np.float64), params=crosssim_params(dev, rn, adcb))
            y_cs = np.stack([core @ X[t].astype(np.float64) for t in range(T)])
            cs.append(error_stats(y_cs, y_ex)["rel_rms_err"])
            cfg = AnalogConfig(cell_bits=4, w_mag_bits=4, contributors=K, x_mag_bits=7, bits_per_pass=7,
                               adc_bits=24, device_model=dev, seed=seed)
            if not rn:
                # CrossSim case without read noise: disable it in ours too
                import k3cim.devices as kd
                kd._HAS_READ_NOISE["SONOS"] = False
            y_m, _ = analog_mvm(W, X, cfg)
            if not rn:
                import k3cim.devices as kd
                kd._HAS_READ_NOISE["SONOS"] = True
            mine.append(error_stats(y_m, y_ex)["rel_rms_err"])
        out[name] = {"crosssim_mean": float(np.mean(cs)), "crosssim_std": float(np.std(cs)),
                     "k3cim_mean": float(np.mean(mine)), "k3cim_std": float(np.std(mine)),
                     "ratio": float(np.mean(mine) / np.mean(cs))}
        print(name, out[name], flush=True)
    json.dump(out, open(os.path.join(ROOT, "data", "sim_outputs", "crosssim", "crossval.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
