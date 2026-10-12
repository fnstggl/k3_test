"""Vectorised numerical model of an analog compute-in-memory matrix-vector multiply.

The model operates on *exact integer* renderings of MX-format operands, so it
can be compared bit-for-bit with an exact digital dot product:

    y[n] = sum_g  2^(ew[n,g] + ex[g]) * sum_{k in g} Wint[n,k] * Xint[k]

g = contributor group (C rows summed on one bitline per conversion).

Physical chain simulated per (weight slice j, input pass p, sign phase):
  1. weight magnitude |Wint| split into `n_slices` cells of `cell_bits` each
     (unsigned levels 0..2^b-1); sign by differential pair (separate pos/neg
     arrays, digitised separately) or by offset (+2^(B-1), offset removed
     digitally using sum(x) - an exact digital side computation);
  2. input magnitude |Xint| split into passes of `bits_per_pass` bits; input
     sign by two phases (positive / negative inputs applied separately);
  3. bitline sum  S = sum_k G[n,k] * u[k]  with
       G = level * (1 + gain_err) + prog_err (static per cell, programming),
       plus read noise (per operation), temperature gain, drift,
       optional saturating compression  S' = S / (1 + a * S/S_fs);
  4. ADC: uniform `adc_bits` over [0, FS]; FS = exact max (no clipping) or
     a calibrated percentile; optional ADC noise (LSB rms);
  5. digital shift-and-add over slices and passes, signs, scales;
  6. optional calibration (per-output gain/offset from calibration vectors)
     and spot-checking (fraction of outputs recomputed digitally).

All noise magnitudes are expressed as fractions of the *maximum cell
current* I_max (= level 2^b-1), which is how SONOS/RRAM/NAND papers report
them.  Physical presets live in k3cim/devices.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np


@dataclass
class AnalogConfig:
    cell_bits: int = 4               # 1=SLC 2=MLC 3=TLC 4=QLC
    w_mag_bits: int = 4              # magnitude bits of integer weights (E2M1 half-units -> 4)
    signed_mode: str = "differential"  # differential | offset
    contributors: int = 32           # rows summed per conversion (per bitline group)
    x_mag_bits: int = 8              # magnitude bits of integer activations
    bits_per_pass: int = 1           # 1, 2, 4, 8 (input bits encoded per analog step)
    adc_bits: int = 8
    adc_range: str = "max"           # max | percentile
    adc_percentile: float = 99.99
    adc_noise_lsb: float = 0.0
    # device non-idealities (fractions of I_max of one cell)
    sigma_prog_abs: float = 0.0      # state-independent programming error
    sigma_prog_rel: float = 0.0      # state-proportional programming error (x level)
    sigma_read_abs: float = 0.0      # per-read noise (state independent)
    sigma_read_rel: float = 0.0
    drift_mean_rel: float = 0.0      # mean relative current shift after retention time
    drift_sigma_rel: float = 0.0     # cell-to-cell spread of drift
    temp_gain: float = 0.0           # global multiplicative error (temperature), calibratable
    temp_sigma_rel: float = 0.0      # per-cell mismatch of temperature coefficient
    off_current: float = 0.0         # leakage of level-0 cells (fraction of I_max)
    compression: float = 0.0         # bitline compression coefficient a (speculative)
    device_model: str | None = None  # CrossSim measured model: SONOS | RRAMMilo | RRAMWan (overrides prog/read sigmas)
    device_time_days: float = 0.0    # retention time for CrossSim drift model (SONOS: 0..5 days measured)
    # mitigation
    calibration: str = "none"        # none | gain_offset (digital post-correction) | adc_trim (ADC reference
                                     # tracks the global gain via reference columns) | adc_trim+gain_offset
    prog_verify_factor: float = 1.0  # divide programming sigma (write-verify iterations)
    spot_check_frac: float = 0.0
    seed: int = 0

    @property
    def n_slices(self):
        return max(1, math.ceil(self.w_mag_bits / self.cell_bits))

    @property
    def n_passes(self):
        return max(1, math.ceil(self.x_mag_bits / self.bits_per_pass))

    def conversions_per_output_group(self):
        sign_w = 2 if self.signed_mode == "differential" else 1
        return self.n_slices * self.n_passes * 2 * sign_w   # x2: input sign phases

    def exact_adc_bits(self):
        """ADC bits needed to represent every possible bitline sum without loss."""
        lv = 2 ** self.cell_bits - 1
        if self.signed_mode == "offset":
            lv = 2 ** self.cell_bits - 1
        smax = self.contributors * lv * (2 ** self.bits_per_pass - 1)
        return math.ceil(math.log2(smax + 1))


def _split_unsigned(a, nbits_per, nparts):
    """Split non-negative integer array into little-endian digits of nbits_per bits."""
    base = 1 << nbits_per
    out = []
    r = a.astype(np.int64)
    for _ in range(nparts):
        out.append(r % base)
        r = r // base
    assert np.all(r == 0), "value exceeds representable range"
    return out


def analog_mvm(Wint, Xint, cfg: AnalogConfig, w_exp=None, x_exp=None, return_parts=False):
    """Simulate y = W x for integer matrices with per-group power-of-two scales.

    Wint: [N, K] signed integers (|W| < 2^w_mag_bits)
    Xint: [T, K] signed integers (|X| < 2^x_mag_bits)  (T = batch of input vectors)
    w_exp: [N, G] exponents per contributor group (G = K / C) or None (=0)
    x_exp: [T, G] exponents per group or None
    Returns (y_analog [T, N], y_exact [T, N]) as float64.
    """
    rng = np.random.default_rng(cfg.seed)
    N, K = Wint.shape
    T = Xint.shape[0]
    C = cfg.contributors
    assert K % C == 0, (K, C)
    G = K // C
    w_exp = np.zeros((N, G), np.int64) if w_exp is None else np.asarray(w_exp)
    x_exp = np.zeros((T, G), np.int64) if x_exp is None else np.asarray(x_exp)
    assert np.abs(Wint).max(initial=0) < 2 ** cfg.w_mag_bits
    assert np.abs(Xint).max(initial=0) < 2 ** cfg.x_mag_bits

    Wg = Wint.reshape(N, G, C).astype(np.float64)
    Xg = Xint.reshape(T, G, C).astype(np.float64)
    scale = np.ldexp(1.0, (w_exp[None, :, :] + x_exp[:, None, :]))  # [T, N, G]
    y_exact = (np.einsum("ngc,tgc->tng", Wg, Xg) * scale).sum(-1)

    lv_max = 2 ** cfg.cell_bits - 1
    # ---------------------------------------------------------------- weights -> cells
    if cfg.signed_mode == "differential":
        mags = [np.maximum(Wint, 0), np.maximum(-Wint, 0)]
        wsigns = [1.0, -1.0]
        offset = 0
    elif cfg.signed_mode == "offset":
        offset = 2 ** cfg.w_mag_bits
        mags = [Wint + offset]          # 0 .. 2^(B+1)-1
        wsigns = [1.0]
    else:
        raise ValueError(cfg.signed_mode)
    nsl = cfg.n_slices if cfg.signed_mode == "differential" else max(
        1, math.ceil((cfg.w_mag_bits + 1) / cfg.cell_bits))

    read_sig = {}

    def cell_currents(level):
        """Static per-cell current (in units of one level) incl. programming/drift errors."""
        L = level.astype(np.float64)
        if cfg.device_model:
            from .devices import crosssim_cell_currents
            I, sig = crosssim_cell_currents(level, cfg.cell_bits, cfg.device_model, cfg.device_time_days,
                                            seed=int(rng.integers(1 << 30)))
            # program-verify tightening applies to the programming component only
            if cfg.prog_verify_factor != 1.0:
                I = L + (I - L) / cfg.prog_verify_factor
            read_sig[id(level)] = sig
        else:
            sp = (cfg.sigma_prog_abs * lv_max + cfg.sigma_prog_rel * L) / cfg.prog_verify_factor
            I = L.copy()
            if np.any(sp > 0):
                I += sp * rng.standard_normal(L.shape)
        if cfg.drift_mean_rel or cfg.drift_sigma_rel:
            I *= 1.0 + cfg.drift_mean_rel + cfg.drift_sigma_rel * rng.standard_normal(L.shape)
        if cfg.temp_sigma_rel:
            I *= 1.0 + cfg.temp_sigma_rel * rng.standard_normal(L.shape)
        I += cfg.off_current * lv_max * (L == 0)
        I *= 1.0 + cfg.temp_gain
        return np.maximum(I, 0.0)

    cells = []   # list of (sign, slice_weight, currents[N,G,C], level[N,G,C])
    for m, sgn in zip(mags, wsigns):
        for j, lev in enumerate(_split_unsigned(m, cfg.cell_bits, nsl)):
            levg = lev.reshape(N, G, C)
            cells.append((sgn, float(2 ** (cfg.cell_bits * j)), cell_currents(levg), levg))

    # ---------------------------------------------------------------- inputs -> passes
    xs = [(1.0, np.maximum(Xint, 0)), (-1.0, np.maximum(-Xint, 0))]
    npass = cfg.n_passes
    umax = 2 ** cfg.bits_per_pass - 1
    smax_exact = C * lv_max * umax
    if cfg.adc_range == "max":
        fs = smax_exact
    else:
        fs = None  # set per conversion type below from percentile of ideal sums

    y_int = np.zeros((T, N, G))
    for xsgn, xm in xs:
        for p, u in enumerate(_split_unsigned(xm, cfg.bits_per_pass, npass)):
            ug = u.reshape(T, G, C).astype(np.float64)
            if not ug.any():
                continue
            pw = float(2 ** (cfg.bits_per_pass * p))
            for wsgn, sw, I, lev in cells:
                S = np.einsum("ngc,tgc->tng", I, ug)          # analog bitline sums
                var_cell = None
                if cfg.device_model and id(lev) in read_sig:
                    var_cell = read_sig[id(lev)] ** 2
                elif cfg.sigma_read_abs or cfg.sigma_read_rel:
                    var_cell = (cfg.sigma_read_abs * lv_max + cfg.sigma_read_rel * lev) ** 2
                if var_cell is not None and np.any(var_cell > 0):
                    var = np.einsum("ngc,tgc->tng", var_cell, ug ** 2)
                    S = S + np.sqrt(var) * rng.standard_normal(S.shape)
                if cfg.compression:
                    S = S / (1.0 + cfg.compression * S / smax_exact)
                if fs is None:
                    ideal = np.einsum("ngc,tgc->tng", lev.astype(np.float64), ug)
                    fsc = max(np.percentile(ideal, cfg.adc_percentile), 1.0)
                else:
                    fsc = fs
                nlev = 2 ** cfg.adc_bits - 1
                if fs is None:
                    lsb = fsc / nlev
                else:
                    # power-of-two LSB (in unit-cell currents): exact when the ADC
                    # covers the full sum range, otherwise drops low-order bits
                    lsb = float(2 ** max(0, math.ceil(math.log2(fsc / nlev))))
                if cfg.calibration.startswith("adc_trim"):
                    # reference columns track global current scale (temperature, mean drift)
                    lsb *= (1.0 + cfg.temp_gain) * (1.0 + cfg.drift_mean_rel)
                q = S / lsb
                if cfg.adc_noise_lsb:
                    q = q + cfg.adc_noise_lsb * rng.standard_normal(q.shape)
                q = np.clip(np.rint(q), 0, nlev) * lsb
                if cfg.calibration.startswith("adc_trim"):
                    q = q / ((1.0 + cfg.temp_gain) * (1.0 + cfg.drift_mean_rel))
                y_int += xsgn * wsgn * sw * pw * q
    if cfg.signed_mode == "offset":
        # remove offset * sum(x) exactly in digital
        y_int -= offset * Xg.sum(-1)[:, None, :]
    y = (y_int * scale).sum(-1)

    if cfg.calibration in ("gain_offset", "adc_trim+gain_offset"):
        y = _calibrate_gain_offset(Wint, cfg, w_exp, y, y_exact, Xint, x_exp)
    if cfg.spot_check_frac > 0:
        n_spot = int(round(cfg.spot_check_frac * N))
        if n_spot:
            idx = rng.choice(N, n_spot, replace=False)
            y[:, idx] = y_exact[:, idx]
    if return_parts:
        return y, y_exact, {"fs": fs}
    return y, y_exact


def _calibrate_gain_offset(Wint, cfg, w_exp, y, y_exact, Xint, x_exp):
    """Per-output linear correction fitted on independent calibration inputs.

    Calibration vectors are random integer inputs with the same group exponents;
    the hardware runs them once (after programming / periodically), compares to
    a digitally computed reference and stores (gain, offset) per output.  This
    removes systematic errors (temperature gain, mean drift, compression trend)
    but not random per-cell errors.
    """
    T_cal = 64
    rng = np.random.default_rng(cfg.seed + 7919)
    lim = 2 ** cfg.x_mag_bits - 1
    Xc = rng.integers(-lim, lim + 1, size=(T_cal, Xint.shape[1]))
    xe = np.repeat(x_exp[:1], T_cal, axis=0)
    cfg2 = replace(cfg, calibration="none", spot_check_frac=0.0)  # same seed -> same static cell errors
    yc, yc_ex = analog_mvm(Wint, Xc, cfg2, w_exp, xe)
    A = np.stack([yc_ex, np.ones_like(yc_ex)], -1)            # [Tc, N, 2]
    out = np.empty_like(y)
    for n in range(y.shape[1]):
        coef, *_ = np.linalg.lstsq(A[:, n, :], yc[:, n], rcond=None)
        g, o = coef
        out[:, n] = (y[:, n] - o) / (g if abs(g) > 1e-9 else 1.0)
    return out


def error_stats(y, y_ref):
    d = y - y_ref
    rms_ref = np.sqrt(np.mean(y_ref ** 2))
    rel_rms = np.sqrt(np.mean(d ** 2)) / rms_ref if rms_ref > 0 else 0.0
    exact_frac = float(np.mean(np.abs(d) <= 1e-9 * max(rms_ref, 1e-30)))
    snr_db = 20 * np.log10(1.0 / rel_rms) if rel_rms > 0 else float("inf")
    return {"rel_rms_err": float(rel_rms), "snr_db": float(snr_db), "exact_frac": exact_frac,
            "max_abs_err_rel": float(np.max(np.abs(d)) / rms_ref) if rms_ref > 0 else 0.0}


def analog_mvm_adc_sweep(Wint, Xint, cfg: AnalogConfig, adc_bits_list, w_exp=None, x_exp=None,
                         calib_mask=None, percentile=99.99):
    """Ideal-device fast path: compute every bitline sum once, then quantise for each ADC resolution.

    Equivalent to calling analog_mvm(..., replace(cfg, adc_bits=b)) for each b when the device
    is ideal (no programming/read noise, drift, temperature, compression) and adc_range == "max".
    If calib_mask (bool[T]) is given, the ADC full scale of every conversion type (slice x pass x sign)
    is instead calibrated to the `percentile` of the bitline sums of the calibration vectors
    (calib_mask True) and applied unchanged to all vectors (sums above FS clip).
    Returns ({b: y_analog}, y_exact).
    """
    assert not (cfg.device_model or cfg.sigma_prog_abs or cfg.sigma_prog_rel or cfg.sigma_read_abs
                or cfg.sigma_read_rel or cfg.compression or cfg.temp_gain or cfg.drift_mean_rel
                or cfg.adc_noise_lsb), "fast path is for ideal devices only"
    N, K = Wint.shape
    T = Xint.shape[0]
    C = cfg.contributors
    G = K // C
    w_exp = np.zeros((N, G), np.int64) if w_exp is None else np.asarray(w_exp)
    x_exp = np.zeros((T, G), np.int64) if x_exp is None else np.asarray(x_exp)
    Wg = Wint.reshape(N, G, C).astype(np.float64)
    Xg = Xint.reshape(T, G, C).astype(np.float64)
    scale = np.ldexp(1.0, (w_exp[None, :, :] + x_exp[:, None, :]))
    y_exact = (np.einsum("ngc,tgc->tng", Wg, Xg) * scale).sum(-1)
    lv_max = 2 ** cfg.cell_bits - 1
    if cfg.signed_mode == "differential":
        mags, wsigns, offset = [np.maximum(Wint, 0), np.maximum(-Wint, 0)], [1.0, -1.0], 0
        nsl = cfg.n_slices
    else:
        offset = 2 ** cfg.w_mag_bits
        mags, wsigns = [Wint + offset], [1.0]
        nsl = max(1, math.ceil((cfg.w_mag_bits + 1) / cfg.cell_bits))
    cells = []
    for m, sgn in zip(mags, wsigns):
        for j, lev in enumerate(_split_unsigned(m, cfg.cell_bits, nsl)):
            cells.append((sgn, float(2 ** (cfg.cell_bits * j)), lev.reshape(N, G, C).astype(np.float64)))
    umax = 2 ** cfg.bits_per_pass - 1
    smax = C * lv_max * umax
    acc = {b: np.zeros((T, N, G)) for b in adc_bits_list}
    for xsgn, xm in ((1.0, np.maximum(Xint, 0)), (-1.0, np.maximum(-Xint, 0))):
        for p, u in enumerate(_split_unsigned(xm, cfg.bits_per_pass, cfg.n_passes)):
            ug = u.reshape(T, G, C).astype(np.float64)
            if not ug.any():
                continue
            pw = float(2 ** (cfg.bits_per_pass * p))
            for wsgn, sw, lev in cells:
                S = np.einsum("ngc,tgc->tng", lev, ug)
                if calib_mask is not None:
                    fs_cal = max(float(np.percentile(S[calib_mask], percentile)), 1.0)
                for b in adc_bits_list:
                    nlev = 2 ** b - 1
                    if calib_mask is None:
                        lsb = float(2 ** max(0, math.ceil(math.log2(smax / nlev))))
                    else:
                        # enough levels for unit resolution -> exact integer LSB; else spread FS over the codes
                        lsb = 1.0 if fs_cal <= nlev else fs_cal / nlev
                    acc[b] += xsgn * wsgn * sw * pw * np.clip(np.rint(S / lsb), 0, nlev) * lsb
    out = {}
    for b in adc_bits_list:
        y = acc[b]
        if cfg.signed_mode == "offset":
            y = y - offset * Xg.sum(-1)[:, None, :]
        out[b] = (y * scale).sum(-1)
    return out, y_exact
