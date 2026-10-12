#!/usr/bin/env python3
"""Analog-CIM precision sweep on REAL Kimi-K3 tensors.

Weights: MXFP4 routed-expert matrices (exact E2M1 codes + E8M0 scales from the
checkpoint) and BF16 dense matrices (rendered as MXINT8, block 32).
Activations: real inputs recorded by scripts/k3_real_forward.py, quantised to
MXFP8-E4M3 (block 32) as in K3's QAT recipe.

Reference = exact digital dot product of the MXFP4 (or MXINT8) weights with
the MXFP8 activations (float64, exact).  "Budget" = relative error that MXFP8
activation quantisation itself introduces (BF16 activations vs MXFP8) on the
same MVM -- the noise level K3 was trained to tolerate.

Integer mapping for C contributors (one analog sum = one conversion):
  weights: C <= 32 -> per-block codes (4 magnitude bits, exact MX semantics);
           C > 32  -> blocks inside a group aligned to a common exponent with
                      `w_align_extra` extra magnitude bits (exact if the block
                      exponent spread <= extra, else low-order bits rounded).
  inputs:  MXFP8 values rendered as signed fixed point with `x_mag_bits`
           magnitude bits relative to the group max (lossy if a block holds
           values spanning > x_mag_bits-4 binades).

Usage: python scripts/precision_sweep.py [--quick]
Writes results/precision_sweep.csv
"""
import argparse
import csv
import itertools
import math
import os
import sys
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from k3cim import hf_tensors as hf  # noqa: E402
from k3cim.analog import AnalogConfig, analog_mvm, analog_mvm_adc_sweep, error_stats  # noqa: E402
from k3cim.formats import (aligned_int, dequant_mx, mxfp4_scale_exponents,  # noqa: E402
                           quantize_mxfp8, unpack_mxfp4_codes)

P = "language_model.model."
ACT = os.path.join(ROOT, "data", "k3", "activations", "k3_layers0-3.npz")
OUT = os.path.join(ROOT, "results", "precision_sweep.csv")


# ----------------------------------------------------------------------------- operands
def expert_operands(layer, expert, mat, rows, acts):
    pk = hf.fetch(f"{P}layers.{layer}.block_sparse_moe.experts.{expert}.{mat}.weight_packed")[:rows]
    sc = hf.fetch(f"{P}layers.{layer}.block_sparse_moe.experts.{expert}.{mat}.weight_scale")[:rows]
    v2 = unpack_mxfp4_codes(pk).astype(np.int64)        # half units
    e = mxfp4_scale_exponents(sc).astype(np.int64) - 1  # value = v2 * 2^(e)
    if mat in ("w1", "w3"):
        X = acts[f"L{layer}.moe.expert.in"].astype(np.float64)
    else:
        X = acts[f"L{layer}.moe.w2.in"].astype(np.float64)[:32]
    return v2, e, X


def dense_operands(tname, aname, rows, acts):
    W = hf.fetch(tname)[:rows].astype(np.float64)
    mi, me = aligned_int(W, 8, group=32)                # MXINT8-style rendering of BF16 weights
    v = mi.reshape(W.shape).astype(np.int64)
    e = me[..., 0].astype(np.int64)
    X = acts[aname].astype(np.float64)
    return v, e, X, W


def map_weights(v, e, C, extra):
    """Return (Wint, w_exp[N,G], mag_bits) for C contributors per conversion."""
    N, K = v.shape
    B = 32
    base_bits = int(np.ceil(np.log2(np.abs(v).max() + 1)))
    if C <= B:
        reps = B // C
        return v, np.repeat(e, reps, axis=1), base_bits
    g = C // B
    G = K // C
    eg = e[:, :G * g].reshape(N, G, g)
    ref = eg.max(-1) - extra                                  # keep `extra` binades below the max block
    shift = np.repeat(eg - ref[..., None], B, axis=-1).reshape(N, K)   # >= -inf .. extra
    vv = v.astype(np.float64) * np.ldexp(1.0, shift)
    W = np.round(vv).astype(np.int64)                         # exact when shift >= 0 for all blocks
    return W, ref, base_bits + extra


def map_inputs(Xq, C, x_mag_bits):
    T, K = Xq.shape
    G = K // C
    xg = Xq.reshape(T, G, C)
    amax = np.abs(xg).max(-1)
    with np.errstate(divide="ignore"):
        emax = np.where(amax > 0, np.floor(np.log2(np.where(amax > 0, amax, 1.0))), -126)
    ex = (emax - (x_mag_bits - 1)).astype(np.int64)
    lim = 2 ** x_mag_bits - 1
    Xi = np.clip(np.round(xg / np.ldexp(1.0, ex)[..., None]), -lim, lim).astype(np.int64).reshape(T, K)
    return Xi, ex


def run_case(Wint, wexp, wbits, Xi, xexp, base_cfg, y_ref, budget, meta, rows_out):
    cfg = AnalogConfig(**{**base_cfg, "w_mag_bits": max(wbits, 1)})
    t0 = time.time()
    y, _ = analog_mvm(Wint, Xi, cfg, wexp, xexp)
    st = error_stats(y, y_ref)
    r = dict(meta)
    r.update({k: base_cfg.get(k) for k in ("cell_bits", "contributors", "bits_per_pass", "x_mag_bits", "adc_bits",
                                            "signed_mode", "device_model", "device_time_days", "sigma_prog_abs",
                                            "sigma_read_abs", "temp_gain", "temp_sigma_rel", "compression",
                                            "calibration", "spot_check_frac", "prog_verify_factor",
                                            "drift_mean_rel", "drift_sigma_rel", "adc_noise_lsb")})
    r.update({"w_mag_bits": wbits, "slices": cfg.n_slices, "passes": cfg.n_passes,
              "adc_exact_bits": cfg.exact_adc_bits(),
              "conversions_per_output_per_group": cfg.conversions_per_output_group(),
              "rel_rms_err": st["rel_rms_err"], "snr_db": st["snr_db"], "exact_frac": st["exact_frac"],
              "mxfp8_budget_err": budget, "budget_ratio": st["rel_rms_err"] / budget if budget else None,
              "sim_s": round(time.time() - t0, 3)})
    rows_out.append(r)
    return r


def verdict(ratio):
    if ratio is None:
        return ""
    if ratio <= 0.25:
        return "within_budget(<=25% of MXFP8 noise)"
    if ratio <= 1.0:
        return "marginal(<=MXFP8 noise; needs e2e eval)"
    return "exceeds_budget(likely accuracy loss)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--rows", type=int, default=128)
    args = ap.parse_args()
    acts = dict(np.load(ACT))
    rows_out = []
    R = args.rows

    # ---------------- operands: real expert (layer 1, most-routed expert) and a real dense op
    topk = acts["L1.moe.topk_idx"]
    expert = int(np.bincount(topk.ravel()).argmax())
    v, e, X = expert_operands(1, expert, "w1", R, acts)
    Wf = v.astype(np.float64) * np.ldexp(1.0, np.repeat(e, 32, axis=1))
    q, se = quantize_mxfp8(X)
    Xq = dequant_mx(q, se)
    y_bf = X @ Wf.T
    y_ref = Xq @ Wf.T
    budget = float(np.linalg.norm(y_ref - y_bf) / np.linalg.norm(y_bf))
    print(f"expert L1 #{expert} w1 tile {v.shape}, MXFP8 budget err {budget:.4f}", flush=True)
    operands = {"L1.expert.w1": (v, e, Xq, y_ref, budget, "mxfp4")}

    vd, ed, Xd, Wd_bf16 = dense_operands(f"{P}layers.0.self_attn.q_proj.weight", "L0.kda.in", R, acts)
    Wd = vd.astype(np.float64) * np.ldexp(1.0, np.repeat(ed, 32, axis=1))
    qd, sed = quantize_mxfp8(Xd)
    Xdq = dequant_mx(qd, sed)
    y_bf_d = Xd @ Wd_bf16.T
    y_ref_d = Xdq @ Wd.T
    budget_d = float(np.linalg.norm(Xdq @ Wd_bf16.T - y_bf_d) / np.linalg.norm(y_bf_d))
    w_requant_err = float(np.linalg.norm(Xdq @ Wd.T - Xdq @ Wd_bf16.T) / np.linalg.norm(Xdq @ Wd_bf16.T))
    print(f"dense L0 q_proj tile {vd.shape}, MXFP8 budget {budget_d:.4f}, MXINT8-weight requant err {w_requant_err:.4f}",
          flush=True)
    operands["L0.kda.q_proj(bf16->mxint8)"] = (vd, ed, Xdq, y_ref_d, budget_d, "mxint8")

    def prepare(name, C, xbits, extra):
        v_, e_, Xq_, y_ref_, budget_, kind = operands[name]
        Wint, wexp, wbits = map_weights(v_, e_, C, extra)
        Xi, xexp = map_inputs(Xq_, C, xbits)
        # representation-only error (no analog): weights aligned + inputs fixed-point
        Wrep = Wint.astype(np.float64) * np.ldexp(1.0, np.repeat(wexp, C, axis=1))
        Xrep = Xi.astype(np.float64) * np.ldexp(1.0, np.repeat(xexp, C, axis=1))
        rep_err = float(np.linalg.norm(Xrep @ Wrep.T - y_ref_) / np.linalg.norm(y_ref_))
        return Wint, wexp, wbits, Xi, xexp, y_ref_, budget_, rep_err

    # ---------------- Sweep A: ideal devices, full factorial over mapping x ADC
    Cs = [8, 16, 32, 64, 128, 256]
    cells = [1, 2, 3, 4]
    bpps = [1, 2, 4, 8]                 # bits per pass -> passes = 8,4,2,1 for 8-bit inputs
    adcs = list(range(4, 15))
    if args.quick:
        Cs, adcs = [32, 128], [6, 9, 12]
    xbits = 8
    t0 = time.time()
    for name in operands:
        for C in Cs:
            extra = 0 if C <= 32 else (1 if C <= 128 else 2)
            Wint, wexp, wbits, Xi, xexp, y_ref_, budget_, rep_err = prepare(name, C, xbits, extra)
            for cb, bpp in itertools.product(cells, bpps):
                acfg = AnalogConfig(cell_bits=cb, contributors=C, bits_per_pass=bpp, x_mag_bits=xbits,
                                    w_mag_bits=max(wbits, 1), signed_mode="differential", seed=1)
                t1 = time.time()
                ys, _ = analog_mvm_adc_sweep(Wint, Xi, acfg, adcs, wexp, xexp)
                for ab in adcs:
                    st = error_stats(ys[ab], y_ref_)
                    r = {"sweep": "A_ideal_device", "tensor": name, "evidence": "exact_math+ideal_device",
                         "representation_err": rep_err, "w_align_extra_bits": extra,
                         "cell_bits": cb, "contributors": C, "bits_per_pass": bpp, "x_mag_bits": xbits,
                         "adc_bits": ab, "signed_mode": "differential", "w_mag_bits": wbits,
                         "slices": acfg.n_slices, "passes": acfg.n_passes, "adc_exact_bits": acfg.exact_adc_bits(),
                         "conversions_per_output_per_group": acfg.conversions_per_output_group(),
                         "rel_rms_err": st["rel_rms_err"], "snr_db": st["snr_db"], "exact_frac": st["exact_frac"],
                         "mxfp8_budget_err": budget_, "budget_ratio": st["rel_rms_err"] / budget_,
                         "sim_s": round((time.time() - t1) / len(adcs), 3)}
                    r["verdict"] = verdict(r["budget_ratio"])
                    rows_out.append(r)
            print(f"  sweep A {name} C={C} done ({time.time() - t0:.0f}s)", flush=True)

    # ---------------- Sweep B: device non-idealities at representative mappings
    dev_cases = [
        ("SONOS_t0", dict(device_model="SONOS", device_time_days=0.0), "measured_device_model(CrossSim SONOS, planar 40nm)"),
        ("SONOS_t1d", dict(device_model="SONOS", device_time_days=1.0), "measured_device_model(CrossSim SONOS)"),
        ("SONOS_t5d", dict(device_model="SONOS", device_time_days=5.0), "measured_device_model(CrossSim SONOS)"),
        ("RRAM_Milo", dict(device_model="RRAMMilo"), "measured_device_model(CrossSim RRAM Milo IRPS21)"),
        ("RRAM_Wan", dict(device_model="RRAMWan"), "measured_device_model(CrossSim NeuRRAM Wan Nature22)"),
    ] + [(f"generic_sigma{s}", dict(sigma_prog_abs=s / 100, sigma_read_abs=s / 200), "parametric_assumption")
         for s in (0.25, 0.5, 1.0, 2.0, 4.0)]
    if args.quick:
        dev_cases = dev_cases[:2] + dev_cases[5:7]
    for name in operands:
        for C in ([32, 128] if not args.quick else [32]):
            extra = 0 if C <= 32 else 1
            Wint, wexp, wbits, Xi, xexp, y_ref_, budget_, rep_err = prepare(name, C, xbits, extra)
            for cb in cells:
                for bpp in (1, 8):
                    tmp = AnalogConfig(cell_bits=cb, contributors=C, bits_per_pass=bpp, x_mag_bits=xbits,
                                       w_mag_bits=wbits)
                    exact = tmp.exact_adc_bits()
                    for ab in sorted({min(exact, 14), min(exact, 14) - 2}):
                        for dname, dkw, ev in dev_cases:
                            for cal in ("none", "gain_offset", "adc_trim+gain_offset"):
                                if cal != "none" and not dname.startswith("SONOS_t5"):
                                    continue
                                cfg = dict(cell_bits=cb, contributors=C, bits_per_pass=bpp, x_mag_bits=xbits,
                                           adc_bits=ab, signed_mode="differential", calibration=cal, seed=2, **dkw)
                                r = run_case(Wint, wexp, wbits, Xi, xexp, cfg, y_ref_, budget_,
                                             {"sweep": "B_device", "tensor": name, "device_case": dname, "evidence": ev,
                                              "representation_err": rep_err, "w_align_extra_bits": extra}, rows_out)
                                r["verdict"] = verdict(r["budget_ratio"])
            print(f"  sweep B {name} C={C} done ({time.time() - t0:.0f}s)", flush=True)

    # ---------------- Sweep C: thermal, nonlinearity, aging, calibration, spot-check, program-verify
    name = "L1.expert.w1"
    C = 32
    Wint, wexp, wbits, Xi, xexp, y_ref_, budget_, rep_err = prepare(name, C, xbits, 0)
    base = dict(cell_bits=4, contributors=C, bits_per_pass=1, x_mag_bits=xbits, adc_bits=9, signed_mode="differential",
                device_model="SONOS", seed=3)
    variants = []
    for tg in (0.0, 0.02, 0.05, 0.10):              # global current change from temperature (e.g. +-25 C)
        for ts in (0.0, 0.01, 0.03):                # per-cell mismatch of temperature coefficient
            for cal in ("none", "gain_offset", "adc_trim", "adc_trim+gain_offset"):
                variants.append(("thermal", dict(temp_gain=tg, temp_sigma_rel=ts, calibration=cal), "parametric_assumption"))
    for a in (0.0, 0.02, 0.05, 0.1, 0.2):           # bitline compression / nonlinear summation
        for cal in ("none", "gain_offset"):
            variants.append(("nonlinear_bl", dict(compression=a, calibration=cal), "speculative_model"))
    for dm, ds in ((0.0, 0.0), (-0.02, 0.01), (-0.05, 0.02), (-0.10, 0.04)):   # aging / retention (generic)
        for cal in ("none", "gain_offset", "adc_trim", "adc_trim+gain_offset"):
            variants.append(("aging_drift", dict(drift_mean_rel=dm, drift_sigma_rel=ds, calibration=cal), "parametric_assumption"))
    for f in (0.0, 0.01, 0.05, 0.10):
        variants.append(("spot_check", dict(spot_check_frac=f), "exact_math"))
    for pv in (1.0, 2.0, 4.0):
        variants.append(("program_verify", dict(prog_verify_factor=pv), "parametric_assumption"))
    for an in (0.0, 0.5, 1.0):
        variants.append(("adc_noise", dict(adc_noise_lsb=an), "parametric_assumption"))
    if args.quick:
        variants = variants[::5]
    for vname, kw, ev in variants:
        cfg = {**base, **kw}
        r = run_case(Wint, wexp, wbits, Xi, xexp, cfg, y_ref_, budget_,
                     {"sweep": f"C_{vname}", "tensor": name, "device_case": "SONOS_t0+" + vname, "evidence": ev,
                      "representation_err": rep_err, "w_align_extra_bits": 0}, rows_out)
        r["verdict"] = verdict(r["budget_ratio"])
    print(f"  sweep C done ({time.time() - t0:.0f}s)", flush=True)

    keys = []
    for r in rows_out:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows_out)
    print(f"wrote {len(rows_out)} rows to {OUT}")


if __name__ == "__main__":
    main()
