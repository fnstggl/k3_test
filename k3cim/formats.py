"""Exact numerics for the tensor formats used by Kimi K3.

* MXFP4 (OCP MX v1.0): E2M1 elements, one E8M0 (power-of-two) scale per
  block of 32 elements along the reduction (input) dimension.  The K3
  checkpoint stores them in compressed-tensors "mxfp4-pack-quantized" layout:
  two 4-bit codes per uint8 (low nibble = even element), bit 3 = sign,
  code 0..7 -> {0, .5, 1, 1.5, 2, 3, 4, 6}; scale uint8 u -> 2**(u-127).
* MXFP8 E4M3 activations: E4M3 elements (bias 7, max 448, subnormal step
  2**-9), one E8M0 scale per 32 elements, shared exponent
  floor(log2(amax)) - 8 (OCP rule), saturating conversion.
* BF16 rounding (round-to-nearest-even).

All decoding is exact in float64 (every MXFP4 x MXFP8 product and every
partial sum of up to 2**20 such products is exactly representable).

Integer representations used by the compute-in-memory mapping:
* E2M1 code value in half-units: v2 = 2*v in {-12..12} (4 magnitude bits + sign).
* E4M3 value in units of 2**-9: integer magnitude <= 448*512 = 229376
  (18 magnitude bits) -- i.e. an exact fixed-point rendering of one FP8
  activation needs 18+1 bits, not 8.
"""
import numpy as np

E2M1_VALUES = np.array([0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0])
E2M1_MAX = 6.0
E4M3_MAX = 448.0
E4M3_MIN_NORMAL_EXP = -6
E4M3_MANT_BITS = 3
MX_BLOCK = 32
E2M1_EMAX = 2   # floor(log2(6))
E4M3_EMAX = 8   # floor(log2(448))


# ----------------------------------------------------------------------------- BF16
def bf16_round(x):
    """Round float32/float64 array to bfloat16 (RNE), returned as float32."""
    x = np.asarray(x, dtype=np.float32)
    u = x.view(np.uint32).astype(np.uint64)
    rounding_bias = ((u >> 16) & 1) + 0x7FFF
    u = ((u + rounding_bias) >> 16) << 16
    out = u.astype(np.uint32).view(np.float32)
    return np.where(np.isnan(x), x, out)


# ----------------------------------------------------------------------------- MXFP4
def unpack_mxfp4_codes(packed):
    """uint8 [N, K/2] -> signed half-unit integers int8 [N, K] in {-12..12}."""
    packed = np.asarray(packed, dtype=np.uint8)
    lo = packed & 0x0F
    hi = packed >> 4
    codes = np.empty(packed.shape[:-1] + (packed.shape[-1] * 2,), dtype=np.uint8)
    codes[..., 0::2] = lo
    codes[..., 1::2] = hi
    mag_half = (E2M1_VALUES * 2).astype(np.int8)[codes & 0x7]
    sign = np.where(codes & 0x8, -1, 1).astype(np.int8)
    return (mag_half * sign).astype(np.int8)


def mxfp4_scale_exponents(scale_u8):
    """uint8 E8M0 -> int exponent e such that block scale = 2**e."""
    return np.asarray(scale_u8, dtype=np.int32) - 127


def dequant_mxfp4(packed, scale_u8):
    """Exact float64 weights W[N, K] from packed codes and E8M0 scales."""
    v2 = unpack_mxfp4_codes(packed).astype(np.float64)       # half units
    e = mxfp4_scale_exponents(scale_u8)                       # [N, K/32]
    scale = np.ldexp(0.5, e)                                  # 0.5 * 2**e (half-unit -> value)
    return v2 * np.repeat(scale, MX_BLOCK, axis=-1)


def round_e2m1(x):
    """Round to nearest E2M1 value (RNE), saturating at +-6."""
    x = np.asarray(x, dtype=np.float64)
    a = np.abs(x)
    with np.errstate(divide="ignore"):
        e = np.floor(np.log2(np.where(a > 0, a, 1.0)))
    step = np.ldexp(1.0, (np.maximum(e, 0) - 1).astype(int))
    q = np.round(a / step) * step
    q = np.minimum(q, E2M1_MAX)
    return np.sign(x) * q


def quantize_mxfp4(x, block=MX_BLOCK):
    """OCP MXFP4 quantization along the last axis. Returns (values_e2m1, scale_exp)."""
    x = np.asarray(x, dtype=np.float64)
    xb = x.reshape(x.shape[:-1] + (-1, block))
    amax = np.abs(xb).max(axis=-1, keepdims=True)
    with np.errstate(divide="ignore"):
        se = np.where(amax > 0, np.floor(np.log2(np.where(amax > 0, amax, 1.0))) - E2M1_EMAX, -127)
    se = se.astype(np.int32)
    q = round_e2m1(xb / np.ldexp(1.0, se))
    return q.reshape(x.shape), se[..., 0]


# ----------------------------------------------------------------------------- E4M3 / MXFP8
def round_e4m3(x):
    """Round to nearest FP8-E4M3 value (RNE), saturating at +-448."""
    x = np.asarray(x, dtype=np.float64)
    a = np.abs(x)
    with np.errstate(divide="ignore"):
        e = np.floor(np.log2(np.where(a > 0, a, 1.0)))
    e = np.maximum(e, E4M3_MIN_NORMAL_EXP)
    step = np.ldexp(1.0, (e - E4M3_MANT_BITS).astype(int))
    q = np.round(a / step) * step
    q = np.minimum(q, E4M3_MAX)
    return np.sign(x) * q


def quantize_mxfp8(x, block=MX_BLOCK):
    """OCP MXFP8-E4M3 quantization along the last axis.

    Returns (elements, scale_exp) with x ~= elements * 2**scale_exp (per block).
    """
    x = np.asarray(x, dtype=np.float64)
    shp = x.shape
    xb = x.reshape(shp[:-1] + (-1, block))
    amax = np.abs(xb).max(axis=-1, keepdims=True)
    with np.errstate(divide="ignore"):
        se = np.where(amax > 0, np.floor(np.log2(np.where(amax > 0, amax, 1.0))) - E4M3_EMAX, -127)
    se = se.astype(np.int32)
    q = round_e4m3(xb / np.ldexp(1.0, se))
    return q.reshape(shp), se[..., 0]


def dequant_mx(elements, scale_exp, block=MX_BLOCK):
    s = np.ldexp(1.0, np.repeat(scale_exp, block, axis=-1))
    return elements * s


def mxfp8_roundtrip(x, block=MX_BLOCK):
    q, se = quantize_mxfp8(x, block)
    return dequant_mx(q, se, block)


def e4m3_to_int(elements):
    """Exact integer rendering of E4M3 values in units of 2**-9 (|int| <= 229376)."""
    return np.rint(np.asarray(elements, dtype=np.float64) * 512.0).astype(np.int64)


def aligned_int(values, bits, axis=-1, group=None):
    """Block-floating-point (MXINT-style) rendering with `bits` signed magnitude bits.

    Each group (default: whole last axis) is scaled by a power of two so that its
    max magnitude fits in `bits` magnitude bits; values are rounded (RNE).
    Returns (ints, exponent) with values ~= ints * 2**exponent.  Lossless iff
    every value is a multiple of 2**exponent.
    """
    v = np.asarray(values, dtype=np.float64)
    if group is not None:
        v = v.reshape(v.shape[:-1] + (-1, group))
    amax = np.abs(v).max(axis=-1, keepdims=True)
    with np.errstate(divide="ignore"):
        emax = np.where(amax > 0, np.floor(np.log2(np.where(amax > 0, amax, 1.0))), -126)
    exp = (emax - (bits - 1)).astype(np.int32)
    ints = np.round(v / np.ldexp(1.0, exp))
    lim = 2 ** bits - 1
    ints = np.clip(ints, -lim, lim)
    return ints, exp
