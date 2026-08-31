"""Number formats and per-plane compute (PIM) configuration.

Models the *rate* and *width* of near-plane arithmetic. Functional correctness of
MXFP dot products is modeled separately (k3/mxfp.py reference model + Gate 7 RTL);
here we only need: bits/param stored, ops/page, cycles/page, accumulator width.
"""

from dataclasses import dataclass
from enum import Enum


class WFormat(Enum):
    """Weight storage formats. value = (element_bits, scale_bits, block_size)."""
    FP16 = (16, 0, 1)
    FP8_E4M3 = (8, 0, 1)
    MXFP8 = (8, 8, 32)     # OCP MX: E4M3 elements + E8M0 scale per 32
    MXFP4 = (4, 8, 32)     # OCP MX: E2M1 elements + E8M0 scale per 32
    INT8 = (8, 0, 1)
    INT4 = (4, 0, 1)

    @property
    def bits_per_param(self) -> float:
        e, s, b = self.value
        return e + (s / b if b else 0.0)

    @property
    def bytes_per_param(self) -> float:
        return self.bits_per_param / 8.0


@dataclass
class PimConfig:
    """One compute cluster per plane (LLM-on-the-Palm: 1 MAC lane @ 400MHz)."""
    lanes_per_plane: int = 1          # parallel MAC/reduce lanes reading the page buffer
    freq_MHz: float = 400.0           # lane clock (paper Sec III-B)
    elems_per_lane_cycle: float = 1.0 # elements consumed per lane per cycle
    accumulator_bits: int = 32        # FP32 accumulator (paper Fig 4b)
    output_bytes_per_pass: int = 4    # per-plane partial result size (paper: 4B)
    # Latency to drain one plane's partial result to the channel (paper: 35ns)
    output_transfer_ns: float = 35.0

    @property
    def cycle_s(self) -> float:
        return 1.0 / (self.freq_MHz * 1e6)

    def compute_time_per_page_s(self, elems_per_page: float) -> float:
        """Time for the plane's lanes to consume one page of weights."""
        cycles = elems_per_page / (self.lanes_per_plane * self.elems_per_lane_cycle)
        return cycles * self.cycle_s


def elems_per_page(page_payload_bytes: float, fmt: WFormat) -> float:
    """Weights stored per page for a format (block scales stored inline)."""
    return page_payload_bytes * 8.0 / fmt.bits_per_param
