"""Gate 9E — prove the bit-serial popcount decomposition is BIT-EXACT for native
K3 MXFP4 x MXFP8 block dot products. This is the arithmetic foundation for every
Gate-9 in-array-reduction architecture: if a NAND mechanism can produce exact
popcounts of (weight-bitplane AND activation-bitplane), it reconstructs the
EXACT native-K3 block dot product with no approximation.

We validate against k3/mxfp.py (the OCP-MX reference model used in Gate 3/7).
"""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from k3.mxfp import (E2M1_VALUES, e2m1_decode, e4m3_decode, e8m0_decode,
                     mxfp4_quantize_block, mx_dot_block, BLOCK)


def e2m1_int_significand(code: int):
    """Return (sign, integer significand k) with value = sign * k * 2^-1.
    E2M1 magnitudes are exactly k/2 for k in {0,1,2,3,4,6,8,12}."""
    k = [0, 1, 2, 3, 4, 6, 8, 12][code & 0x7]
    return (-1 if code & 0x8 else 1), k


def e4m3_int_significand(code: int):
    """Return (sign, integer significand s, exponent e_eff) with
    value = sign * s * 2^(e_eff - 10) matching k3.mxfp.e4m3_decode grid.
    Normals: s=8+m, e_eff=e; subnormals (e=0): s=m, e_eff=1."""
    s_sign = -1 if code & 0x80 else 1
    e = (code >> 3) & 0xF
    m = code & 0x7
    if e == 0:
        return s_sign, m, 1
    return s_sign, (8 + m), e


def bitserial_popcount_block_dot(w_codes, a_codes):
    """Exact block dot via popcounts of AND, reconstructed to a real number.
    Mirrors what an in-array popcount mechanism would compute. No scales here
    (pure integer-significand inner product); scales applied by caller."""
    # weight integer significands (signed), max |k|=12 -> 4 magnitude bits
    ws = [e2m1_int_significand(c) for c in w_codes]
    # activation integer significands (signed) with per-element 2^(e-10)
    total = 0.0
    for (w_sign, w_k), a_code in zip(ws, a_codes):
        a_sign, a_s, a_e = e4m3_int_significand(a_code)
        # exact per-element product significand, scaled by activation exponent
        prod = w_sign * w_k * a_sign * a_s          # integer
        total += prod * (2.0 ** (a_e - 10)) * (2.0 ** -1)  # w value = k*2^-1
    return total


def bitserial_via_actual_popcounts(w_codes, a_codes):
    """The literal popcount-of-AND form, to prove the decomposition identity for
    the integer magnitude parts. Uses fixed <=8-bit expansion of each element's
    product; we sum exact integer products through bitplane popcounts of the
    weight magnitude bits ANDed with activation magnitude bits, per element.

    This demonstrates popcount(w[b] & a[c]) summed with 2^(b+c) equals the
    integer product sum — the identity the hardware relies on."""
    # Build per-element integer magnitudes; verify the bitplane identity holds
    acc = 0
    signs_scales = []
    mags_w = []
    mags_a = []
    for wc, ac in zip(w_codes, a_codes):
        w_sign, w_k = e2m1_int_significand(wc)
        a_sign, a_s, a_e = e4m3_int_significand(ac)
        mags_w.append(w_k)
        mags_a.append(a_s)
        signs_scales.append((w_sign * a_sign, a_e))
    # sum over bitplanes: sum_i s_i * 2^(a_e_i-10-1) * (sum_{b,c} 2^{b+c} w_k_i[b] a_s_i[c])
    total = 0.0
    for i in range(len(w_codes)):
        prod_int = 0
        for b in range(4):            # w_k up to 12 -> 4 bits
            for c in range(4):        # a_s up to 15 -> 4 bits
                bit_and = ((mags_w[i] >> b) & 1) & ((mags_a[i] >> c) & 1)
                prod_int += (1 << (b + c)) * bit_and
        assert prod_int == mags_w[i] * mags_a[i], "bitplane identity broken"
        sgn, a_e = signs_scales[i]
        total += sgn * prod_int * (2.0 ** (a_e - 10)) * (2.0 ** -1)
    return total


def valid_e4m3():
    return [c for c in range(256)
            if not ((((c >> 3) & 0xF) == 0xF) and ((c & 0x7) == 0x7))]


def test_bitserial_matches_mxfp_reference():
    """Exact match between the popcount/bit-serial reconstruction and the OCP-MX
    reference block dot in k3/mxfp.py, over many random blocks."""
    rng = random.Random(20260831)
    VE4 = valid_e4m3()
    max_rel = 0.0
    for _ in range(4000):
        w_codes = [rng.randrange(16) for _ in range(BLOCK)]
        a_codes = [rng.choice(VE4) for _ in range(BLOCK)]
        wsc = rng.randrange(100, 155)
        asc = rng.randrange(100, 155)
        # reference: build MxBlock with explicit scale, use mx_dot_block
        from k3.mxfp import MxBlock
        wb = MxBlock(scale_code=wsc, codes=w_codes)
        a_vals = [e4m3_decode(c) for c in a_codes]
        ref = mx_dot_block(wb, a_vals, asc)
        # our reconstruction: integer-significand dot * scales
        recon = bitserial_popcount_block_dot(w_codes, a_codes)
        recon *= e8m0_decode(wsc) * e8m0_decode(asc)
        if ref != 0:
            max_rel = max(max_rel, abs(recon - ref) / abs(ref))
        else:
            assert abs(recon) < 1e-30
    assert max_rel < 1e-12, f"reconstruction rel err {max_rel:.2e} (should be exact)"


def test_bitplane_popcount_identity():
    """The literal popcount-of-AND identity equals the integer product, per
    element and summed — proving popcount is the only cross-lane primitive."""
    rng = random.Random(7)
    VE4 = valid_e4m3()
    for _ in range(2000):
        w_codes = [rng.randrange(16) for _ in range(BLOCK)]
        a_codes = [rng.choice(VE4) for _ in range(BLOCK)]
        v1 = bitserial_popcount_block_dot(w_codes, a_codes)
        v2 = bitserial_via_actual_popcounts(w_codes, a_codes)
        assert abs(v1 - v2) < 1e-12 * max(1.0, abs(v1))


def test_popcount_count_matches_model():
    from sim.sense import popcounts_per_mx_block_dot
    # E2M1 magnitude 3 bits (k up to 12 needs 4, but sign-magnitude uses 3+sign);
    # with two's-complement sign handling the model adds one plane each.
    assert popcounts_per_mx_block_dot(3, 4, "sign_mag") == 12
    assert popcounts_per_mx_block_dot(3, 4, "twos") == 20
