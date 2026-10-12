#!/usr/bin/env python3
"""Real-tensor numerics analysis for K3 (weights from the checkpoint, activations
from scripts/k3_real_forward.py).

Outputs data/k3/numerics_analysis.json and results/numerics_k3_tensors.csv:
 1. MXFP4 expert weights: E2M1 code histogram, rms/max, zero fraction, and the
    spread of E8M0 block exponents inside groups of 2/4/8 consecutive blocks
    along the reduction dim (= 64/128/256 analog contributors).  An exact
    integer rendering of a group needs 4 + spread magnitude bits.
 2. BF16 dense weights: error of re-quantising to MXINT8 / MXFP8 / MXFP4
    (block 32), on weights and on real MVM outputs.
 3. Real activations: MXFP8 quantisation error (the noise level K3 was
    QAT-trained to tolerate), exponent spread within MX blocks (bits needed
    for an exact fixed-point rendering), outlier ratios.
"""
import csv
import glob
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from k3cim import hf_tensors as hf  # noqa: E402
from k3cim.formats import (MX_BLOCK, aligned_int, dequant_mx, mxfp4_scale_exponents,  # noqa: E402
                           quantize_mxfp4, quantize_mxfp8, unpack_mxfp4_codes)

P = "language_model.model."
ACT = os.path.join(ROOT, "data", "k3", "activations", "k3_layers0-3.npz")


def rel(a, b):
    return float(np.linalg.norm(a - b) / max(np.linalg.norm(b), 1e-30))


def expert_stats(layer=1, max_experts=64):
    files = sorted(glob.glob(os.path.join(hf.TEN_DIR, f"{P}layers.{layer}.block_sparse_moe.experts.*.w1.weight_scale.bin")))
    ids = sorted({int(f.split("experts.")[1].split(".")[0]) for f in files})[:max_experts]
    hist = np.zeros(16, np.int64)
    spreads = {g: [] for g in (2, 4, 8)}
    rms_over_max, zero_frac = [], []
    for e in ids:
        for w in ("w1", "w2", "w3"):
            pk = hf.fetch(f"{P}layers.{layer}.block_sparse_moe.experts.{e}.{w}.weight_packed")
            sc = hf.fetch(f"{P}layers.{layer}.block_sparse_moe.experts.{e}.{w}.weight_scale")
            v2 = unpack_mxfp4_codes(pk)
            mag = np.abs(v2)
            vals, cnt = np.unique(mag, return_counts=True)
            for v, c in zip(vals, cnt):
                hist[int(v)] += c
            rms_over_max.append(float(np.sqrt(np.mean(v2.astype(np.float64) ** 2)) / 12.0))
            zero_frac.append(float(np.mean(v2 == 0)))
            ex = mxfp4_scale_exponents(sc)
            for g in spreads:
                nb = ex.shape[1] // g * g
                grp = ex[:, :nb].reshape(ex.shape[0], -1, g)
                spreads[g].append((grp.max(-1) - grp.min(-1)).ravel())
    out = {"layer": layer, "n_experts": len(ids),
           "e2m1_halfunit_magnitude_hist": {int(k): int(hist[k]) for k in range(13) if hist[k]},
           "rms_over_max_mean": float(np.mean(rms_over_max)), "zero_frac_mean": float(np.mean(zero_frac))}
    for g, lst in spreads.items():
        s = np.concatenate(lst)
        out[f"exp_spread_group{g}_C{g * MX_BLOCK}"] = {
            "mean": float(s.mean()), "p50": float(np.percentile(s, 50)), "p99": float(np.percentile(s, 99)),
            "max": int(s.max()), "frac_spread_0": float(np.mean(s == 0)), "frac_le1": float(np.mean(s <= 1)),
            "frac_le2": float(np.mean(s <= 2)), "frac_le3": float(np.mean(s <= 3)),
            "exact_mag_bits_p99": int(4 + np.percentile(s, 99)), "exact_mag_bits_max": int(4 + s.max())}
    return out


def dense_requant(acts):
    rows = []
    cases = [("L0.kda.q_proj", f"{P}layers.0.self_attn.q_proj.weight", "L0.kda.in"),
             ("L0.kda.o_proj", f"{P}layers.0.self_attn.o_proj.weight", "L0.kda.o_proj.in"),
             ("L0.kda.g_proj", f"{P}layers.0.self_attn.g_proj.weight", "L0.kda.in"),
             ("L0.mlp.down_proj", f"{P}layers.0.mlp.down_proj.weight", "L0.mlp.down.in"),
             ("L1.moe.shared_gate", f"{P}layers.1.block_sparse_moe.shared_experts.gate_proj.weight", "L1.moe.in"),
             ("L1.moe.latent_down", f"{P}layers.1.block_sparse_moe.routed_expert_down_proj.weight", "L1.moe.in"),
             ("L1.moe.latent_up", f"{P}layers.1.block_sparse_moe.routed_expert_up_proj.weight", "L1.moe.latent_up.in"),
             ("L3.mla.q_b_proj", f"{P}layers.3.self_attn.q_b_proj.weight", "L3.mla.q_b.in"),
             ("L3.mla.o_proj", f"{P}layers.3.self_attn.o_proj.weight", "L3.mla.o_proj.in")]
    for name, tname, aname in cases:
        try:
            W = hf.fetch(tname)[:2048].astype(np.float64)   # 2048-row slice bounds memory; statistics are row-wise
        except Exception as ex:  # noqa: BLE001
            rows.append({"tensor": name, "error": str(ex)})
            continue
        X = acts[aname].astype(np.float64) if aname in acts else None
        r = {"tensor": name, "shape": "x".join(map(str, hf.tensor_info(tname)[2]["shape"])), "rows_analyzed": W.shape[0],
             "w_rms_over_absmax": float(np.sqrt(np.mean(W ** 2)) / np.abs(W).max())}
        mi, me = aligned_int(W, 8, group=32)
        Wq = {"mxint8": (mi * np.ldexp(1.0, me)).reshape(W.shape)}
        q, se = quantize_mxfp8(W); Wq["mxfp8_e4m3"] = dequant_mx(q, se)
        q, se = quantize_mxfp4(W); Wq["mxfp4"] = dequant_mx(q, se)
        for k, Wk in Wq.items():
            r[f"w_relerr_{k}"] = rel(Wk, W)
            if X is not None:
                Y = X @ W.T
                r[f"y_relerr_{k}"] = rel(X @ Wk.T, Y)
        if X is not None:
            q, se = quantize_mxfp8(X)
            r["y_relerr_mxfp8_activations_only"] = rel(dequant_mx(q, se) @ W.T, X @ W.T)
        rows.append(r)
        print(r, flush=True)
    return rows


def activation_stats(acts):
    rows = []
    for k, X in acts.items():
        if not k.endswith(".in") or X.ndim != 2 or X.shape[1] % 32:
            continue
        X = X.astype(np.float64)
        q, se = quantize_mxfp8(X)
        Xq = dequant_mx(q, se)
        # per-element exponent spread inside each MX block (bits for exact fixed point)
        a = np.abs(q).reshape(X.shape[0], -1, 32)
        with np.errstate(divide="ignore"):
            e = np.floor(np.log2(np.where(a > 0, a, np.nan)))
        spread = np.nanmax(e, -1) - np.nanmin(e, -1)
        mi, me = aligned_int(Xq, 8, group=32)
        x8 = (mi * np.ldexp(1.0, me)).reshape(X.shape)
        mi, me = aligned_int(Xq, 6, group=32)
        x6 = (mi * np.ldexp(1.0, me)).reshape(X.shape)
        tok_absmax_over_rms = np.abs(X).max(1) / np.sqrt((X ** 2).mean(1))
        rows.append({"activation": k, "T": X.shape[0], "K": X.shape[1],
                     "mxfp8_relerr": rel(Xq, X),
                     "mxint8_from_mxfp8_relerr_vs_mxfp8": rel(x8, Xq),
                     "mxint6_from_mxfp8_relerr_vs_mxfp8": rel(x6, Xq),
                     "block_exp_spread_p50": float(np.nanpercentile(spread, 50)),
                     "block_exp_spread_p99": float(np.nanpercentile(spread, 99)),
                     "exact_fixed_point_bits_p99": float(4 + np.nanpercentile(spread, 99)),
                     "absmax_over_rms_median": float(np.median(tok_absmax_over_rms)),
                     "absmax_over_rms_max": float(tok_absmax_over_rms.max())})
    return rows


def main():
    res = {"experts": [expert_stats(L) for L in (1, 2, 3)
                       if glob.glob(os.path.join(hf.TEN_DIR, f"{P}layers.{L}.block_sparse_moe.experts.*.w1.weight_scale.bin"))]}
    acts = dict(np.load(ACT)) if os.path.exists(ACT) else {}
    res["dense_requant"] = dense_requant(acts)
    res["activations"] = activation_stats(acts)
    json.dump(res, open(os.path.join(ROOT, "data", "k3", "numerics_analysis.json"), "w"), indent=1)
    rows = []
    for r in res["dense_requant"]:
        rows.append({"kind": "dense_weight_requant", **r})
    for r in res["activations"]:
        rows.append({"kind": "activation", **r})
    keys = sorted({k for r in rows for k in r})
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    with open(os.path.join(ROOT, "results", "numerics_k3_tensors.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(json.dumps(res["experts"], indent=1))


if __name__ == "__main__":
    main()
