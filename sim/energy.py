"""Energy accounting: converts a TokenResult's activity tallies into joules.

Every coefficient lives in EnergyParams (architecture.py) with source notes;
this module is pure arithmetic. Components kept separate per project rules:
cell reads / channel I/O / PIM accumulation / DRAM / NPU / static.
"""

from dataclasses import dataclass

from .architecture import SystemConfig
from .scheduler import TokenResult
from .units import NJ, PJ


@dataclass
class EnergyBreakdown:
    cell_read_J: float
    channel_io_J: float
    pim_mac_J: float
    dram_J: float
    npu_J: float
    static_J: float

    @property
    def total_J(self) -> float:
        return (self.cell_read_J + self.channel_io_J + self.pim_mac_J
                + self.dram_J + self.npu_J + self.static_J)

    def as_dict(self) -> dict:
        return {
            "cell_read_J": self.cell_read_J,
            "channel_io_J": self.channel_io_J,
            "pim_mac_J": self.pim_mac_J,
            "dram_J": self.dram_J,
            "npu_J": self.npu_J,
            "static_J": self.static_J,
            "total_J": self.total_J,
        }


def page_read_energy_J(sys: SystemConfig) -> float:
    ep = sys.energy
    if ep.page_read_model == "per_page":
        return ep.page_read_nJ * NJ
    if ep.page_read_model == "icc":
        # per-die read power spread over the planes sensing concurrently
        p_die_W = sys.nand.vcc_V * sys.nand.icc_read_mA * 1e-3
        return p_die_W * sys.nand.effective_tR_s / sys.nand.planes_per_die
    raise ValueError(ep.page_read_model)


def token_energy(sys: SystemConfig, res: TokenResult) -> EnergyBreakdown:
    ep = sys.energy
    cell = res.pages_sensed * page_read_energy_J(sys)
    chan = res.channel_energy_bytes * ep.channel_pj_per_byte * PJ
    mac = res.macs * ep.mac_pj_per_op * PJ
    dram = res.dram_bytes * ep.dram_pj_per_byte * PJ
    npu = res.dyn_flops * ep.npu_pj_per_flop * PJ
    static = ep.static_W * res.latency_s
    return EnergyBreakdown(cell_read_J=cell, channel_io_J=chan, pim_mac_J=mac,
                           dram_J=dram, npu_J=npu, static_J=static)
