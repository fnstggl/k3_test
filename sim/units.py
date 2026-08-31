"""Explicit-unit helpers.

Convention used across the whole simulator:
  time    -> seconds internally; helpers ns/us/ms convert IN, *_ns/_us/_ms convert OUT
  size    -> bytes internally (float ok for aggregate math); bits helpers explicit
  rate    -> bytes/second internally; GBps helper converts
  energy  -> joules internally; pJ/nJ helpers convert
  power   -> watts internally

Every config field name carries its unit suffix when it is NOT in base units
(e.g. tR_us). Base-unit fields have no suffix (e.g. channel_bw is B/s? NO —
fields are suffixed: channel_bw_Bps). Keep everything suffixed for grep-ability.
"""

NS = 1e-9
US = 1e-6
MS = 1e-3
KB = 1024.0
MB = 1024.0 ** 2
GB = 1024.0 ** 3
TB = 1024.0 ** 4
# Decimal variants (bandwidth marketing, e.g. "3.2 GB/s" ONFI = decimal)
GB_DEC = 1e9
MB_DEC = 1e6
TB_DEC = 1e12
PJ = 1e-12
NJ = 1e-9
UJ = 1e-6


def ns(x: float) -> float:
    return x * NS


def us(x: float) -> float:
    return x * US


def ms(x: float) -> float:
    return x * MS


def to_ns(t_s: float) -> float:
    return t_s / NS


def to_us(t_s: float) -> float:
    return t_s / US


def to_ms(t_s: float) -> float:
    return t_s / MS


def GBps(x: float) -> float:
    """Decimal GB/s -> B/s (interface bandwidths are quoted decimal)."""
    return x * GB_DEC


def to_GBps(bps: float) -> float:
    return bps / GB_DEC


def bits_to_bytes(bits: float) -> float:
    return bits / 8.0


def bytes_to_bits(b: float) -> float:
    return b * 8.0
