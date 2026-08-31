"""Exact Kimi K3 decode workload.

Parameter shapes from configs/k3.yaml (validated against the K3 tech report
Table 1/Sec 2, HF config.json, and vLLM's kimi_k3 implementation — see
reports/00_environment_and_sources.md). Derived totals are asserted against the
published 2.78T total / 104.2B active within 1%.

Workload structure per decoded token (93 backbone layers):
  layer 1            : KDA attention + dense FFN (h -> 33792 -> h, SiTU-GLU)
  layers 2..93       : (KDA or Gated MLA per 3:1 pattern) + Stable LatentMoE
  final              : LM head GEMV (163840 x 7168)
Dynamic side: KDA recurrent state update, MLA attention over compressed KV cache,
AttnRes block attention, router top-k, norms, sampling.

MTP layer and vision encoder are excluded from the baseline decode path
(speculative decoding off; text-only), recorded as such.
"""

from dataclasses import dataclass, field

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sim.arithmetic import WFormat
from sim.workload import GemvOp, DynOp, Step, TokenWorkload
from k3.mapping import K3MappingConfig, expected_max_group_load, group_geometry

# ---- architecture constants (configs/k3.yaml; sources cited there) ----
H = 7168                # hidden dim
L = 93                  # backbone layers
N_KDA = 69
N_MLA = 24
N_MOE = 92              # layers 2..93
HEADS = 96
HEAD_DIM = 128          # KDA dk = dv = 128; MLA v_head_dim = 128
PROJ = HEADS * HEAD_DIM  # 12288
Q_LORA = 1536
KV_LORA = 512
QK_ROPE = 64            # dims retained (NoPE: no rotation applied)
QK_NOPE = 128
N_EXPERTS = 896
TOPK = 16
N_SHARED = 2
LATENT = 3584
EXP_HID = 3072
DENSE_FFN = 33792
VOCAB = 163840
ALPHA_RANK = 128        # KDA low-rank decay: d->128->PROJ (vLLM kda.py fused sizes)

PUBLISHED_TOTAL = 2.78e12
PUBLISHED_ACTIVE = 104.2e9


@dataclass
class K3Precisions:
    """Storage/wire formats. K3-native: routed experts MXFP4 w/ MXFP8 acts;
    everything else 'higher precision' (checkpoint BF16; FP8 deploy variant)."""
    expert_w: WFormat = WFormat.MXFP4
    expert_act_bytes: float = 8.25 / 8.0      # MXFP8 on the wire
    dense_w: WFormat = WFormat.FP16           # BF16-class 2B (bits match FP16)
    dense_act_bytes: float = 2.0
    kda_state_bytes: float = 4.0              # FP32 recurrent state (sensitivity: 2.0)
    kv_entry_bytes: float = 2.0               # BF16 compressed KV cache entries


# ---------------------------------------------------------------------------
# parameter accounting
# ---------------------------------------------------------------------------

def kda_layer_params() -> dict:
    return {
        "qkvg": 4 * H * PROJ,                # Wq,Wk,Wv,Wg (full-rank gate)
        "o": PROJ * H,
        "alpha_lowrank": H * ALPHA_RANK + ALPHA_RANK * PROJ,
        "beta": H * HEADS,
        "shortconv": 3 * PROJ * 4,           # k=4 conv on q,k,v streams
    }


def mla_layer_params() -> dict:
    return {
        "q_a": H * Q_LORA,
        "q_b": Q_LORA * HEADS * (QK_NOPE + QK_ROPE),
        "kv_a": H * (KV_LORA + QK_ROPE),
        "kv_b": KV_LORA * HEADS * (QK_NOPE + HEAD_DIM),
        "gate": H * PROJ,
        "o": PROJ * H,
    }


def moe_layer_params() -> dict:
    return {
        "router": H * N_EXPERTS,
        "w_down_latent": H * LATENT,
        "experts": N_EXPERTS * 3 * LATENT * EXP_HID,   # SiTU-GLU: Wg, Wu, Wd
        "w_up_latent": LATENT * H,
        "shared": 3 * H * (N_SHARED * EXP_HID),        # fused 2x3072 = 6144 (vLLM)
    }


def dense_layer_ffn_params() -> float:
    return 3 * H * DENSE_FFN


def total_params() -> float:
    t = N_KDA * sum(kda_layer_params().values())
    t += N_MLA * sum(mla_layer_params().values())
    t += N_MOE * sum(moe_layer_params().values())
    t += dense_layer_ffn_params()
    t += 2 * VOCAB * H                                  # embedding + untied head
    return t


def active_params_per_token() -> float:
    a = N_KDA * sum(kda_layer_params().values())
    a += N_MLA * sum(mla_layer_params().values())
    m = moe_layer_params()
    a += N_MOE * (m["router"] + m["w_down_latent"] + m["w_up_latent"] + m["shared"]
                  + TOPK * 3 * LATENT * EXP_HID)
    a += dense_layer_ffn_params()
    a += VOCAB * H                                      # LM head (embed lookup ~0)
    return a


def assert_published_totals(tolerance: float = 0.01) -> dict:
    t, a = total_params(), active_params_per_token()
    terr = abs(t - PUBLISHED_TOTAL) / PUBLISHED_TOTAL
    aerr = abs(a - PUBLISHED_ACTIVE) / PUBLISHED_ACTIVE
    assert terr < tolerance, f"total {t:.3e} vs published 2.78e12 ({terr:.1%})"
    assert aerr < tolerance, f"active {a:.3e} vs published 104.2e9 ({aerr:.1%})"
    return {"total": t, "active": a, "total_err": terr, "active_err": aerr}


# ---------------------------------------------------------------------------
# workload builder
# ---------------------------------------------------------------------------

def layer_type(i: int) -> str:
    """i in 1..93. 3 KDA then 1 MLA repeating; layer 93 forced MLA (TR 2.1)."""
    if i == 93:
        return "mla"
    return "mla" if i % 4 == 0 else "kda"


@dataclass
class ResidencyPolicy:
    """Where each weight pool lives.
    'nand'  : GEMV on Flash-PIM (weight-resident)
    'dram'  : streamed from DRAM to NPU per token (roofline)
    """
    experts: str = "nand"
    dense_pool: str = "nand"     # KDA/MLA/shared/W↓W↑/dense FFN/router/head
    kv_cache: str = "dram"


def build_token_workload(ctx: int,
                         prec: K3Precisions = None,
                         res: ResidencyPolicy = None,
                         mapping: K3MappingConfig = None,
                         nand_geom: dict = None,
                         dram_bw_note: str = "") -> TokenWorkload:
    """One decoded token at context length ctx.

    mapping/nand_geom control expert placement: nand_geom must give
    {n_channels, dies_per_channel, planes_per_die} so expert groups can be
    laid out on channel boundaries."""
    prec = prec or K3Precisions()
    res = res or ResidencyPolicy()
    mapping = mapping or K3MappingConfig()
    grouped = mapping.expert_strategy == "grouped"
    if grouped:
        assert nand_geom, "grouped expert mapping needs nand_geom"
        geo = group_geometry(nand_geom["n_channels"], nand_geom["dies_per_channel"],
                             nand_geom["planes_per_die"], mapping.n_expert_groups)
        expert_fraction = geo["plane_fraction"]
        collision = expected_max_group_load(
            mapping.n_expert_groups, TOPK, N_EXPERTS,
            replication=mapping.expert_replication, alpha=mapping.hot_expert_alpha)
    else:
        expert_fraction, collision = 1.0, 1.0
    exp_hints = {"plane_fraction": expert_fraction,
                 "rows_per_page": mapping.rows_per_page_expert}
    if grouped:
        exp_hints["channels_override"] = geo["channels_per_group"]
        exp_hints["dies_per_channel_override"] = geo["dies_per_channel_in_group"]
    dense_hints = {"plane_fraction": 1.0,
                   "rows_per_page": mapping.rows_per_page_dense}
    steps: list[Step] = []

    def wop(name, out_dim, in_dim, kind="dense", count=1) -> GemvOp:
        if kind == "expert":
            return GemvOp(name, out_dim, in_dim, prec.expert_w,
                          prec.expert_act_bytes, count=count, hints=dict(exp_hints))
        return GemvOp(name, out_dim, in_dim, prec.dense_w,
                      prec.dense_act_bytes, count=count, hints=dict(dense_hints))

    def emit_gemv_steps(prefix, ops, dyn=None, overlap=False, parallel=False):
        if res.dense_pool == "nand":
            steps.append(Step(prefix, nand_ops=ops, dyn_ops=dyn or [],
                              overlap=overlap, parallel_nand=parallel))
        else:  # stream weights from DRAM: bytes = sum weight_bytes + act traffic
            dbytes = sum(o.weight_bytes for o in ops)
            flops = sum(2 * o.weight_params for o in ops)
            dyn_ops = [DynOp(prefix + ".stream", dram_bytes=dbytes, flops=flops)]
            steps.append(Step(prefix, dyn_ops=dyn_ops + (dyn or []), overlap=overlap))

    for i in range(1, L + 1):
        lt = layer_type(i)
        if lt == "kda":
            # S1: qkv + full-rank gate share input x (one broadcast group)
            emit_gemv_steps(f"L{i}.kda.qkvg",
                            [wop(f"L{i}.kda.qkvg", 4 * PROJ, H)])
            # S2: recurrent state read-modify-write + delta rule (dynamic)
            state_bytes = HEADS * HEAD_DIM * HEAD_DIM * prec.kda_state_bytes
            steps.append(Step(f"L{i}.kda.state",
                              dyn_ops=[DynOp(f"L{i}.kda.state",
                                             dram_bytes=2 * state_bytes,
                                             flops=6 * HEADS * HEAD_DIM * HEAD_DIM)]))
            # S3: output projection
            emit_gemv_steps(f"L{i}.kda.o", [wop(f"L{i}.kda.o", H, PROJ)])
        else:
            emit_gemv_steps(f"L{i}.mla.a",
                            [wop(f"L{i}.mla.q_a", Q_LORA, H),
                             wop(f"L{i}.mla.kv_a", KV_LORA + QK_ROPE, H),
                             wop(f"L{i}.mla.gate", PROJ, H)])
            emit_gemv_steps(f"L{i}.mla.q_b",
                            [wop(f"L{i}.mla.q_b", HEADS * (QK_NOPE + QK_ROPE), Q_LORA)])
            # absorbed W_UK/W_UV act as per-token GEMVs against kv_b weights
            emit_gemv_steps(f"L{i}.mla.kv_b_absorbed",
                            [wop(f"L{i}.mla.kv_b", HEADS * (QK_NOPE + HEAD_DIM), KV_LORA)])
            # attention over compressed KV cache (dynamic)
            kv_bytes = ctx * (KV_LORA + QK_ROPE) * prec.kv_entry_bytes
            att_flops = 2 * 2 * ctx * (KV_LORA + QK_ROPE) * HEADS / 64  # MQA-style shared c
            steps.append(Step(f"L{i}.mla.attn",
                              dyn_ops=[DynOp(f"L{i}.mla.attn", dram_bytes=kv_bytes,
                                             flops=att_flops)]))
            emit_gemv_steps(f"L{i}.mla.o", [wop(f"L{i}.mla.o", H, PROJ)])

        # AttnRes: block attention over <=9 d-wide sums (dynamic, tiny)
        steps.append(Step(f"L{i}.attnres",
                          dyn_ops=[DynOp(f"L{i}.attnres", dram_bytes=9 * H * 2.0,
                                         flops=2 * 9 * H)]))

        # FFN part
        if i == 1:
            emit_gemv_steps("L1.dense.gu", [wop("L1.dense.gu", 2 * DENSE_FFN, H)])
            emit_gemv_steps("L1.dense.d", [wop("L1.dense.d", H, DENSE_FFN)])
            continue
        # Stable LatentMoE
        emit_gemv_steps(f"L{i}.moe.pre",
                        [wop(f"L{i}.moe.router", N_EXPERTS, H),
                         wop(f"L{i}.moe.wdown", LATENT, H),
                         wop(f"L{i}.moe.shared_gu", 2 * N_SHARED * EXP_HID, H)])
        # routed experts: 16 selected, gate+up then down, latent-space, MXFP4
        if res.experts == "nand":
            if grouped:
                gu = [wop(f"L{i}.moe.exp{j}.gu", 2 * EXP_HID, LATENT, kind="expert")
                      for j in range(TOPK)]
                dn = [wop(f"L{i}.moe.exp{j}.d", LATENT, EXP_HID, kind="expert")
                      for j in range(TOPK)]
                steps.append(Step(f"L{i}.moe.experts_gu", nand_ops=gu,
                                  parallel_nand=True, collision_factor=collision))
                steps.append(Step(f"L{i}.moe.experts_d", nand_ops=dn,
                                  parallel_nand=True, collision_factor=collision))
                steps.append(Step(f"L{i}.moe.shared_d",
                                  nand_ops=[wop(f"L{i}.moe.shared_d", H,
                                                N_SHARED * EXP_HID)]))
            else:  # wide: all planes per expert, serial
                gu = [wop(f"L{i}.moe.exp.gu", 2 * EXP_HID, LATENT, kind="expert",
                          count=TOPK)]
                dn = [wop(f"L{i}.moe.exp.d", LATENT, EXP_HID, kind="expert",
                          count=TOPK)]
                steps.append(Step(f"L{i}.moe.experts_gu", nand_ops=gu))
                steps.append(Step(f"L{i}.moe.experts_d", nand_ops=dn))
                steps.append(Step(f"L{i}.moe.shared_d",
                                  nand_ops=[wop(f"L{i}.moe.shared_d", H,
                                                N_SHARED * EXP_HID)]))
        else:
            eb = TOPK * 3 * LATENT * EXP_HID * prec.expert_w.bytes_per_param
            steps.append(Step(f"L{i}.moe.experts",
                              dyn_ops=[DynOp(f"L{i}.moe.experts", dram_bytes=eb,
                                             flops=2 * TOPK * 3 * LATENT * EXP_HID)]))
            steps.append(Step(f"L{i}.moe.shared_d",
                              dyn_ops=[DynOp(f"L{i}.moe.shared_d",
                                             dram_bytes=H * N_SHARED * EXP_HID * 2.0,
                                             flops=2 * H * N_SHARED * EXP_HID)]))
        emit_gemv_steps(f"L{i}.moe.wup", [wop(f"L{i}.moe.wup", H, LATENT)])

    # LM head
    emit_gemv_steps("lm_head", [wop("lm_head", VOCAB, H)])
    return TokenWorkload(name="kimi-k3-decode", steps=steps)


def nand_bytes_per_token(prec: K3Precisions = None,
                         res: ResidencyPolicy = None) -> dict:
    """Weight bytes that must be sensed from NAND per token, by pool."""
    prec = prec or K3Precisions()
    res = res or ResidencyPolicy()
    expert_active = N_MOE * TOPK * 3 * LATENT * EXP_HID
    dense_active = active_params_per_token() - expert_active
    out = {"expert_bytes": expert_active * prec.expert_w.bytes_per_param
           if res.experts == "nand" else 0.0,
           "dense_bytes": dense_active * prec.dense_w.bytes_per_param
           if res.dense_pool == "nand" else 0.0}
    out["total"] = out["expert_bytes"] + out["dense_bytes"]
    return out


def storage_bytes(prec: K3Precisions = None) -> dict:
    """Total weight storage by pool (for capacity checks)."""
    prec = prec or K3Precisions()
    expert_total = N_MOE * N_EXPERTS * 3 * LATENT * EXP_HID
    dense_total = total_params() - expert_total - VOCAB * H  # embed stays DRAM-side
    return {"expert_bytes": expert_total * prec.expert_w.bytes_per_param,
            "dense_bytes": dense_total * prec.dense_w.bytes_per_param,
            "embed_bytes": VOCAB * H * prec.dense_w.bytes_per_param}
