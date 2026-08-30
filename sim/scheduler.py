"""Token-level scheduler: turns a TokenWorkload + SystemConfig into latency,
traffic, and activity tallies (energy.py converts tallies to joules).

Semantics:
  - nand_ops inside a Step: serial unless step.parallel_nand (then max over ops,
    valid only when mapping puts them on disjoint plane groups — asserted).
  - dyn_ops inside a Step: serial with each other (sum), roofline-timed.
  - Step with overlap=True: step time = max(nand_time, dyn_time)
    else: nand_time + dyn_time.
  - Token latency = sum of step times + dyn.fixed_overhead_s.
"""

from dataclasses import dataclass, field

from .architecture import SystemConfig
from .mapping import map_gemv, MappedOp
from .workload import TokenWorkload, Step, GemvOp, DynOp


@dataclass
class OpRecord:
    name: str
    kind: str                   # 'nand' | 'dyn'
    latency_s: float
    bottleneck: str = ""
    pages_sensed: float = 0.0
    macs: float = 0.0
    channel_cmd_bytes: float = 0.0
    channel_input_bytes: float = 0.0
    channel_input_energy_bytes: float = 0.0
    channel_output_bytes: float = 0.0
    dram_bytes: float = 0.0
    dyn_flops: float = 0.0
    planes_used: int = 0
    windows_per_plane: float = 0.0
    period_us: float = 0.0


@dataclass
class TokenResult:
    latency_s: float
    records: list = field(default_factory=list)
    nand_busy_s: float = 0.0
    dyn_busy_s: float = 0.0

    # --- aggregates ---
    def _sum(self, attr: str) -> float:
        return sum(getattr(r, attr) for r in self.records)

    @property
    def pages_sensed(self) -> float:
        return self._sum("pages_sensed")

    @property
    def macs(self) -> float:
        return self._sum("macs")

    @property
    def channel_bytes(self) -> float:
        return (self._sum("channel_cmd_bytes") + self._sum("channel_input_bytes")
                + self._sum("channel_output_bytes"))

    @property
    def channel_energy_bytes(self) -> float:
        """Receiver-weighted bytes for I/O energy accounting."""
        return (self._sum("channel_cmd_bytes") + self._sum("channel_input_energy_bytes")
                + self._sum("channel_output_bytes"))

    @property
    def bytes_entering_nand(self) -> float:
        return self._sum("channel_cmd_bytes") + self._sum("channel_input_bytes")

    @property
    def bytes_leaving_nand(self) -> float:
        return self._sum("channel_output_bytes")

    @property
    def dram_bytes(self) -> float:
        return self._sum("dram_bytes")

    @property
    def dyn_flops(self) -> float:
        return self._sum("dyn_flops")

    # internal_weight_bytes (bytes read out of cell arrays, i.e. internal NAND
    # traffic) is set by simulate_token as a plain attribute.
    internal_weight_bytes: float = 0.0

    def tok_per_s(self) -> float:
        return 1.0 / self.latency_s


def time_dyn_op(op: DynOp, sys: SystemConfig) -> float:
    t_mem = op.dram_bytes / sys.dyn.dram_bw_Bps if op.dram_bytes else 0.0
    t_cmp = op.flops / sys.dyn.npu_flops if op.flops else 0.0
    return max(t_mem, t_cmp)


def simulate_token(sys: SystemConfig, wl: TokenWorkload) -> TokenResult:
    records: list[OpRecord] = []
    total = sys.dyn.fixed_overhead_s
    nand_busy = 0.0
    dyn_busy = 0.0
    internal_weight_bytes = 0.0

    for step in wl.steps:
        nand_time = 0.0
        nand_times = []
        for op in step.nand_ops:
            m: MappedOp = map_gemv(op, sys.nand, sys.pim, sys.mapping)
            cb = m.channel_bytes
            rec = OpRecord(
                name=op.name, kind="nand", latency_s=m.latency_s,
                bottleneck=m.timing.bottleneck,
                pages_sensed=m.pages_sensed, macs=op.macs,
                channel_cmd_bytes=cb["cmd"], channel_input_bytes=cb["input"],
                channel_input_energy_bytes=cb["input_energy"],
                channel_output_bytes=cb["output"],
                planes_used=m.planes_used, windows_per_plane=m.windows_per_plane,
                period_us=m.timing.period_s * 1e6,
            )
            records.append(rec)
            nand_times.append(m.latency_s)
            internal_weight_bytes += m.pages_sensed * sys.nand.usable_page_bytes
        if nand_times:
            if step.parallel_nand:
                # disjoint plane groups required: total plane use must fit the array
                assert sum(map_gemv(o, sys.nand, sys.pim, sys.mapping).planes_used
                           for o in step.nand_ops) <= sys.nand.n_planes * 1.001, \
                    f"step {step.name}: parallel nand_ops exceed plane count"
                nand_time = max(nand_times)
            else:
                nand_time = sum(nand_times)

        dyn_time = 0.0
        for dop in step.dyn_ops:
            t = time_dyn_op(dop, sys)
            records.append(OpRecord(name=dop.name, kind="dyn", latency_s=t,
                                    dram_bytes=dop.dram_bytes, dyn_flops=dop.flops))
            dyn_time += t

        step_time = max(nand_time, dyn_time) if step.overlap else nand_time + dyn_time
        total += step_time
        nand_busy += nand_time
        dyn_busy += dyn_time

    res = TokenResult(latency_s=total, records=records,
                      nand_busy_s=nand_busy, dyn_busy_s=dyn_busy)
    res.internal_weight_bytes = internal_weight_bytes
    return res
