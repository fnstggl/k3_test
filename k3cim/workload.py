"""Layer-by-layer Kimi-K3 inference workload derived from the released config.

The graph is built from data/k3/config.json and cross-checked against the
safetensors manifest (data/k3/tensor_manifest_grouped.csv).  Every op of a
single decode step is enumerated with its dependencies, so the scheduler can
compute a true critical path (no "aggregate weight-ops" shortcut).

Conventions
-----------
* Linear op: y[N] = W[N, K] x[K];  MACs = K*N*count.
* `count` = number of copies active per token (16 routed experts, 96 heads ...).
* `stored` = number of copies stored (896 experts ...).
* wdtype in {"bf16", "mxfp4", "fp32", None}; bytes per weight from the
  checkpoint (MXFP4 = 4 bits + 8-bit scale per 32 = 4.25 bits).
* MLA decode uses the standard weight-absorbed form (latent KV cache of
  kv_lora_rank + qk_rope_head_dim = 576 values per token per layer), which is
  how production engines (vLLM/SGLang FlashMLA) run DeepSeek/Kimi MLA.
  `fold_mla=True` additionally pre-multiplies W_UK into q_b and W_UV into
  o_proj (exact in real arithmetic, more weights, two fewer sequential stages).
"""
from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG_PATH = os.path.join(ROOT, "data", "k3", "config.json")
MANIFEST_PATH = os.path.join(ROOT, "data", "k3", "tensor_manifest_grouped.csv")

BYTES_PER_WEIGHT = {"bf16": 2.0, "fp32": 4.0, "mxfp4": 4.25 / 8, None: 0.0}


def load_config(path=CFG_PATH):
    return json.load(open(path))["text_config"]


@dataclass
class Op:
    name: str
    layer: int
    kind: str              # linear | attn_score | attn_value | softmax | kda_recurrent | conv | norm |
                           # attnres | router_topk | act | combine | add | embed | sample | headnorm
    K: int = 0
    N: int = 0
    count: int = 1
    stored: int = 1
    wdtype: str | None = None
    deps: list = field(default_factory=list)
    always_active: bool = True
    ctx_scaled: bool = False   # cost proportional to context length L
    elems: int = 0             # elementwise / reduction size (non-linear ops)
    note: str = ""

    @property
    def macs(self):
        return self.K * self.N * self.count if self.kind == "linear" else 0

    @property
    def active_weights(self):
        return self.K * self.N * self.count if self.kind == "linear" and self.wdtype else 0

    @property
    def stored_weights(self):
        return self.K * self.N * self.stored if self.kind == "linear" and self.wdtype else 0


class K3Workload:
    def __init__(self, cfg=None, fold_mla=False, kv_bytes=2.0, kda_state_bytes=4.0):
        self.cfg = cfg or load_config()
        self.fold_mla = fold_mla
        self.kv_bytes = kv_bytes
        self.kda_state_bytes = kda_state_bytes
        c = self.cfg
        self.H = c["hidden_size"]
        self.nL = c["num_hidden_layers"]
        self.kda_layers = {i - 1 for i in c["linear_attn_config"]["kda_layers"]}      # 0-indexed
        self.mla_layers = {i - 1 for i in c["linear_attn_config"]["full_attn_layers"]}
        assert self.kda_layers.isdisjoint(self.mla_layers)
        assert len(self.kda_layers) + len(self.mla_layers) == self.nL
        self.dense_layers = set(range(c["first_k_dense_replace"]))
        self.moe_layers = set(range(self.nL)) - self.dense_layers
        self.ops = self._build()

    # ------------------------------------------------------------------ graph
    def _attn_kda(self, L, x):
        c, H = self.cfg, self.H
        la = c["linear_attn_config"]
        nh, hd = la["num_heads"], la["head_dim"]
        P = nh * hd
        p = f"L{L}.kda."
        ops = [
            Op(p + "q_proj", L, "linear", H, P, wdtype="bf16", deps=[x]),
            Op(p + "k_proj", L, "linear", H, P, wdtype="bf16", deps=[x]),
            Op(p + "v_proj", L, "linear", H, P, wdtype="bf16", deps=[x]),
            Op(p + "g_proj", L, "linear", H, P, wdtype="bf16", deps=[x], note="full-rank output gate"),
            Op(p + "f_a_proj", L, "linear", H, hd, wdtype="bf16", deps=[x]),
            Op(p + "b_proj", L, "linear", H, nh, wdtype="bf16", deps=[x]),
            Op(p + "f_b_proj", L, "linear", hd, P, wdtype="bf16", deps=[p + "f_a_proj"]),
            Op(p + "conv_qkv", L, "conv", elems=3 * P * la["short_conv_kernel_size"],
               deps=[p + "q_proj", p + "k_proj", p + "v_proj"], note="depthwise causal conv k=4 + SiLU"),
            Op(p + "qk_l2norm", L, "headnorm", elems=2 * P, deps=[p + "conv_qkv"], note="per-head L2 norm (local)"),
            Op(p + "gate_beta", L, "act", elems=P + nh, deps=[p + "f_b_proj", p + "b_proj"]),
            Op(p + "recurrent", L, "kda_recurrent", elems=nh * hd * hd,
               deps=[p + "qk_l2norm", p + "gate_beta"],
               note="S=diag(e^g)S; S+=beta k(v-S^T k)^T; o=S^T q  (~4*H*d^2 MAC, state r/w)"),
            Op(p + "o_norm_gate", L, "headnorm", elems=P, deps=[p + "recurrent", p + "g_proj"]),
            Op(p + "o_proj", L, "linear", P, H, wdtype="bf16", deps=[p + "o_norm_gate"]),
        ]
        return ops, p + "o_proj"

    def _attn_mla(self, L, x):
        c, H = self.cfg, self.H
        nh = c["num_attention_heads"]
        dn, dr, dv = c["qk_nope_head_dim"], c["qk_rope_head_dim"], c["v_head_dim"]
        qr, kr = c["q_lora_rank"], c["kv_lora_rank"]
        p = f"L{L}.mla."
        ops = [
            Op(p + "q_a_proj", L, "linear", H, qr, wdtype="bf16", deps=[x]),
            Op(p + "kv_a_proj", L, "linear", H, kr + dr, wdtype="bf16", deps=[x]),
            Op(p + "g_proj", L, "linear", H, nh * dv, wdtype="bf16", deps=[x], note="output gate"),
            Op(p + "q_a_norm", L, "norm", elems=qr, deps=[p + "q_a_proj"]),
            Op(p + "kv_a_norm", L, "norm", elems=kr, deps=[p + "kv_a_proj"], note="latent appended to KV cache"),
        ]
        if not self.fold_mla:
            ops += [
                Op(p + "q_b_proj", L, "linear", qr, nh * (dn + dr), wdtype="bf16", deps=[p + "q_a_norm"]),
                Op(p + "uk_absorb", L, "linear", dn, kr, count=nh, stored=nh, wdtype="bf16",
                   deps=[p + "q_b_proj"], note="per-head q_nope @ W_UK (kv_b K-part)"),
            ]
            qdep = p + "uk_absorb"
        else:
            ops += [Op(p + "q_b_folded", L, "linear", qr, nh * (kr + dr), wdtype="bf16", deps=[p + "q_a_norm"],
                       note="W_UK^T W_qb_nope pre-multiplied")]
            qdep = p + "q_b_folded"
        ops += [
            Op(p + "score", L, "attn_score", K=kr + dr, N=nh, ctx_scaled=True,
               deps=[qdep, p + "kv_a_norm"], note="96 heads x L x 576 MAC over latent cache"),
            Op(p + "softmax", L, "softmax", elems=nh, ctx_scaled=True, deps=[p + "score"]),
            Op(p + "value", L, "attn_value", K=kr, N=nh, ctx_scaled=True, deps=[p + "softmax"],
               note="96 heads x L x 512 MAC"),
        ]
        if not self.fold_mla:
            ops += [
                Op(p + "uv_absorb", L, "linear", kr, dv, count=nh, stored=nh, wdtype="bf16",
                   deps=[p + "value"], note="per-head o_lat @ W_UV (kv_b V-part)"),
                Op(p + "gate_mul", L, "act", elems=nh * dv, deps=[p + "uv_absorb", p + "g_proj"]),
                Op(p + "o_proj", L, "linear", nh * dv, H, wdtype="bf16", deps=[p + "gate_mul"]),
            ]
        else:
            # gate is per (head, v-dim): cannot be applied after folding W_UV into o_proj
            # unless W_UV is applied first -> folding o_proj only legal without gate.
            # K3 uses an output gate, so only the UV absorb can be kept separate:
            ops += [
                Op(p + "uv_absorb", L, "linear", kr, dv, count=nh, stored=nh, wdtype="bf16",
                   deps=[p + "value"], note="kept: output gate sits between W_UV and o_proj"),
                Op(p + "gate_mul", L, "act", elems=nh * dv, deps=[p + "uv_absorb", p + "g_proj"]),
                Op(p + "o_proj", L, "linear", nh * dv, H, wdtype="bf16", deps=[p + "gate_mul"]),
            ]
        return ops, p + "o_proj"

    def _mlp_dense(self, L, x):
        c, H = self.cfg, self.H
        I = c["intermediate_size"]
        p = f"L{L}.mlp."
        ops = [
            Op(p + "gate_proj", L, "linear", H, I, wdtype="bf16", deps=[x]),
            Op(p + "up_proj", L, "linear", H, I, wdtype="bf16", deps=[x]),
            Op(p + "situ", L, "act", elems=I, deps=[p + "gate_proj", p + "up_proj"]),
            Op(p + "down_proj", L, "linear", I, H, wdtype="bf16", deps=[p + "situ"]),
        ]
        return ops, p + "down_proj"

    def _mlp_moe(self, L, x):
        c, H = self.cfg, self.H
        E, k, ns = c["num_experts"], c["num_experts_per_token"], c["num_shared_experts"]
        I, Hl = c["moe_intermediate_size"], c["routed_expert_hidden_size"]
        p = f"L{L}.moe."
        ops = [
            Op(p + "router", L, "linear", H, E, wdtype="bf16", deps=[x], note="fp32 math on bf16 weights"),
            Op(p + "topk", L, "router_topk", elems=E, deps=[p + "router"], note="sigmoid+bias, top-16 of 896"),
            Op(p + "latent_down", L, "linear", H, Hl, wdtype="bf16", deps=[x]),
            Op(p + "shared_gate", L, "linear", H, I * ns, wdtype="bf16", deps=[x]),
            Op(p + "shared_up", L, "linear", H, I * ns, wdtype="bf16", deps=[x]),
            Op(p + "shared_act", L, "act", elems=I * ns, deps=[p + "shared_gate", p + "shared_up"]),
            Op(p + "shared_down", L, "linear", I * ns, H, wdtype="bf16", deps=[p + "shared_act"]),
            Op(p + "expert_w1", L, "linear", Hl, I, count=k, stored=E, wdtype="mxfp4", always_active=False,
               deps=[p + "topk", p + "latent_down"]),
            Op(p + "expert_w3", L, "linear", Hl, I, count=k, stored=E, wdtype="mxfp4", always_active=False,
               deps=[p + "topk", p + "latent_down"]),
            Op(p + "expert_act", L, "act", elems=I * k, deps=[p + "expert_w1", p + "expert_w3"]),
            Op(p + "expert_w2", L, "linear", I, Hl, count=k, stored=E, wdtype="mxfp4", always_active=False,
               deps=[p + "expert_act"]),
            Op(p + "combine", L, "combine", elems=Hl * k, deps=[p + "expert_w2"],
               note="weighted sum of 16 expert outputs (cross-tile gather)"),
            Op(p + "latent_norm", L, "norm", elems=Hl, deps=[p + "combine"]),
            Op(p + "latent_up", L, "linear", Hl, H, wdtype="bf16", deps=[p + "latent_norm"]),
            Op(p + "sum", L, "add", elems=H, deps=[p + "latent_up", p + "shared_down"]),
        ]
        return ops, p + "sum"

    def _build(self):
        c, H = self.cfg, self.H
        ops = [Op("embed", -1, "embed", elems=H, note="1 row of 163840x7168 bf16 table")]
        prev = "embed"
        nblocks = 0
        for L in range(self.nL):
            p = f"L{L}."
            if nblocks > 0:
                ops.append(Op(p + "attnres_attn", L, "attnres", elems=(nblocks + 1) * H, deps=[prev],
                              note=f"softmax mix of {nblocks + 1} block residuals"))
                prev = p + "attnres_attn"
            if L % c["attn_res_block_size"] == 0:
                nblocks += 1
            ops.append(Op(p + "input_norm", L, "norm", elems=H, deps=[prev]))
            if L in self.kda_layers:
                a, out = self._attn_kda(L, p + "input_norm")
            else:
                a, out = self._attn_mla(L, p + "input_norm")
            ops += a
            ops.append(Op(p + "resid_attn", L, "add", elems=H, deps=[out]))
            ops.append(Op(p + "attnres_mlp", L, "attnres", elems=(nblocks + 1) * H, deps=[p + "resid_attn"]))
            ops.append(Op(p + "post_norm", L, "norm", elems=H, deps=[p + "attnres_mlp"]))
            if L in self.dense_layers:
                m, out = self._mlp_dense(L, p + "post_norm")
            else:
                m, out = self._mlp_moe(L, p + "post_norm")
            ops += m
            ops.append(Op(p + "resid_mlp", L, "add", elems=H, deps=[out]))
            prev = p + "resid_mlp"
        ops += [
            Op("final_attnres", self.nL, "attnres", elems=(nblocks + 1) * H, deps=[prev]),
            Op("final_norm", self.nL, "norm", elems=H, deps=["final_attnres"]),
            Op("lm_head", self.nL, "linear", H, c["vocab_size"], wdtype="bf16", deps=["final_norm"]),
            Op("sample", self.nL, "sample", elems=c["vocab_size"], deps=["lm_head"], note="argmax/top-p over 163840"),
        ]
        self.n_blocks_final = nblocks
        names = [o.name for o in ops]
        assert len(names) == len(set(names))
        return ops

    # --------------------------------------------------------------- metrics
    def linear_ops(self):
        return [o for o in self.ops if o.kind == "linear"]

    def stored_params(self):
        """Stored text-model parameters by dtype from the op graph (+ embedding)."""
        out = {"bf16": 0, "mxfp4": 0}
        for o in self.linear_ops():
            out[o.wdtype] += o.stored_weights
        out["bf16"] += self.cfg["vocab_size"] * self.H   # embedding table
        return out

    def active_params(self):
        out = {"bf16": 0, "mxfp4": 0}
        for o in self.linear_ops():
            out[o.wdtype] += o.active_weights
        out["bf16_embedding_row"] = self.H
        return out

    def active_weight_bytes(self):
        return sum(o.active_weights * BYTES_PER_WEIGHT[o.wdtype] for o in self.linear_ops())

    def kv_cache_bytes(self, L):
        c = self.cfg
        per_tok = (c["kv_lora_rank"] + c["qk_rope_head_dim"]) * len(self.mla_layers) * self.kv_bytes
        return per_tok * L

    def kv_cache_bytes_naive(self, L):
        """Non-absorbed (expanded per-head K and V) cache, as in the HF reference code."""
        c = self.cfg
        per = c["num_attention_heads"] * (c["qk_nope_head_dim"] + c["qk_rope_head_dim"] + c["v_head_dim"])
        return per * len(self.mla_layers) * self.kv_bytes * L

    def kda_state_bytes_total(self):
        la = self.cfg["linear_attn_config"]
        rec = la["num_heads"] * la["head_dim"] ** 2 * self.kda_state_bytes
        conv = 3 * la["num_heads"] * la["head_dim"] * (la["short_conv_kernel_size"] - 1) * 2
        return len(self.kda_layers) * (rec + conv)

    def decode_macs(self, L):
        """MACs for one decode token at context length L (linear + attention + KDA)."""
        lin = sum(o.macs for o in self.ops)
        att = 0
        for o in self.ops:
            if o.kind in ("attn_score", "attn_value"):
                att += o.K * o.N * L
        la = self.cfg["linear_attn_config"]
        kda = len(self.kda_layers) * 4 * la["num_heads"] * la["head_dim"] ** 2
        return {"linear": lin, "attention": att, "kda": kda, "total": lin + att + kda}

    def decode_bytes_moved(self, L):
        """Unavoidable bytes touched per decode token if weights are *streamed* (not in-situ)."""
        return {"weights": self.active_weight_bytes(), "kv_read": self.kv_cache_bytes(L),
                "kda_state_rw": 2 * self.kda_state_bytes_total()}

    def prefill_macs(self, T):
        """MACs to prefill T prompt tokens (causal attention: sum_{t<T} t)."""
        lin = sum(o.macs for o in self.ops) * T
        att_per_ctx = sum(o.K * o.N for o in self.ops if o.kind in ("attn_score", "attn_value"))
        att = att_per_ctx * T * (T + 1) / 2
        la = self.cfg["linear_attn_config"]
        kda = len(self.kda_layers) * 4 * la["num_heads"] * la["head_dim"] ** 2 * T
        return {"linear": lin, "attention": att, "kda": kda, "total": lin + att + kda}

    def critical_path_ops(self, latency_fn):
        """Longest path through the op DAG. latency_fn(op) -> seconds. Returns (total, path)."""
        finish, pred = {}, {}
        for o in self.ops:   # ops are in topological order by construction
            start, best = 0.0, None
            for d in o.deps:
                if finish[d] > start:
                    start, best = finish[d], d
            finish[o.name] = start + latency_fn(o)
            pred[o.name] = best
        end = max(finish, key=finish.get)
        path, n = [], end
        while n is not None:
            path.append(n)
            n = pred[n]
        return finish[end], path[::-1]

    def sequential_linear_depth(self):
        """Number of linear ops on the critical path when every linear op costs 1 and others 0."""
        t, path = self.critical_path_ops(lambda o: 1.0 if o.kind == "linear" else 0.0)
        return int(t), path

    def sync_depth(self):
        """Critical path counting linear ops AND global reductions (norm/attnres/topk/softmax/combine)."""
        heavy = {"linear", "norm", "attnres", "router_topk", "softmax", "combine", "sample"}
        t, path = self.critical_path_ops(lambda o: 1.0 if o.kind in heavy else 0.0)
        return int(t), path


def manifest_check(wl: K3Workload, manifest_path=MANIFEST_PATH):
    """Compare op-graph parameter counts with the real checkpoint manifest."""
    rows = list(csv.DictReader(open(manifest_path)))
    ck = {"bf16": 0, "mxfp4": 0, "fp32": 0, "vision_bf16": 0}
    for r in rows:
        n, dt, ne = r["tensor_pattern"], r["dtype"], int(r["elements_total"])
        if n.startswith(("vision_tower", "mm_projector")):
            ck["vision_bf16"] += ne
        elif dt == "BF16":
            ck["bf16"] += ne
        elif dt == "F32":
            ck["fp32"] += ne
        elif n.endswith("weight_packed"):
            ck["mxfp4"] += ne * 2
    # small BF16 params not modelled as linear ops: norms, attn-res projections, gate bias are F32
    small_bf16 = sum(int(r["elements_total"]) for r in rows if r["dtype"] == "BF16" and
                     not r["tensor_pattern"].startswith(("vision_tower", "mm_projector")) and
                     any(s in r["tensor_pattern"] for s in ("norm.weight", "res_proj.weight", "layernorm.weight")))
    g = wl.stored_params()
    return {"checkpoint": ck, "graph": g, "small_bf16_not_in_graph": small_bf16,
            "bf16_match": g["bf16"] + small_bf16 == ck["bf16"], "mxfp4_match": g["mxfp4"] == ck["mxfp4"]}
