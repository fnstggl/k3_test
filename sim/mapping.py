"""Mapping of GEMV weights onto NAND planes.

The mapping decides, for each GemvOp:
  - which planes hold its weights (plane_fraction of the whole array, >=1 die group)
  - how many page windows each participating plane must process
  - the input-broadcast scope and per-window input bytes (with in-page row reuse)
  - per-window partial-output bytes

Layout model (transparent, matches LLM-on-the-Palm when rows_per_page=1):
  A page stores `rows_per_page` (R) row-segments of `cols_per_page` (=E/R) columns,
  where E = weights per page. All planes participating in an op step through the
  SAME column range in lockstep, so one input chunk of cols_per_page elements per
  window serves every plane in the broadcast scope. Each plane emits R partial
  sums per window (accumulator retained across the pages of one column sweep when
  retain_accumulator=True; the partial is exported once per row per column sweep
  it completes — with export_every_page=True the paper's per-page 4B export is used).
"""

from dataclasses import dataclass
import math

from .nand import NandConfig
from .arithmetic import PimConfig, WFormat, elems_per_page
from .workload import GemvOp
from .plane import window_timing, WindowTiming


@dataclass
class MappingPolicy:
    plane_fraction: float = 1.0        # fraction of all planes striped by each op
    input_scope: str = "die"           # 'channel' | 'die' | 'plane'
    rows_per_page: int = 1             # R: row segments sharing a page (input reuse)
    export_every_page: bool = True     # paper: 4B partial out per plane per window
    retain_accumulator: bool = True    # accumulate across a row's successive pages
    partial_bytes: float = 4.0         # exported partial width (FP32)
    channel_overlaps_sense: bool = True


@dataclass
class MappedOp:
    op: GemvOp
    planes_used: int
    windows_per_plane: float           # page windows each plane processes
    timing: WindowTiming
    active_dies_per_channel: int
    active_planes_per_die: int

    @property
    def latency_s(self) -> float:
        # steady-state + pipeline fill (first sense + first compute)
        fill = self.timing.sense_s + self.timing.compute_s
        return self.windows_per_plane * self.timing.period_s + fill

    @property
    def pages_sensed(self) -> float:
        return self.windows_per_plane * self.planes_used

    @property
    def channel_bytes(self) -> dict:
        """Total channel traffic for the whole op across all channels, bytes."""
        t = self.timing.traffic
        # traffic is per-window per-channel; windows_per_plane windows; channels used:
        channels_used = max(1, round(self.planes_used
                                     / (self.active_planes_per_die * self.active_dies_per_channel)))
        w = self.windows_per_plane * channels_used
        return {"cmd": t.cmd_bytes * w, "input": t.input_bytes * w,
                "output": t.output_bytes * w}


def map_gemv(op: GemvOp, nand: NandConfig, pim: PimConfig,
             policy: MappingPolicy) -> MappedOp:
    """Stripe one GemvOp across plane_fraction of the array."""
    planes_used = max(1, int(round(nand.n_planes * policy.plane_fraction)))
    # keep whole dies when possible (broadcast scope granularity)
    planes_per_die = nand.planes_per_die
    if planes_used >= planes_per_die:
        planes_used = (planes_used // planes_per_die) * planes_per_die
        active_planes = planes_per_die
        dies_used = planes_used // planes_per_die
        active_dies_per_channel = max(1, min(nand.dies_per_channel,
                                             math.ceil(dies_used / nand.n_channels)))
    else:
        active_planes = planes_used
        active_dies_per_channel = 1

    E = elems_per_page(nand.usable_page_bytes, op.w_fmt)
    pages_total = math.ceil(op.weight_params / E)
    windows_per_plane = pages_total / planes_used

    R = policy.rows_per_page
    cols_per_page = E / R
    input_bytes_scope = cols_per_page * op.act_bytes
    if policy.export_every_page:
        out_bytes = R * policy.partial_bytes
    else:
        # export once per completed row sweep: amortize by pages per row sweep
        pages_per_sweep = max(1.0, op.in_dim / cols_per_page)
        out_bytes = R * policy.partial_bytes / pages_per_sweep

    timing = window_timing(
        nand, pim, E, input_bytes_scope, policy.input_scope, out_bytes,
        active_dies_per_channel=active_dies_per_channel,
        active_planes_per_die=active_planes,
        channel_overlaps_sense=policy.channel_overlaps_sense,
    )
    return MappedOp(op=op, planes_used=planes_used, windows_per_plane=windows_per_plane,
                    timing=timing, active_dies_per_channel=active_dies_per_channel,
                    active_planes_per_die=active_planes)


def capacity_check(total_weight_bytes: float, nand: NandConfig,
                   slack: float = 0.9) -> bool:
    """Weights must fit in `slack` of raw capacity (FTL/replication margin)."""
    return total_weight_bytes <= nand.capacity_bytes * slack
