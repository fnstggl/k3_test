import itertools

import numpy as np
import pytest

from k3cim.analog import AnalogConfig, analog_mvm, error_stats


@pytest.fixture
def operands():
    rng = np.random.default_rng(3)
    return rng.integers(-12, 13, size=(32, 256)), rng.integers(-127, 128, size=(4, 256))


@pytest.mark.parametrize("cb,bpp,mode,C", list(itertools.product((1, 2, 3, 4), (1, 2, 4, 8),
                                                                   ("differential", "offset"), (8, 32, 128))))
def test_exact_with_enough_adc_bits(operands, cb, bpp, mode, C):
    W, X = operands
    cfg = AnalogConfig(cell_bits=cb, w_mag_bits=4, contributors=C, x_mag_bits=7, bits_per_pass=bpp, signed_mode=mode)
    cfg.adc_bits = cfg.exact_adc_bits()
    y, ye = analog_mvm(W, X, cfg)
    assert np.array_equal(y, ye)


def test_adc_truncation_increases_error(operands):
    W, X = operands
    errs = []
    for ab in (12, 9, 7, 5):
        y, ye = analog_mvm(W, X, AnalogConfig(cell_bits=4, contributors=32, x_mag_bits=7, bits_per_pass=1, adc_bits=ab))
        errs.append(error_stats(y, ye)["rel_rms_err"])
    assert errs == sorted(errs)


def test_noise_monotonic(operands):
    W, X = operands
    errs = [error_stats(*analog_mvm(W, X, AnalogConfig(cell_bits=4, contributors=32, x_mag_bits=7, adc_bits=16,
                                                       bits_per_pass=1, sigma_prog_abs=s)))["rel_rms_err"]
            for s in (0.0, 0.005, 0.02)]
    assert errs[0] == 0 and errs[0] < errs[1] < errs[2]


def test_calibration_removes_global_gain(operands):
    W, X = operands
    base = dict(cell_bits=4, contributors=32, x_mag_bits=7, adc_bits=16, bits_per_pass=1, temp_gain=0.08)
    e_none = error_stats(*analog_mvm(W, X, AnalogConfig(**base)))["rel_rms_err"]
    e_cal = error_stats(*analog_mvm(W, X, AnalogConfig(**base, calibration="gain_offset")))["rel_rms_err"]
    e_trim = error_stats(*analog_mvm(W, X, AnalogConfig(**base, calibration="adc_trim")))["rel_rms_err"]
    # digital post-correction cannot undo rounding of non-integer analog sums (x2^p in bit-serial shift-add);
    # trimming the ADC reference with the global gain restores exact integer alignment
    assert e_none > 0.05 and e_cal < e_none / 4 and e_trim < 1e-9


def test_spot_check_zeroes_checked_outputs(operands):
    W, X = operands
    cfg = AnalogConfig(cell_bits=4, contributors=32, x_mag_bits=7, adc_bits=16, sigma_prog_abs=0.02, spot_check_frac=0.5)
    y, ye = analog_mvm(W, X, cfg)
    assert np.mean(np.all(np.isclose(y, ye), axis=0)) >= 0.5


def test_mx_group_scales_applied():
    rng = np.random.default_rng(4)
    W = rng.integers(-12, 13, size=(8, 64))
    X = rng.integers(-100, 101, size=(2, 64))
    we = rng.integers(-3, 3, size=(8, 2))
    xe = rng.integers(-3, 3, size=(2, 2))
    cfg = AnalogConfig(cell_bits=4, contributors=32, x_mag_bits=7, bits_per_pass=8)
    cfg.adc_bits = cfg.exact_adc_bits()
    y, ye = analog_mvm(W, X, cfg, we, xe)
    ref = sum((X[:, g * 32:(g + 1) * 32] @ W[:, g * 32:(g + 1) * 32].T) * 2.0 ** (we[:, g][None] + xe[:, g][:, None])
              for g in range(2))
    assert np.allclose(ye, ref) and np.allclose(y, ref)


def test_adc_sweep_fast_path_matches_reference(operands):
    from dataclasses import replace

    from k3cim.analog import analog_mvm_adc_sweep
    W, X = operands
    for cb, bpp, C in ((4, 1, 32), (2, 4, 128), (1, 8, 8)):
        cfg = AnalogConfig(cell_bits=cb, w_mag_bits=4, contributors=C, x_mag_bits=7, bits_per_pass=bpp)
        fast, ye = analog_mvm_adc_sweep(W, X, cfg, [4, 7, 10, 14])
        for b, y in fast.items():
            y_ref, _ = analog_mvm(W, X, replace(cfg, adc_bits=b))
            assert np.allclose(y, y_ref)
