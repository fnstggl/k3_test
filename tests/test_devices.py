import numpy as np

from k3cim.devices import crosssim_cell_currents, sonos_sigma_frac_of_imax


def test_crosssim_sonos_matches_closed_form():
    lev = np.tile(np.arange(16), 8000).reshape(-1, 16)
    I, _ = crosssim_cell_currents(lev, 4, "SONOS", 0.0, seed=1)
    sig = (I - lev).std(0)[15] / 15.0                          # fraction of I_max at the top level
    assert abs(sig - sonos_sigma_frac_of_imax(1600.0)) / sonos_sigma_frac_of_imax(1600.0) < 0.05


def test_sonos_drift_lowers_high_states():
    lev = np.tile(np.arange(16), 4000).reshape(-1, 16)
    I0, _ = crosssim_cell_currents(lev, 4, "SONOS", 0.0, seed=2)
    I5, _ = crosssim_cell_currents(lev, 4, "SONOS", 5.0, seed=2)
    assert (I5 - lev).mean(0)[15] < (I0 - lev).mean(0)[15] - 0.2
