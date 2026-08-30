"""System = NAND fabric + per-plane PIM + dynamic side (NPU + DRAM) + host link.

Bundles the configs and the scheduling/energy parameters an experiment sweeps.
"""

from dataclasses import dataclass, field

from .nand import NandConfig, palm_znand
from .arithmetic import PimConfig
from .mapping import MappingPolicy
from .units import GBps


@dataclass
class DynSideConfig:
    """NPU + DRAM roofline for dynamic ops (attention, norms, routing...)."""
    dram_bw_Bps: float = GBps(50.0)     # LPDDR5-class (paper Fig 1a ~50 GB/s)
    npu_flops: float = 17e12            # ANE-class TOPS; sensitivity (paper Fig 16d: 7-27)
    # fixed per-token dynamic overhead not tied to ctx (norms, router, sampling):
    fixed_overhead_s: float = 0.0


@dataclass
class EnergyParams:
    """All values must be sourced or swept; defaults = Gate 2 calibration targets
    (see reports/01_palm_reproduction.md for derivation)."""
    # NAND cell read energy per page sense. Two bookkeeping modes:
    #  'icc': E = vcc * icc_read * tR / planes_per_die (per-die current model)
    #  'per_page': E = page_read_nj directly
    page_read_model: str = "per_page"
    page_read_nJ: float = 183.0          # calibrated vs paper Fig 15 in Gate 2
    channel_pj_per_byte: float = 200.0   # ONFI I/O incl. controller side; Gate 2 calibrated
    mac_pj_per_op: float = 1.0           # near-plane MAC energy; sensitivity (28nm-class)
    dram_pj_per_byte: float = 60.0       # LPDDR5-class access energy; sensitivity var
    npu_pj_per_flop: float = 0.5         # sensitivity var
    static_W: float = 0.0                # controller/idle power; sensitivity


@dataclass
class SystemConfig:
    nand: NandConfig = field(default_factory=palm_znand)
    pim: PimConfig = field(default_factory=PimConfig)
    dyn: DynSideConfig = field(default_factory=DynSideConfig)
    mapping: MappingPolicy = field(default_factory=MappingPolicy)
    energy: EnergyParams = field(default_factory=EnergyParams)
    host_bw_Bps: float = GBps(4.2)
