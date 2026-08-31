"""Gate 9 physics-aware sense-event model.

The Gate 1-8 simulator counted BYTES READ. Gate 9 models PHYSICAL SENSE EVENTS
and, for each, how much EXACT native-K3 arithmetic it accomplishes.

Central exact-arithmetic fact (derived, provable — see reports/07c and
tests/test_gate9_exact.py):

    An integer/fixed dot product decomposes into weighted popcounts of AND:
      sum_i w_i * a_i = sum_{b,c} 2^{b+c} * popcount_i( w_i[b] AND a_i[c] )
    For K3 MXFP4(w) x MXFP8(a): per 32-element block, the exact block dot is
      2^(ew+ea) * sum_{b<Bw}sum_{c<Ba} 2^{b+c} * popcount32( w[b] & a[c] )
    with Bw,Ba the significand bit widths. So the ONLY cross-lane primitive a
    NAND array must provide is an exact POPCOUNT across the reduction lanes.
    Everything else (the AND products) is per-bitline and free under sensing.

This module represents mechanisms by *what one sense event delivers*, so the
optimizer can compare "useful exact K3 MACs per physical sense" across
fundamentally different physics. Every parameter carries an evidence level
(L1/L2/L3) and modification class (F0/F1/F2/F3); values are loaded from
configs/nand_capabilities.yaml (primary-source-audited) — this file only holds
the composition math, no invented constants.
"""

from dataclasses import dataclass, field
from enum import Enum


class Evidence(Enum):
    L1 = "measured on exact target/family"
    L2 = "measured on other commercial 3D NAND"
    L3 = "proposed/simulated/patented/hypothesis"


class ModClass(Enum):
    F0 = "commodity firmware/controller only"
    F1 = "existing internal HW, needs command/test-mode exposure"
    F2 = "tiny peripheral/control modification"
    F3 = "substantial array/cell redesign"


@dataclass
class ReadMode:
    """A way of turning cell charge into latched bits, with its cost per event."""
    name: str
    tR_s: float                    # sense latency for ONE event
    energy_J_per_bit: float        # sense energy per sensed bit
    wordlines_per_event: int = 1   # MWS: WLs electrically combined in one sense
    blocks_per_event: int = 1      # inter-block MWS
    combine_fn: str = "read"       # 'read' | 'AND' | 'OR' | 'NAND' | 'NOR'
    # charge-recycling: within a consecutive same-block chain, non-first events
    # cost tR_recycled instead of tR_s (AiF cr-read)
    tR_recycled_s: float = None
    energy_recycled_J_per_bit: float = None
    max_chain: int = 1             # max consecutive recycled events (1 = no cr)
    evidence: Evidence = Evidence.L3
    mod_class: ModClass = ModClass.F3
    notes: str = ""

    def chain_time_s(self, n_events: int) -> float:
        """Time for n consecutive events using cr-read when available."""
        if self.tR_recycled_s is None or self.max_chain <= 1:
            return n_events * self.tR_s
        # first event full, up to (max_chain-1) recycled, then a new full precharge
        chain = max(1, self.max_chain)
        full = 1 + (n_events - 1) // chain          # number of full precharges
        recycled = n_events - full
        return full * self.tR_s + recycled * self.tR_recycled_s

    def chain_energy_J_per_bit(self, n_events: int) -> float:
        if self.energy_recycled_J_per_bit is None or self.max_chain <= 1:
            return self.energy_J_per_bit
        chain = max(1, self.max_chain)
        full = 1 + (n_events - 1) // chain
        recycled = n_events - full
        return (full * self.energy_J_per_bit
                + recycled * self.energy_recycled_J_per_bit) / n_events


@dataclass
class Reducer:
    """Local exact-reduction datapath consuming latched bits into partial sums.
    'popcount_width' = lanes an exact popcount covers per reducer op;
    'ops_per_s' = reducer throughput (popcount ops/second per reducer)."""
    name: str
    kind: str                      # 'digital_tree' | 'failbit_count' | 'bitserial_lane' | 'none'
    popcount_width: int            # lanes reduced per op
    ops_per_s: float               # per reducer
    area_um2_sky130: float         # from Gate 7 synthesis or model
    energy_J_per_op: float
    exact: bool = True             # exact integer result?
    evidence: Evidence = Evidence.L3
    mod_class: ModClass = ModClass.F2
    notes: str = ""


@dataclass
class SenseArchitecture:
    """A composed candidate: read mode + reducer + layout + batching policy."""
    name: str
    read: ReadMode
    reducer: Reducer
    # layout: how many exact MAC-equivalents one sense event's latched bits yield
    # BEFORE batch reuse (i.e. weights resolved per event that feed real K3 MACs)
    macs_per_sense_event_b1: float
    batch: int = 1
    batch_reuse_efficiency: float = 1.0  # fraction of B reuses that land (page residency)
    weight_contributions_per_sense: float = 1.0
    exact: bool = True
    unverified_primitives: list = field(default_factory=list)

    @property
    def worst_evidence(self) -> Evidence:
        order = {Evidence.L1: 1, Evidence.L2: 2, Evidence.L3: 3}
        return max([self.read.evidence, self.reducer.evidence], key=lambda e: order[e])

    @property
    def worst_mod_class(self) -> ModClass:
        order = {ModClass.F0: 0, ModClass.F1: 1, ModClass.F2: 2, ModClass.F3: 3}
        return max([self.read.mod_class, self.reducer.mod_class],
                   key=lambda m: order[m])


# ---- exact bit-serial decomposition helpers (the arithmetic ground truth) ----

def popcounts_per_mx_block_dot(bw_sig_bits: int = 3, ba_sig_bits: int = 4,
                               sign_handling: str = "twos") -> int:
    """Number of exact popcount-of-AND operations to compute one 32-element
    MXFP4(E2M1: 1 sign+2exp+1mant -> significand up to 3 bits incl implicit)
    x MXFP8(E4M3: significand 4 bits incl implicit) block dot product exactly.

    The block dot = sum over (b in weight-significand-bits, c in act-sig-bits)
    of 2^(b+c) * popcount(w[b] & a[c]); sign via two's-complement bitplanes adds
    one extra effective bitplane each. This is the EXACT integer inner product of
    the block's integer significands, then scaled by 2^(ew+ea)."""
    bw = bw_sig_bits + (1 if sign_handling == "twos" else 0)
    ba = ba_sig_bits + (1 if sign_handling == "twos" else 0)
    return bw * ba


def exact_dot_macs(reduction_dim: int) -> int:
    """MAC-equivalents in an exact dot product of given reduction dimension."""
    return reduction_dim
