"""OCP Microscaling (MX) format reference model.

Source: OCP Microscaling Formats (MX) Specification v1.0 (Rouhani et al., 2023),
the format K3 ships (TR §4.1.4 cites [104]).

  MXFP4: block of 32 FP4 (E2M1) elements + one shared E8M0 scale (power of two).
  MXFP8: block of 32 FP8 (E4M3) elements + one shared E8M0 scale.

This is the functional ground truth for:
  - Gate 4: what arithmetic a NAND-internal primitive set must realize
  - Gate 7: RTL equivalence testing (rtl/ vs this model)

Dot-product semantics modeled after hardware MX GEMM (e.g. Blackwell/DeepGEMM
`fp8_fp4_mega_moe`): per 32-block, integer/FP products accumulate exactly, scaled
by 2^(e_w + e_a); block partials accumulate in FP32.
"""

from dataclasses import dataclass
import math

# E2M1 magnitude table (sign separate): 1 sign + 2 exp + 1 mantissa
# codes 0..7 -> 0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0
E2M1_VALUES = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0]

E4M3_MAX = 448.0
E2M1_MAX = 6.0
BLOCK = 32


def e2m1_encode(x: float) -> int:
    """Nearest-even encode of a real to signed E2M1 (4-bit code 0..15)."""
    s = 1 if x < 0 else 0
    a = abs(x)
    best, bi = None, 0
    for i, v in enumerate(E2M1_VALUES):
        d = abs(a - v)
        if best is None or d < best - 1e-30 or (abs(d - best) <= 1e-30 and i % 2 == 0):
            best, bi = d, i
    return (s << 3) | bi


def e2m1_decode(code: int) -> float:
    v = E2M1_VALUES[code & 0x7]
    return -v if code & 0x8 else v


def e8m0_encode(scale: float) -> int:
    """Power-of-two scale exponent, biased 127 (0..254; 255=NaN unused here)."""
    if scale <= 0:
        return 0
    e = int(math.floor(math.log2(scale)))
    return max(0, min(254, e + 127))


def e8m0_decode(code: int) -> float:
    return 2.0 ** (code - 127)


def e4m3_decode(code: int) -> float:
    """Decode an 8-bit E4M3 code to its real value (sign,4-exp,3-mant).
    Normals: (8+m)*2^(e-10); subnormals (e=0): m*2^-9. e=15,m=7 = NaN (excluded)."""
    s = -1.0 if code & 0x80 else 1.0
    e = (code >> 3) & 0xF
    m = code & 0x7
    if e == 0:
        return s * m * 2.0 ** -9
    return s * (8 + m) * 2.0 ** (e - 10)


def e4m3_quantize(x: float) -> float:
    """Round a real to the E4M3 grid (saturating, no inf)."""
    if x == 0.0:
        return 0.0
    s = -1.0 if x < 0 else 1.0
    a = min(abs(x), E4M3_MAX)
    e = math.floor(math.log2(a))
    e = max(e, -6)                      # subnormal floor
    m = a / 2.0 ** e                    # in [1,2) normally
    q = round(m * 8) / 8.0              # 3 mantissa bits
    v = q * 2.0 ** e
    if v > E4M3_MAX:
        v = E4M3_MAX
    return s * v


@dataclass
class MxBlock:
    """One 32-element MX block: element codes + shared E8M0 exponent code."""
    scale_code: int
    codes: list


def mxfp4_quantize_block(vals: list) -> MxBlock:
    """OCP MX quantization: shared scale = 2^floor(log2(max)) / max_elem_pow2."""
    amax = max((abs(v) for v in vals), default=0.0)
    if amax == 0.0:
        return MxBlock(e8m0_encode(1.0), [0] * len(vals))
    # per OCP spec: X = 2^(floor(log2(amax)) - emax_elem), emax(E2M1)=2 (val 4.0->6.0 top)
    shared = 2.0 ** (math.floor(math.log2(amax)) - 2)
    codes = [e2m1_encode(v / shared) for v in vals]
    return MxBlock(e8m0_encode(shared), codes)


def mxfp4_dequant(block: MxBlock) -> list:
    s = e8m0_decode(block.scale_code)
    return [e2m1_decode(c) * s for c in block.codes]


def mx_dot_block(w_block: MxBlock, a_vals: list, a_scale_code: int,
                 a_codes_are_e4m3: bool = True) -> float:
    """Reference MXFP4(w) x MXFP8(a) block dot product with FP32 accumulation.

    a_vals: already-decoded E4M3 element values (without scale).
    Result = 2^(ew+ea-254) * sum(w_i * a_i) accumulated exactly then FP32-rounded.
    """
    acc = 0.0
    for c, av in zip(w_block.codes, a_vals):
        acc += e2m1_decode(c) * av
    return acc * e8m0_decode(w_block.scale_code) * e8m0_decode(a_scale_code)


def mx_dot(w_blocks: list, a_blocks: list) -> float:
    """Full dot product across block lists: [(MxBlock, a_vals, a_scale_code)]."""
    total = 0.0
    for wb, (avals, ascale) in zip(w_blocks, a_blocks):
        total += mx_dot_block(wb, avals, ascale)
    return total


# --- integer-arithmetic view (what minimal hardware must implement) ---------

def e2m1_as_int_halves(code: int) -> int:
    """E2M1 magnitudes are exactly k/2 for k in {0,1,2,3,4,6,8,12}: return signed k.
    A w*a product is then (k * a) >> 1 — i.e. shift-add only, no multiplier."""
    k = [0, 1, 2, 3, 4, 6, 8, 12][code & 0x7]
    return -k if code & 0x8 else k
