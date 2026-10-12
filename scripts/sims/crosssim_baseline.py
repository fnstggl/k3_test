#!/usr/bin/env python3
"""Reproduce the recorded numeric outputs of CrossSim tutorial part 2 (V3.2.1).

Runs the exact code of tutorial/tutorial_pt2.ipynb cells 0-27 (plots removed),
in the same order and with the same seed (np.random.seed(198)), then compares
with the outputs stored in the notebook.  Usage:
    python scripts/sims/crosssim_baseline.py /path/to/cross-sim
"""
import json
import os
import sys

import numpy as np

CS = sys.argv[1] if len(sys.argv) > 1 else "/home/user/ext/cross-sim"
sys.path.insert(0, CS)
os.chdir(os.path.join(CS, "tutorial"))
import scipy.linalg  # noqa: E402
from PIL import Image  # noqa: E402
from applications.mvm_params import set_params  # noqa: E402
from simulator import AnalogCore  # noqa: E402

np.random.seed(198)
res = {}
# cell 2: quantization (consumes RNG? no errors enabled)
N_ft1 = 256
W = np.real(scipy.linalg.dft(N_ft1))
x = np.zeros(N_ft1); x[122:133] = 1
for b in (4, 6, 8):
    p = set_params(weight_bits=b, weight_percentile=100, input_bits=b, input_range=(-1, 1), adc_bits=b, adc_range=(-12, 12))
    y = AnalogCore(W, params=p) @ x
    res[f"quant_{b}b_rel_err_vs_numpy"] = float(np.linalg.norm(y - W @ x) / np.linalg.norm(W @ x))
# cell 8
N = 64
W_rdft = np.real(scipy.linalg.dft(N))
AnalogCore(W_rdft, params=set_params(weight_bits=8, wtmodel="BALANCED", Rmin=1e3, Rmax=1e6))
AnalogCore(W_rdft, params=set_params(weight_bits=8, wtmodel="OFFSET", Rmin=1e3, Rmax=1e6))
# cell 15/17
W_dft = scipy.linalg.dft(64)
base = {'weight_bits': 8, 'complex_matrix': True, 'Rmin': 1e3, 'Rmax': 1e6,
        'error_model': 'generic', 'alpha_error': 0.25, 'proportional_error': True}
xb = AnalogCore(W_dft, params=set_params(wtmodel="BALANCED", **base))
xo = AnalogCore(W_dft, params=set_params(wtmodel="OFFSET", **base))
res["weight_mae_balanced"] = float(np.mean(np.abs(W_dft - xb.get_matrix())))
res["weight_mae_offset"] = float(np.mean(np.abs(W_dft - xo.get_matrix())))
# cell 19/20
N1 = N2 = 256; Nch = 3
X = np.array(Image.open('../applications/dsp/example_images/orchid.jpg').resize((N1, N2))).astype(np.float32) / 255


def recon(params):
    Wd = scipy.linalg.dft(N1); Wi = np.matrix.getH(Wd)
    a, b = AnalogCore(Wd, params=params), AnalogCore(Wi, params=params)
    return a, b


def run_pair(pa, pb):
    Wd = scipy.linalg.dft(N1); Wi = np.matrix.getH(Wd)
    a1, a2 = AnalogCore(Wd, params=pa), AnalogCore(Wi, params=pa)
    b1, b2 = AnalogCore(Wd, params=pb), AnalogCore(Wi, params=pb)
    Ra = np.zeros(X.shape, dtype=np.complex128); Rb = np.zeros(X.shape, dtype=np.complex128)
    for ch in range(Nch):
        Y = (a1 @ X[:, :, ch]) @ a1; Ra[:, :, ch] = (a2 @ Y) @ a2
        Y = (b1 @ X[:, :, ch]) @ b1; Rb[:, :, ch] = (b2 @ Y) @ b2
    Ra = np.real(Ra / (N1 * N2)).clip(0, 1); Rb = np.real(Rb / (N1 * N2)).clip(0, 1)
    return float(np.mean(np.abs(Ra - X))), float(np.mean(np.abs(Rb - X)))


base = {'weight_bits': 8, 'complex_matrix': True, 'complex_input': True, 'Rmin': 1e3, 'Rmax': 1e6,
        'error_model': 'generic', 'alpha_error': 0.15, 'proportional_error': True}
res["dft_img_mae_balanced"], res["dft_img_mae_offset"] = run_pair(set_params(wtmodel="BALANCED", **base),
                                                                  set_params(wtmodel="OFFSET", **base))
base['Rmax'] = 4e3
res["dft_img_mae_balanced_onoff4"], res["dft_img_mae_offset_onoff4"] = run_pair(set_params(wtmodel="BALANCED", **base),
                                                                                set_params(wtmodel="OFFSET", **base))
# cell 25 (slices visual) then 27
AnalogCore(W_rdft, params=set_params(weight_bits=9, Rmin=1e3, Rmax=1e6, wtmodel="BALANCED", Nslices=4))
base = {'weight_bits': 9, 'complex_matrix': True, 'complex_input': True, 'wtmodel': 'BALANCED', 'Rmin': 1e3, 'Rmax': 1e6,
        'error_model': 'generic', 'alpha_error': 0.15, 'proportional_error': True}
res["dft_img_mae_1slice"], res["dft_img_mae_4slices"] = run_pair(set_params(Nslices=1, **base), set_params(Nslices=4, **base))

expected = {"weight_mae_balanced": 0.21637, "weight_mae_offset": 0.34244,
            "dft_img_mae_balanced": 0.08355, "dft_img_mae_offset": 0.14456,
            "dft_img_mae_balanced_onoff4": 0.11186, "dft_img_mae_offset_onoff4": 0.19570,
            "dft_img_mae_1slice": 0.08336, "dft_img_mae_4slices": 0.06327}
rows = []
for k, v in res.items():
    e = expected.get(k)
    rows.append({"metric": k, "expected_tutorial_pt2": e, "observed": round(v, 5),
                 "pct_diff": None if e is None else round(100 * (v - e) / e, 2)})
out = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                   "data", "sim_outputs", "crosssim", "baseline_reproduction.json")
json.dump(rows, open(out, "w"), indent=1)
for r in rows:
    print(r)
