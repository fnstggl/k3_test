"""Workload description: weight-resident GEMV ops + dynamic ops, grouped into
dependency steps for one decoded token.

A Step's nand_ops run back-to-back on the NAND fabric (serial within the step,
because successive FC layers depend on each other's outputs — parallel_nand=True
declares they use disjoint plane groups and independent inputs, e.g. concurrently
computed experts). dyn_ops model NPU/DRAM-side work; overlap=True lets them hide
under the step's NAND time (no data dependency), otherwise they add serially.
"""

from dataclasses import dataclass, field

from .arithmetic import WFormat


@dataclass
class GemvOp:
    """y[out_dim] += W[out_dim, in_dim] @ x[in_dim], W resident in NAND."""
    name: str
    out_dim: int
    in_dim: int
    w_fmt: WFormat = WFormat.FP16
    act_bytes: float = 2.0          # bytes per input activation element on the wire
    count: int = 1                  # identical instances (e.g. selected experts)

    @property
    def weight_params(self) -> float:
        return float(self.out_dim) * self.in_dim * self.count

    @property
    def weight_bytes(self) -> float:
        return self.weight_params * self.w_fmt.bytes_per_param

    @property
    def macs(self) -> float:
        return self.weight_params  # one MAC per stored weight per token


@dataclass
class DynOp:
    """Dynamic-side op (attention, KDA state update, norms, router, reductions)."""
    name: str
    dram_bytes: float = 0.0         # bytes moved to/from DRAM
    flops: float = 0.0              # compute on NPU/dyn engine
    location: str = "npu"


@dataclass
class Step:
    name: str
    nand_ops: list = field(default_factory=list)     # list[GemvOp]
    dyn_ops: list = field(default_factory=list)      # list[DynOp]
    overlap: bool = False           # dyn ops overlap the NAND time of THIS step
    parallel_nand: bool = False     # nand_ops on disjoint plane groups, run concurrently


@dataclass
class TokenWorkload:
    name: str
    steps: list = field(default_factory=list)

    def total_weight_bytes(self) -> float:
        return sum(op.weight_bytes for s in self.steps for op in s.nand_ops)

    def total_macs(self) -> float:
        return sum(op.macs for s in self.steps for op in s.nand_ops)


# ---------------------------------------------------------------------------
# GPT-3-class builder (Gate 2 calibration workload)
# ---------------------------------------------------------------------------

def gpt3_token_workload(hidden: int, n_layers: int, ffn_mult: int = 4,
                        ctx: int = 128, vocab: int = 50257,
                        w_fmt: WFormat = WFormat.FP16,
                        act_bytes: float = 2.0,
                        dram_bw_note: str = "attention K/V streamed from DRAM",
                        include_lm_head: bool = True,
                        lm_head_on_nand: bool = True,
                        attn_overlap: bool = False) -> TokenWorkload:
    """Decode-one-token workload for a GPT-3-class dense transformer, with the
    LLM-on-the-Palm mapping: all FC layers on Flash-PIM; QxK/softmax/SxV on NPU
    reading the KV cache from DRAM (paper Sec IV-B).

    ctx: current context length (KV entries attended this token).
    """
    steps = []
    d_ff = ffn_mult * hidden
    kv_bytes_per_layer = 2.0 * ctx * hidden * 2.0   # K and V, FP16
    for l in range(n_layers):
        steps.append(Step(
            name=f"L{l}.qkv",
            nand_ops=[GemvOp(f"L{l}.qkv", 3 * hidden, hidden, w_fmt, act_bytes)],
        ))
        # attention on NPU: streams K then V from DRAM; strictly between qkv and proj
        steps.append(Step(
            name=f"L{l}.attn",
            dyn_ops=[DynOp(f"L{l}.attn", dram_bytes=kv_bytes_per_layer,
                           flops=2 * 2 * ctx * hidden)],
            overlap=attn_overlap,
        ))
        steps.append(Step(
            name=f"L{l}.proj",
            nand_ops=[GemvOp(f"L{l}.proj", hidden, hidden, w_fmt, act_bytes)],
        ))
        steps.append(Step(
            name=f"L{l}.ffn1",
            nand_ops=[GemvOp(f"L{l}.ffn1", d_ff, hidden, w_fmt, act_bytes)],
        ))
        steps.append(Step(
            name=f"L{l}.ffn2",
            nand_ops=[GemvOp(f"L{l}.ffn2", hidden, d_ff, w_fmt, act_bytes)],
        ))
    if include_lm_head:
        if lm_head_on_nand:
            steps.append(Step(name="lm_head",
                              nand_ops=[GemvOp("lm_head", vocab, hidden, w_fmt, act_bytes)]))
        else:
            steps.append(Step(name="lm_head",
                              dyn_ops=[DynOp("lm_head", dram_bytes=vocab * hidden * 2.0,
                                             flops=2.0 * vocab * hidden)]))
    return TokenWorkload(name="gpt3", steps=steps)
