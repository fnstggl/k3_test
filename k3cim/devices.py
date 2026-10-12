"""Device non-ideality presets for the analog precision study.

Two kinds of presets:

* CrossSim-backed (supported by measured data): the per-cell programming
  error / drift / read-noise are produced by CrossSim's own device classes
  (simulator/devices/custom/*.py) through `crosssim_cell_currents`:
    - "SONOS"     40nm planar charge-trap cell, 128K devices measured
                  (Agrawal IEDM 2022; Xiao TCAS-I 2022), t = 0..5 days drift
    - "RRAMMilo"  HfO2 RRAM, programming error + I-V nonlinearity (Milo IRPS 2021)
    - "RRAMWan"   NeuRRAM RRAM programming error (Wan Nature 2022)
  The SONOS cell is the closest *measured* proxy for charge-trap 3D NAND
  cells, but it is a planar single-crystal-Si transistor, not a poly-Si
  vertical string; 3D NAND variability is expected to be worse.

* Generic parametric presets (state-independent / proportional Gaussian
  errors in units of I_max) used for sweeps and for the speculative 3D NAND /
  FeNAND cases.  Their magnitudes are assumptions recorded in
  results/physical_assumptions.csv.
"""
from __future__ import annotations

import numpy as np

_CROSSSIM_DEVICE_LIMITS = {
    # model: (Rmin, Rmax) giving the suggested conductance window, Vread
    "SONOS": dict(Rmin=62.5e3, Rmax=6.25e11, Vread=0.1),   # I_max = 1.6 uA at 0.1 V, on/off 1e7
    "RRAMMilo": dict(Rmin=1 / 225e-6, Rmax=1 / 50e-6, Vread=0.1),
    "RRAMWan": dict(Rmin=1 / 39e-6, Rmax=1 / 1e-6, Vread=0.1),
}


def _make_crosssim_device(model, cell_bits, time_days=0.0, read_noise=True):
    from simulator import CrossSimParameters
    from simulator.backend import ComputeBackend
    from simulator.devices.device import Device
    ComputeBackend(use_gpu=False)
    p = CrossSimParameters()
    d = p.xbar.device
    lim = _CROSSSIM_DEVICE_LIMITS[model]
    d.Rmin, d.Rmax, d.Vread = lim["Rmin"], lim["Rmax"], lim["Vread"]
    d.cell_bits = cell_bits
    d.time = time_days
    d.programming_error.enable = True
    d.programming_error.model = model
    d.drift_error.enable = time_days > 0
    d.drift_error.model = model if (time_days > 0 and model == "SONOS") else "IdealDevice"
    if read_noise:
        d.read_noise.enable = True
        d.read_noise.model = model
    dev = Device.create_device(d)
    return dev, d


_HAS_READ_NOISE = {"SONOS": True, "RRAMMilo": False, "RRAMWan": False}


def crosssim_cell_currents(levels, cell_bits, model="SONOS", time_days=0.0, seed=0):
    """Map integer cell levels (0..2^b-1) to noisy currents (in level units) via CrossSim.

    Returns (currents, read_noise_sigma) both in units of one level step.
    """
    from simulator.backend import ComputeBackend
    xp = ComputeBackend()
    np.random.seed(seed)
    dev, d = _make_crosssim_device(model, cell_bits, time_days, read_noise=_HAS_READ_NOISE[model])
    lv_max = 2 ** cell_bits - 1
    gmin, gmax = d.Gmin_norm, d.Gmax_norm
    G = gmin + (gmax - gmin) * levels.astype(np.float64) / lv_max
    if time_days > 0:
        Gn = dev.drift_error(G.copy(), time_days)
    else:
        Gn = dev.programming_error(G.copy())
    Gn = np.asarray(Gn)
    var = np.asarray(dev.read_noise_variance(G.copy())) if _HAS_READ_NOISE[model] else np.zeros_like(G)
    I = (Gn - gmin) / (gmax - gmin) * lv_max
    sig = np.sqrt(np.maximum(var, 0)) / (gmax - gmin) * lv_max
    return I, sig


def sonos_sigma_frac_of_imax(I_na, I_max_na=1600.0, t_days=0):
    """Closed form of CrossSim's SONOS programming-variability model (t=0): sigma(I)/I_max."""
    A, B = (19.88665, 176.3115)
    s = A * (1 - np.exp(-np.asarray(I_na) / B))
    return s / I_max_na
