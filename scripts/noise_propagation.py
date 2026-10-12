#!/usr/bin/env python3
"""Propagate analog-MVM-like errors through the real K3 layers 0-3 (real weights, real text).

Every linear-layer output y (per token) is perturbed as
    y' = y + r * rms(y) * N(0, 1)          (r = relative RMS MVM error, as in the precision study)
applied to (i) routed experts only or (ii) every linear op.  A reference run
quantises every linear-layer *input* to MXFP8 (K3's QAT activation format).

Metrics vs the exact BF16 reference forward (data/k3/activations/k3_layers0-3.npz):
  * relative error of the residual stream after layer 3 (all tokens and non-BOS tokens),
  * routing stability: mean fraction of each token's top-16 experts that stays the same
    in MoE layers 1-3 (routing flips are the discontinuous failure mode of MoE).
Writes results/noise_propagation.csv
"""
import csv
import json
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import k3_real_forward as F  # noqa: E402

from k3cim.formats import dequant_mx, quantize_mxfp8  # noqa: E402

REF = os.path.join(ROOT, "data", "k3", "activations", "k3_layers0-3.npz")
OUT = os.path.join(ROOT, "results", "noise_propagation.csv")


def main():
    cfg = json.load(open(os.path.join(ROOT, "data", "k3", "config.json")))["text_config"]
    ref = dict(np.load(REF))
    ids = ref["token_ids"].tolist()
    orig_lin = F.lin
    rows = []
    cases = [("mxfp8_inputs_all_linears", "mxfp8", 0.0)]
    for r in (0.005, 0.01, 0.02, 0.04, 0.08):
        cases += [(f"noise_experts_only_r{r}", "experts", r), (f"noise_all_linears_r{r}", "all", r)]
    if "--quick" in sys.argv:
        cases = cases[:3]
    for name, mode, r in cases:
        rng = np.random.default_rng(1234)
        state = {"in_expert": False}

        def lin(x, w, _mode=mode, _r=r, _rng=rng):
            if _mode == "mxfp8":
                q, se = quantize_mxfp8(np.asarray(x, np.float64))
                return orig_lin(dequant_mx(q, se).astype(np.float32), w)
            y = orig_lin(x, w)
            if _mode == "all" or (_mode == "experts" and state["in_expert"]):
                s = np.sqrt(np.mean(y.astype(np.float64) ** 2, axis=-1, keepdims=True))
                y = y + (_r * s * _rng.standard_normal(y.shape)).astype(np.float32)
            return y

        # mark expert matmuls: the MoE function dequantises experts via F.dequant_mxfp4 right before use
        orig_deq = F.dequant_mxfp4

        def deq(*a, **k):
            state["in_expert"] = True
            return orig_deq(*a, **k)

        orig_rms = F.rms

        def rms_(*a, **k):
            state["in_expert"] = False
            return orig_rms(*a, **k)

        F.lin, F.dequant_mxfp4, F.rms = lin, deq, rms_
        t0 = time.time()
        rec = F.run_layers(ids, 4, cfg, log=lambda m: None)
        F.lin, F.dequant_mxfp4, F.rms = orig_lin, orig_deq, orig_rms
        row = {"case": name, "mode": mode, "rel_mvm_err": r}
        for L in range(4):
            a, b = rec[f"L{L}.out"].astype(np.float64), ref[f"L{L}.out"].astype(np.float64)
            row[f"L{L}_out_relerr_all"] = float(np.linalg.norm(a - b) / np.linalg.norm(b))
            row[f"L{L}_out_relerr_nonBOS"] = float(np.linalg.norm(a[1:] - b[1:]) / np.linalg.norm(b[1:]))
        for L in (1, 2, 3):
            t1, t2 = rec[f"L{L}.moe.topk_idx"], ref[f"L{L}.moe.topk_idx"]
            keep = [len(set(x) & set(y)) / 16.0 for x, y in zip(t1, t2)]
            row[f"L{L}_routing_kept_frac"] = float(np.mean(keep))
            row[f"L{L}_tokens_with_any_flip"] = float(np.mean([k < 1.0 for k in keep]))
        row["sim_s"] = round(time.time() - t0, 1)
        rows.append(row)
        print(row, flush=True)
        keys = list(rows[0].keys())
        with open(OUT, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    main()
