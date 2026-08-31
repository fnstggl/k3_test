#!/usr/bin/env python3
"""Bit-exact golden model of rtl/k3_nand_reducer.sv + test-vector generator.

Mirrors the RTL exactly (including truncating conversions) so Verilator
equivalence is bit-for-bit; separately reports numerical error vs exact
double-precision math (the *inference fidelity* question).

Vector file format (text):
  line 1: n_blocks
  per block: "row wsc asc" then 32 lines "w_code a_code"
  footer: 8 lines "row_hex" (expected FP32 accumulator values, hex)
"""

import random
import struct
import sys

E2M1_K = [0, 1, 2, 3, 4, 6, 8, 12]
# all E4M3 codes except NaN (e=15, m=7)
VALID_E4M3 = [c for c in range(256)
              if not ((((c >> 3) & 0xF) == 0xF) and ((c & 0x7) == 0x7))]


def f32_bits(x: float) -> int:
    return struct.unpack("<I", struct.pack("<f", x))[0]


def bits_f32(b: int) -> float:
    return struct.unpack("<f", struct.pack("<I", b & 0xFFFFFFFF))[0]


def e4m3_value(code: int) -> float:
    s = -1.0 if code & 0x80 else 1.0
    e = (code >> 3) & 0xF
    m = code & 0x7
    if e == 0:
        return s * m * 2.0 ** -9
    return s * (8 + m) * 2.0 ** (e - 10)


def e2m1_value(code: int) -> float:
    v = E2M1_K[code & 0x7] / 2.0
    return -v if code & 0x8 else v


def block_fixed_acc(pairs) -> int:
    """Exact 30-bit signed block accumulate as in RTL."""
    acc = 0
    for w, a in pairs:
        k = E2M1_K[w & 0x7]
        s_w = (w >> 3) & 1
        e = (a >> 3) & 0xF
        m = a & 0x7
        sig = (8 + m) if e != 0 else m
        eeff = e if e != 0 else 1
        mag = (k * sig) << eeff
        s_a = (a >> 7) & 1
        acc += -mag if (s_w ^ s_a) else mag
    assert -(1 << 29) <= acc < (1 << 29)
    return acc


def block_to_fp32_bits(acc: int, wsc: int, asc: int) -> int:
    """Truncating conversion as in RTL."""
    if acc == 0:
        return 0
    sign = 1 if acc < 0 else 0
    mag = -acc if acc < 0 else acc
    msb = mag.bit_length() - 1              # position p (<=29)
    lzc = 29 - msb
    norm = (mag << lzc) & ((1 << 30) - 1)
    fmant = norm >> 6                        # 24 bits, truncate
    ebase = 127 + msb + wsc - 127 + asc - 127 - 11
    if ebase <= 0:
        fexp = 0
    elif ebase >= 255:
        fexp = 254
    else:
        fexp = ebase
    return (sign << 31) | (fexp << 23) | (fmant & 0x7FFFFF)


def fp32_add_trunc_bits(a: int, b: int) -> int:
    """Mirror RTL fp32_add_trunc exactly."""
    if a & 0x7FFFFFFF == 0:
        return b
    if b & 0x7FFFFFFF == 0:
        return a
    sa, ea, ma = (a >> 31) & 1, (a >> 23) & 0xFF, (a & 0x7FFFFF) | 0x800000
    sb, eb, mb = (b >> 31) & 1, (b >> 23) & 0xFF, (b & 0x7FFFFF) | 0x800000
    if (ea << 24) | ma >= (eb << 24) | mb:
        eg, mg, sr = ea, ma << 3, sa
        d = min(ea - eb, 26)
        ml = (mb << 3) >> d
        sum_ = mg + ml if sa == sb else mg - ml
    else:
        eg, mg, sr = eb, mb << 3, sb
        d = min(eb - ea, 26)
        ml = (ma << 3) >> d
        sum_ = mg + ml if sa == sb else mg - ml
    if sum_ == 0:
        return 0
    msb = sum_.bit_length() - 1
    lz2 = 27 - msb
    if lz2 <= 1:
        sum_ >>= (1 - lz2)
        er = (eg + (1 - lz2)) & 0xFF
    else:
        sum_ = (sum_ << (lz2 - 1)) & ((1 << 28) - 1)
        er = (eg - (lz2 - 1)) & 0xFF
    return (sr << 31) | (er << 23) | ((sum_ >> 3) & 0x7FFFFF)


def gen(n_blocks: int, seed: int, path: str, stats_out=sys.stderr):
    rng = random.Random(seed)
    rows_bits = [0] * 8
    rows_exact = [0.0] * 8
    lines = [str(n_blocks)]
    for _ in range(n_blocks):
        row = rng.randrange(8)
        wsc = rng.randrange(100, 155)       # E8M0 codes in a realistic band
        asc = rng.randrange(100, 155)
        pairs = [(rng.randrange(16), rng.choice(VALID_E4M3))
                 for _ in range(32)]
        lines.append(f"{row} {wsc} {asc}")
        lines.extend(f"{w} {a}" for w, a in pairs)
        acc = block_fixed_acc(pairs)
        bf = block_to_fp32_bits(acc, wsc, asc)
        rows_bits[row] = fp32_add_trunc_bits(rows_bits[row], bf)
        exact = sum(e2m1_value(w) * e4m3_value(a) for w, a in pairs) \
            * 2.0 ** (wsc - 127) * 2.0 ** (asc - 127)
        rows_exact[row] += exact
    lines.extend(f"{rb:08x}" for rb in rows_bits)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    # numerical fidelity of the truncating datapath vs exact math
    errs = []
    for rb, ex in zip(rows_bits, rows_exact):
        got = bits_f32(rb)
        if ex != 0:
            errs.append(abs(got - ex) / abs(ex))
    if errs:
        print(f"golden: max rel err vs exact = {max(errs):.3e} "
              f"(n_blocks={n_blocks})", file=stats_out)
    return rows_bits


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    path = sys.argv[3] if len(sys.argv) > 3 else "vectors.txt"
    gen(n, seed, path)
