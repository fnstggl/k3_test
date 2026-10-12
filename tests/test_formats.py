import numpy as np
import pytest

from k3cim.formats import (E2M1_VALUES, aligned_int, bf16_round, dequant_mx, dequant_mxfp4, quantize_mxfp4,
                           quantize_mxfp8, round_e2m1, round_e4m3, unpack_mxfp4_codes)


def pack_reference(vals):
    """compressed-tensors CPU packing (nvfp4/helpers.py pack_fp4_to_uint8), re-implemented."""
    sign = np.signbit(vals).astype(np.uint8)
    x = np.abs(vals * 2).astype(np.int8)
    idx = np.zeros_like(x, dtype=np.uint8)
    for code, v in zip((1, 2, 3, 4, 5, 6), (1, 2, 3, 4, 6, 8)):
        idx[x == v] = code
    idx[x >= 12] = 7
    idx = idx | (sign << 3)
    idx = idx.reshape(-1, 2)
    return (idx[:, 0] | (idx[:, 1] << 4)).astype(np.uint8)


def test_mxfp4_unpack_matches_compressed_tensors_packing():
    rng = np.random.default_rng(0)
    v = rng.choice(np.concatenate([E2M1_VALUES, -E2M1_VALUES[1:]]), size=(4, 64))
    packed = pack_reference(v.ravel()).reshape(4, 32)
    v2 = unpack_mxfp4_codes(packed)
    assert np.array_equal(v2, (2 * v).astype(np.int8))


def test_mxfp4_dequant_scale_bias():
    packed = pack_reference(np.array([1.0, -6.0] * 16)).reshape(1, 16)
    w = dequant_mxfp4(packed, np.array([[127 + 3]], dtype=np.uint8))
    assert w[0, 0] == 8.0 and w[0, 1] == -48.0


@pytest.mark.parametrize("x,expected", [(0.25, 0.0), (0.26, 0.5), (0.75, 1.0), (1.25, 1.0), (1.75, 2.0),
                                        (2.5, 2.0), (3.5, 4.0), (5.0, 4.0), (5.01, 6.0), (100, 6.0)])
def test_e2m1_round_ties_even(x, expected):
    assert round_e2m1(np.array([x]))[0] == expected
    assert round_e2m1(np.array([-x]))[0] == -expected


@pytest.mark.parametrize("x,expected", [(448, 448), (460, 448), (1e6, 448), (1.0625, 1.0), (1.1875, 1.25),
                                        (2 ** -9, 2 ** -9), (1.4 * 2 ** -9, 2 ** -9), (2 ** -10, 0.0)])
def test_e4m3_round(x, expected):
    assert round_e4m3(np.array([x]))[0] == expected


def test_mxfp8_shared_exponent_rule():
    x = np.zeros(32)
    x[0] = 300.0
    q, se = quantize_mxfp8(x[None])
    assert se[0, 0] == int(np.floor(np.log2(300))) - 8
    assert np.all(np.abs(q) <= 448)


def test_mxfp8_relative_error_gaussian():
    rng = np.random.default_rng(1)
    x = rng.standard_normal((64, 1024))
    q, se = quantize_mxfp8(x)
    err = np.linalg.norm(dequant_mx(q, se) - x) / np.linalg.norm(x)
    assert 0.015 < err < 0.04


def test_mxfp4_quantize_values_on_grid():
    rng = np.random.default_rng(2)
    q, se = quantize_mxfp4(rng.standard_normal((8, 64)))
    assert set(np.unique(np.abs(q))).issubset(set(E2M1_VALUES))


def test_bf16_round():
    assert bf16_round(np.array([1.00390625], np.float32))[0] == 1.0          # tie -> even
    assert bf16_round(np.array([1.0078125], np.float32))[0] == 1.0078125


def test_aligned_int_lossless_when_representable():
    v = np.array([[3.0, -12.0, 0.5, 1.0] * 8])
    ints, e = aligned_int(v, 5, group=32)
    assert np.allclose((ints * 2.0 ** e[..., None]).reshape(v.shape), v)
