#!/usr/bin/env python3
"""Seed-to-seed spread of the CrossSim tutorial-pt2 image-DFT metrics (to judge reproduction)."""
import json, os, sys
import numpy as np
CS = sys.argv[1] if len(sys.argv) > 1 else "/home/user/ext/cross-sim"
sys.path.insert(0, CS); os.chdir(os.path.join(CS, "tutorial"))
import scipy.linalg
from PIL import Image
from applications.mvm_params import set_params
from simulator import AnalogCore
N1 = N2 = 256
X = np.array(Image.open('../applications/dsp/example_images/orchid.jpg').resize((N1, N2))).astype(np.float32) / 255
def mae(params):
    Wd = scipy.linalg.dft(N1); Wi = np.matrix.getH(Wd)
    a1, a2 = AnalogCore(Wd, params=params), AnalogCore(Wi, params=params)
    R = np.zeros(X.shape, dtype=np.complex128)
    for ch in range(3):
        Y = (a1 @ X[:, :, ch]) @ a1; R[:, :, ch] = (a2 @ Y) @ a2
    return float(np.mean(np.abs(np.real(R / (N1 * N2)).clip(0, 1) - X)))
cases = {
 "dft_img_mae_balanced": dict(wtmodel="BALANCED", weight_bits=8, Rmax=1e6),
 "dft_img_mae_offset": dict(wtmodel="OFFSET", weight_bits=8, Rmax=1e6),
 "dft_img_mae_1slice": dict(wtmodel="BALANCED", weight_bits=9, Rmax=1e6, Nslices=1),
 "dft_img_mae_4slices": dict(wtmodel="BALANCED", weight_bits=9, Rmax=1e6, Nslices=4)}
out = {}
for k, c in cases.items():
    vals = []
    for s in range(8):
        np.random.seed(1000 + s)
        vals.append(mae(set_params(complex_matrix=True, complex_input=True, Rmin=1e3, error_model='generic',
                                   alpha_error=0.15, proportional_error=True, **c)))
    out[k] = {"mean": float(np.mean(vals)), "std": float(np.std(vals, ddof=1)), "vals": vals}
    print(k, out[k]["mean"], out[k]["std"], flush=True)
json.dump(out, open(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
          "data", "sim_outputs", "crosssim", "seed_spread.json"), "w"), indent=1)
