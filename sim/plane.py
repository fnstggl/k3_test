"""Per-plane page-window pipeline model.

A *window* is one steady-state pipeline slot in which every active plane of a die
consumes one page of weights. Phases considered:

  SENSE    array -> register, tR_eff. With a cache register, sense of page k+1
           overlaps consumption of page k (paper Fig 5). Without it, they serialize.
  COMPUTE  PIM lanes consume the page (elems/page / lane rate).
  CHANNEL  shared per-channel bus time attributable to one window:
             - command issue per die (multi-plane read group)
             - input broadcast (scope-dependent: once per channel / per die / per plane)
             - partial-result drain (per plane)

The steady-state window period is the max of the binding resources; the model also
reports which resource binds (the bottleneck) so experiments can report it.
"""

from dataclasses import dataclass

from .nand import NandConfig
from .arithmetic import PimConfig


@dataclass
class WindowTraffic:
    """Channel-byte breakdown for ONE window on ONE channel."""
    cmd_bytes: float
    input_bytes: float
    output_bytes: float

    @property
    def total_bytes(self) -> float:
        return self.cmd_bytes + self.input_bytes + self.output_bytes


@dataclass
class WindowTiming:
    period_s: float
    sense_s: float
    compute_s: float
    channel_s: float
    bottleneck: str          # 'sense' | 'compute' | 'channel'
    traffic: WindowTraffic   # per channel per window


def window_timing(nand: NandConfig, pim: PimConfig,
                  elems_per_page_val: float,
                  input_bytes_per_window_per_scope: float,
                  input_scope: str,
                  output_bytes_per_plane_window: float,
                  active_dies_per_channel: int | None = None,
                  active_planes_per_die: int | None = None,
                  channel_overlaps_sense: bool = True) -> WindowTiming:
    """Steady-state window period for one channel's worth of dies in lockstep.

    input_scope: 'channel' (one broadcast serves all dies on the channel),
                 'die' (each die needs its own stream),
                 'plane' (each plane distinct — worst case).
    channel_overlaps_sense: if False, channel service time ADDS to the sense time
    (pessimistic serialization; candidate model for the paper's MQSim behavior).
    """
    d = active_dies_per_channel if active_dies_per_channel is not None else nand.dies_per_channel
    p = active_planes_per_die if active_planes_per_die is not None else nand.planes_per_die

    sense = nand.effective_tR_s
    compute = pim.compute_time_per_page_s(elems_per_page_val)

    cmd = nand.cmd_time_per_die_window_s * d
    if input_scope == 'channel':
        in_b = input_bytes_per_window_per_scope
    elif input_scope == 'die':
        in_b = input_bytes_per_window_per_scope * d
    elif input_scope == 'plane':
        in_b = input_bytes_per_window_per_scope * d * p
    else:
        raise ValueError(f"bad input_scope {input_scope}")
    out_b = output_bytes_per_plane_window * d * p
    traffic = WindowTraffic(cmd_bytes=nand.cmd_bytes_per_plane_read * p * d,
                            input_bytes=in_b, output_bytes=out_b)
    channel = cmd + (in_b + out_b) / nand.channel_bw_Bps

    if nand.cache_register:
        candidates = {'sense': sense, 'compute': compute, 'channel': channel}
        if not channel_overlaps_sense:
            # sense and channel serialize: effective sense-lane time = sense + channel
            candidates = {'sense+channel': sense + channel, 'compute': compute}
        bottleneck = max(candidates, key=candidates.get)
        period = candidates[bottleneck]
    else:
        # no cache register: sense then compute serialize on the single register
        base = sense + compute
        if channel_overlaps_sense:
            candidates = {'sense+compute': base, 'channel': channel}
        else:
            candidates = {'sense+compute+channel': base + channel}
        bottleneck = max(candidates, key=candidates.get)
        period = candidates[bottleneck]

    return WindowTiming(period_s=period, sense_s=sense, compute_s=compute,
                        channel_s=channel, bottleneck=bottleneck, traffic=traffic)
