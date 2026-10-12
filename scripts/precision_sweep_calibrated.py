#!/usr/bin/env python3
"""Sweep A with *calibrated* ADC ranges (ideal devices), merged into results/precision_sweep.csv.

The ADC full scale of each conversion type is set to the 99.99th percentile of the
bitline sums observed for the even-indexed tokens (calibration set) and the error is
measured on the odd-indexed tokens only (held out), so range calibration is not
evaluated on its own data.
"""
import csv
import itertools
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import precision_sweep as ps  # noqa: E402

from k3cim.analog import AnalogConfig, analog_mvm_adc_sweep, error_stats  # noqa: E402
from k3cim.formats import dequant_mx, quantize_mxfp8  # noqa: E402


def main():
    acts = dict(np.load(ps.ACT))
    R = 128
    topk = acts["L1.moe.topk_idx"]
    expert = int(np.bincount(topk.ravel()).argmax())
    v, e, X = ps.expert_operands(1, expert, "w1", R, acts)
    Wf = v.astype(np.float64) * np.ldexp(1.0, np.repeat(e, 32, axis=1))
    q, se = quantize_mxfp8(X)
    Xq = dequant_mx(q, se)
    vd, ed, Xd, Wd_bf16 = ps.dense_operands(f"{ps.P}layers.0.self_attn.q_proj.weight", "L0.kda.in", R, acts)
    Wd = vd.astype(np.float64) * np.ldexp(1.0, np.repeat(ed, 32, axis=1))
    qd, sed = quantize_mxfp8(Xd)
    Xdq = dequant_mx(qd, sed)
    T = X.shape[0]
    cal = np.arange(T) % 2 == 0
    ev = ~cal
    ops = {"L1.expert.w1": (v, e, Xq, X, Wf), "L0.kda.q_proj(bf16->mxint8)": (vd, ed, Xdq, Xd, Wd_bf16)}
    rows = []
    adcs = list(range(4, 15))
    t0 = time.time()
    for name, (vv, ee, XXq, XX, Wref) in ops.items():
        y_bf = XX[ev] @ Wref.T
        budget = float(np.linalg.norm(XXq[ev] @ Wref.T - y_bf) / np.linalg.norm(y_bf))
        for C in (8, 16, 32, 64, 128, 256):
            extra = 0 if C <= 32 else (1 if C <= 128 else 2)
            Wint, wexp, wbits = ps.map_weights(vv, ee, C, extra)
            Xi, xexp = ps.map_inputs(XXq, C, 8)
            for cb, bpp in itertools.product((1, 2, 3, 4), (1, 2, 4, 8)):
                cfg = AnalogConfig(cell_bits=cb, contributors=C, bits_per_pass=bpp, x_mag_bits=8,
                                   w_mag_bits=max(wbits, 1), signed_mode="differential")
                ys, y_ex = analog_mvm_adc_sweep(Wint, Xi, cfg, adcs, wexp, xexp, calib_mask=cal)
                for ab in adcs:
                    st = error_stats(ys[ab][ev], y_ex[ev])
                    rows.append({"sweep": "A_ideal_device_calibrated_range", "tensor": name,
                                 "evidence": "exact_math+ideal_device(ADC range calibrated on held-out tokens)",
                                 "cell_bits": cb, "contributors": C, "bits_per_pass": bpp, "x_mag_bits": 8,
                                 "adc_bits": ab, "signed_mode": "differential", "w_mag_bits": wbits,
                                 "slices": cfg.n_slices, "passes": cfg.n_passes, "adc_exact_bits": cfg.exact_adc_bits(),
                                 "conversions_per_output_per_group": cfg.conversions_per_output_group(),
                                 "rel_rms_err": st["rel_rms_err"], "snr_db": st["snr_db"], "exact_frac": st["exact_frac"],
                                 "mxfp8_budget_err": budget, "budget_ratio": st["rel_rms_err"] / budget,
                                 "w_align_extra_bits": extra, "verdict": ps.verdict(st["rel_rms_err"] / budget)})
            print(f"{name} C={C} done ({time.time() - t0:.0f}s)", flush=True)
    path = ps.OUT
    old = list(csv.DictReader(open(path))) if os.path.exists(path) else []
    old = [r for r in old if r.get("sweep") != "A_ideal_device_calibrated_range"]
    allrows = old + rows
    keys = []
    for r in allrows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(allrows)
    print("merged", len(rows), "rows into", path)


if __name__ == "__main__":
    main()
