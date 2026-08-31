"""NAND flash organization + timing + electrical model.

Pure configuration + derived geometry. No scheduling logic here (scheduler.py).
All values must be sourced by the experiment config that instantiates them;
defaults below are the LLM-on-the-Palm Z-NAND configuration (see
references/llm_on_the_palm_parameters.yaml) so Gate 2 uses this class as-is.
"""

from dataclasses import dataclass, field

from .units import us, GBps


@dataclass
class NandConfig:
    # --- geometry ---
    n_channels: int = 8
    dies_per_channel: int = 4
    planes_per_die: int = 8
    page_bytes: int = 2048              # user-data payload per page (spare excluded)
    die_capacity_bytes: float = 8 * 1024**3
    # --- timing ---
    tR_us: float = 3.0                  # array -> page buffer sense time
    cache_register: bool = True         # second register: next-page sense overlaps consumption
    # --- ONFI command-sequence model (grounded in MQSim ONFI_Channel_NVDDR2 defaults,
    # which mirror ONFI NV-DDR2 spec-class values; see reports/01_palm_reproduction.md) ---
    t_CS_ns: float = 20.0               # CE setup
    t_WC_ns: float = 25.0               # WE command/address cycle (legacy SDR)
    t_WB_ns: float = 100.0              # CLK high to R/B low
    t_RR_ns: float = 20.0               # ready to data output
    t_DBSY_ns: float = 500.0            # multi-plane dummy-busy between plane addresses
    cmd_addr_cycles: int = 6            # cmd+5addr (+confirm folded) per plane group
    # Command sequences issued on the channel per die per page window.
    # PIM broadcast command (paper Sec III-C, opcode 36h): 1 sequence selects the die's
    # whole plane group. Stock per-plane addressing needs planes_per_die sequences
    # with t_DBSY between them (MQSim ReadCommandTime[n] structure).
    cmd_seqs_per_die_window: int = 1
    cmd_serializes_with_sense: bool = True   # MQSim-style: command time extends the window
    # --- channel/interface ---
    channel_bw_Bps: float = GBps(3.2)
    # --- multi-level cell + ECC ---
    bits_per_cell: int = 1              # 1=SLC(Z-NAND), 3=TLC, 4=QLC
    ecc_parity_overhead: float = 0.0    # fraction of page payload consumed by parity (0.0 = none)
    read_retry_expected_extra_reads: float = 0.0  # expected extra sense ops per read (BER-driven)
    # --- electrical (per die), sourced from part/paper; used by energy.py ---
    vcc_V: float = 3.3
    icc_read_mA: float = 70.0           # ICC1 multi-plane read current (paper Table I)
    icc_idle_mA: float = 0.0            # standby (unsourced by paper -> 0; sensitivity)
    # energy per byte moved over the ONFI channel (pJ/B); sensitivity, sourced in energy.py
    channel_pj_per_byte: float = 20.0

    # ---- derived ----
    @property
    def tR_s(self) -> float:
        return us(self.tR_us)

    @property
    def n_dies(self) -> int:
        return self.n_channels * self.dies_per_channel

    @property
    def n_planes(self) -> int:
        return self.n_dies * self.planes_per_die

    @property
    def capacity_bytes(self) -> float:
        return self.n_dies * self.die_capacity_bytes

    @property
    def usable_page_bytes(self) -> float:
        """Payload bytes per page available for weights after ECC parity share."""
        return self.page_bytes * (1.0 - self.ecc_parity_overhead)

    @property
    def effective_tR_s(self) -> float:
        """Sense time including expected read-retry repeats."""
        return self.tR_s * (1.0 + self.read_retry_expected_extra_reads)

    @property
    def cmd_seq_time_s(self) -> float:
        """One ONFI read/PIM command sequence: t_CS + 6*t_WC + t_WB + t_RR
        (MQSim ReadCommandTime[1] structure; 290ns with defaults)."""
        return (self.t_CS_ns + self.cmd_addr_cycles * self.t_WC_ns
                + self.t_WB_ns + self.t_RR_ns) * 1e-9

    @property
    def cmd_time_per_die_window_s(self) -> float:
        """Channel bus time to launch one die's page window.
        n sequences chained with t_DBSY between them (MQSim ReadCommandTime[n])."""
        n = self.cmd_seqs_per_die_window
        if n <= 0:
            return 0.0
        return n * self.cmd_seq_time_s + (n - 1) * self.t_DBSY_ns * 1e-9

    @property
    def plane_read_bw_Bps(self) -> float:
        """Peak per-plane sense bandwidth (payload / sense time), pipelining assumed."""
        return self.usable_page_bytes / self.effective_tR_s

    @property
    def aggregate_internal_bw_Bps(self) -> float:
        """Upper bound: all planes sensing continuously."""
        return self.plane_read_bw_Bps * self.n_planes

    def validate(self) -> None:
        assert self.n_channels > 0 and self.dies_per_channel > 0 and self.planes_per_die > 0
        assert self.page_bytes > 0 and self.tR_us > 0
        assert 0.0 <= self.ecc_parity_overhead < 1.0
        assert self.bits_per_cell in (1, 2, 3, 4)


# Named profiles (sources in comments; use these rather than re-typing numbers)

def palm_znand() -> NandConfig:
    """LLM-on-the-Palm Table I configuration (Z-NAND SLC)."""
    return NandConfig()  # defaults ARE the paper config


def generic_tlc(tR_us: float = 50.0, page_kb: int = 16, planes: int = 4,
                dies_per_channel: int = 4, channels: int = 8,
                die_capacity_gb: float = 128.0,
                ecc_parity_overhead: float = 0.10) -> NandConfig:
    """Parameterized commodity-TLC-like profile. EVERY use must sweep tR/page/planes;
    these are placeholders of the right class, not facts about a specific part."""
    return NandConfig(
        n_channels=channels, dies_per_channel=dies_per_channel, planes_per_die=planes,
        page_bytes=page_kb * 1024, die_capacity_bytes=die_capacity_gb * 1024**3,
        tR_us=tR_us, bits_per_cell=3, ecc_parity_overhead=ecc_parity_overhead,
    )
