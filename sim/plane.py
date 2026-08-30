"""Per-plane page-window pipeline model.

A *window* is one steady-state pipeline slot in which every active plane of a die
consumes one page of weights. Phases considered:

  SENSE    array -> register, tR_eff. With a cache register, sense of page k+1
           overlaps consumption of page k (paper Fig 5). Without it, they serialize.
  COMPUTE  PIM lanes consume the page (elems/page / lane rate).
  CMD      ONFI command sequences launching each die's window. Serialized on the
           shared channel; with cmd_serializes_with_sense=True (MQSim-style
           conservative scheduling, validated in Gate 2) they EXTEND the window.
  DATA     input broadcast (scope-dependent) + partial-result drain on the channel.
           Streams overlap sensing by default (channel_overlaps_sense).

The model reports which resource binds (bottleneck) for every op.
"""

from dataclasses import dataclass

from .nand import NandConfig
from .arithmetic import PimConfig

CMD_SEQ_BYTES = 7.0   # opcode + 5 addr + confirm actually driven on the bus


@dataclass
class WindowTraffic:
    """Channel-byte breakdown for ONE window on ONE channel.
    input_bytes are BUS bytes (timing); input_energy_bytes weights broadcast
    receivers (a CE#-multi-die broadcast toggles every selected die's I/O
    receivers, so receive energy scales with dies regardless of scope)."""
    cmd_bytes: float
    input_bytes: float
    output_bytes: float
    input_energy_bytes: float = 0.0

    @property
    def total_bytes(self) -> float:
        return self.cmd_bytes + self.input_bytes + self.output_bytes


@dataclass
class WindowTiming:
    period_s: float
    sense_s: float
    compute_s: float
    cmd_s: float             # per-channel command time per window (all dies)
    data_s: float            # per-channel data (input+output) time per window
    bottleneck: str          # 'sense' | 'compute' | 'channel-data' | '+cmd' suffix
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
    in_energy_b = input_bytes_per_window_per_scope * d if input_scope in ('channel', 'die') \
        else in_b
    traffic = WindowTraffic(cmd_bytes=CMD_SEQ_BYTES * nand.cmd_seqs_per_die_window * d,
                            input_bytes=in_b, output_bytes=out_b,
                            input_energy_bytes=in_energy_b)
    data = (in_b + out_b) / nand.channel_bw_Bps

    # sense lane: does the single register force sense+compute to serialize?
    sense_lane = sense if nand.cache_register else sense + compute

    if channel_overlaps_sense:
        candidates = {'sense': sense_lane, 'compute': compute, 'channel-data': data}
    else:
        candidates = {'sense+data': sense_lane + data, 'compute': compute}
    bottleneck = max(candidates, key=candidates.get)
    period = candidates[bottleneck]

    if nand.cmd_serializes_with_sense:
        if cmd > 0:
            period += cmd
            bottleneck += '+cmd'
    else:
        if cmd + data > period:  # command time competes on the channel
            period = cmd + data
            bottleneck = 'channel-cmd+data'

    return WindowTiming(period_s=period, sense_s=sense, compute_s=compute,
                        cmd_s=cmd, data_s=data, bottleneck=bottleneck, traffic=traffic)
