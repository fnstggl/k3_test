#!/usr/bin/env python3
"""Exact numpy re-implementation of the first Kimi-K3 decoder layers on real text.

Purpose: obtain *real* K3 activations (inputs of every linear layer) and real
weights for the analog-precision study, instead of synthetic distributions.

The implementation follows modeling_kimi_linear.py (revision f831ab6) line by
line: attention residuals (block size 12), KDA (short conv + SiLU, L2-normed
q/k, lower-bounded gate -5*sigmoid(exp(A_log)*(g+dt_bias)), sigmoid beta,
delta-rule recurrence, gated RMSNorm), gated MLA without RoPE, latent MoE
(sigmoid router + correction bias, top-16 renormalised, 3584-d latent with
RMSNorm), shared experts and the dense SiTU-GLU MLP of layer 0.  Routed-expert
weights are dequantised exactly from the MXFP4 checkpoint.  Activations are
rounded to BF16 after every module, like the BF16 reference.

Only layers 0..N-1 are run (default 4: KDA+dense, KDA+MoE, KDA+MoE, MLA+MoE),
because later layers need every earlier layer's weights (~17 GB each).

Outputs (small, committed): data/k3/activations/k3_layers0-3.npz
"""
import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from k3cim import hf_tensors as hf  # noqa: E402
from k3cim.formats import bf16_round, dequant_mxfp4  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = "language_model.model."
TEXT = "The analog compute-in-memory chip stores weights as charge in NAND flash cells."


def tokenize(text):
    import tiktoken
    from tiktoken.load import load_tiktoken_bpe
    tok_dir = os.path.join(ROOT, ".cache", "k3_tokenizer")
    os.makedirs(tok_dir, exist_ok=True)
    for f in ("tiktoken.model", "tokenization_kimi.py"):
        p = os.path.join(tok_dir, f)
        if not os.path.exists(p):
            os.system(f"curl -sSL -o {p} {hf.BASE}{f}")
    src = open(os.path.join(tok_dir, "tokenization_kimi.py")).read()
    m = re.search(r'pat_str = "\|"\.join\(\[(.*?)\]\)', src, re.S)
    parts = re.findall(r'r"""(.*?)"""', m.group(1), re.S)
    enc = tiktoken.Encoding(name="kimi", pat_str="|".join(parts),
                            mergeable_ranks=load_tiktoken_bpe(os.path.join(tok_dir, "tiktoken.model")),
                            special_tokens={})
    return enc.encode(text)


def rms(x, w, eps):
    x = x.astype(np.float32)
    y = x / np.sqrt(np.mean(x * x, axis=-1, keepdims=True) + eps)
    return bf16_round(w * bf16_round(y))


def lin(x, w):  # w: [out, in]
    return bf16_round(x.astype(np.float32) @ w.T)


def silu(x):
    return x / (1.0 + np.exp(-x))


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def situ_and_mul(gate, up, beta, linear_beta):
    gate = gate.astype(np.float32)
    up = up.astype(np.float32)
    a = beta * np.tanh(gate / beta) * sigmoid(gate)
    if linear_beta is not None:
        up = linear_beta * np.tanh(up / linear_beta)
    return bf16_round(a * up)


def apply_attn_res(prefix_sum, block_residual, proj_w, norm_w, eps):
    v = np.concatenate([block_residual, prefix_sum[:, None, :]], axis=1).astype(np.float32)
    k = v / np.sqrt(np.mean(v * v, axis=-1, keepdims=True) + eps)
    sw = (norm_w.astype(np.float32) * proj_w.reshape(-1).astype(np.float32))
    scores = (k * sw).sum(-1)
    scores -= scores.max(-1, keepdims=True)
    p = np.exp(scores)
    p /= p.sum(-1, keepdims=True)
    return bf16_round(np.einsum("tb,tbh->th", p, v)), p


def causal_conv_silu(x, w):  # x [T, C], w [C, 1, 4]
    T, C = x.shape
    K = w.shape[-1]
    xp = np.concatenate([np.zeros((K - 1, C), np.float32), x.astype(np.float32)], 0)
    y = np.zeros((T, C), np.float32)
    for j in range(K):
        y += w[:, 0, j][None, :] * xp[j:j + T]
    return bf16_round(silu(y))


def l2n(x, eps=1e-6):
    return x / np.sqrt((x * x).sum(-1, keepdims=True) + eps)


class Recorder(dict):
    def put(self, key, val):
        self[key] = np.asarray(val, dtype=np.float32)


def kda(L, x, cfg, rec):
    pre = f"{P}layers.{L}.self_attn."
    la = cfg["linear_attn_config"]
    H, D = la["num_heads"], la["head_dim"]
    T = x.shape[0]
    rec.put(f"L{L}.kda.in", x)
    q = causal_conv_silu(lin(x, hf.fetch(pre + "q_proj.weight")), hf.fetch(pre + "q_conv1d.weight"))
    k = causal_conv_silu(lin(x, hf.fetch(pre + "k_proj.weight")), hf.fetch(pre + "k_conv1d.weight"))
    v = causal_conv_silu(lin(x, hf.fetch(pre + "v_proj.weight")), hf.fetch(pre + "v_conv1d.weight"))
    fa = lin(x, hf.fetch(pre + "f_a_proj.weight"))
    rec.put(f"L{L}.kda.f_b.in", fa)
    g = lin(fa, hf.fetch(pre + "f_b_proj.weight")).reshape(T, H, D)
    beta = sigmoid(lin(x, hf.fetch(pre + "b_proj.weight")).astype(np.float32))
    A_log = hf.fetch(pre + "A_log")[:H]  # checkpoint stores 128 entries, zero-padded beyond 96 heads
    dt_bias = hf.fetch(pre + "dt_bias").reshape(H, D)
    gate = la["gate_lower_bound"] * sigmoid(np.exp(A_log)[None, :, None] * (g + dt_bias[None]))
    q = l2n(q.reshape(T, H, D)) * D ** -0.5
    k = l2n(k.reshape(T, H, D))
    v = v.reshape(T, H, D)
    S = np.zeros((H, D, D), np.float32)
    o = np.zeros((T, H, D), np.float32)
    for t in range(T):
        S = S * np.exp(gate[t])[:, :, None]
        kv = (k[t][:, :, None] * S).sum(1)
        S = S + np.einsum("hk,hv->hkv", beta[t][:, None] * k[t], v[t] - kv)
        o[t] = np.einsum("hk,hkv->hv", q[t], S)
    o = bf16_round(o)
    gg = lin(x, hf.fetch(pre + "g_proj.weight")).reshape(T, H, D)
    on = o / np.sqrt(np.mean(o * o, -1, keepdims=True) + cfg["rms_norm_eps"])
    on = bf16_round(on * hf.fetch(pre + "o_norm.weight")[None, None] * sigmoid(gg)).reshape(T, H * D)
    rec.put(f"L{L}.kda.o_proj.in", on)
    rec.put(f"L{L}.kda.state_absmax", np.abs(S).max(axis=(1, 2)))
    return lin(on, hf.fetch(pre + "o_proj.weight"))


def mla(L, x, cfg, rec):
    pre = f"{P}layers.{L}.self_attn."
    H = cfg["num_attention_heads"]
    dn, dr, dv, r = cfg["qk_nope_head_dim"], cfg["qk_rope_head_dim"], cfg["v_head_dim"], cfg["kv_lora_rank"]
    T = x.shape[0]
    eps = cfg["rms_norm_eps"]
    rec.put(f"L{L}.mla.in", x)
    qa = rms(lin(x, hf.fetch(pre + "q_a_proj.weight")), hf.fetch(pre + "q_a_layernorm.weight"), 1e-6)
    rec.put(f"L{L}.mla.q_b.in", qa)
    q = lin(qa, hf.fetch(pre + "q_b_proj.weight")).reshape(T, H, dn + dr)
    ckv = lin(x, hf.fetch(pre + "kv_a_proj_with_mqa.weight"))
    kpass, krot = ckv[:, :r], ckv[:, r:]
    kpass = rms(kpass, hf.fetch(pre + "kv_a_layernorm.weight"), 1e-6)
    rec.put(f"L{L}.mla.kv_b.in", kpass)
    rec.put(f"L{L}.mla.latent_cache", np.concatenate([kpass, krot], 1))
    kv = lin(kpass, hf.fetch(pre + "kv_b_proj.weight")).reshape(T, H, dn + dv)
    knope, val = kv[..., :dn], kv[..., dn:]
    key = np.concatenate([knope, np.broadcast_to(krot[:, None, :], (T, H, dr))], -1)
    sc = np.einsum("thd,shd->hts", q, key) * (dn + dr) ** -0.5
    sc = np.where(np.tril(np.ones((T, T), bool))[None], sc, -np.inf)
    sc -= sc.max(-1, keepdims=True)
    p = np.exp(sc)
    p /= p.sum(-1, keepdims=True)
    o = bf16_round(np.einsum("hts,shd->thd", p, val).reshape(T, H * dv))
    g = sigmoid(lin(x, hf.fetch(pre + "g_proj.weight")))
    o = bf16_round(o * g)
    rec.put(f"L{L}.mla.o_proj.in", o)
    return lin(o, hf.fetch(pre + "o_proj.weight"))


def dense_mlp(L, x, cfg, rec):
    pre = f"{P}layers.{L}.mlp."
    beta, lb = cfg["activation_situ_beta"], cfg["activation_situ_linear_beta"]
    rec.put(f"L{L}.mlp.in", x)
    h = situ_and_mul(lin(x, hf.fetch(pre + "gate_proj.weight")), lin(x, hf.fetch(pre + "up_proj.weight")), beta, lb)
    rec.put(f"L{L}.mlp.down.in", h)
    return lin(h, hf.fetch(pre + "down_proj.weight"))


def moe(L, x, cfg, rec, log):
    pre = f"{P}layers.{L}.block_sparse_moe."
    beta, lb = cfg["activation_situ_beta"], cfg["activation_situ_linear_beta"]
    T = x.shape[0]
    rec.put(f"L{L}.moe.in", x)
    logits = x.astype(np.float32) @ hf.fetch(pre + "gate.weight").T
    scores = sigmoid(logits)
    choice = scores + hf.fetch(pre + "gate.e_score_correction_bias")[None]
    topk = np.argsort(-choice, axis=1)[:, :cfg["num_experts_per_token"]]
    tw = np.take_along_axis(scores, topk, 1)
    tw = tw / (tw.sum(1, keepdims=True) + 1e-20) * cfg["routed_scaling_factor"]
    rec.put(f"L{L}.moe.router_logits", logits)
    rec[f"L{L}.moe.topk_idx"] = topk.astype(np.int32)
    rec.put(f"L{L}.moe.topk_w", tw)
    lat = lin(x, hf.fetch(pre + "routed_expert_down_proj.weight"))
    rec.put(f"L{L}.moe.expert.in", lat)
    uniq = np.unique(topk)
    log(f"  layer {L}: {len(uniq)} distinct experts for {T} tokens")
    names = [f"{pre}experts.{e}.{w}.{t}" for e in uniq for w in ("w1", "w2", "w3")
             for t in ("weight_packed", "weight_scale")]
    with ThreadPoolExecutor(6) as ex:
        list(ex.map(hf.fetch, names))
    log(f"  layer {L}: expert weights fetched")
    y = np.zeros((T, lat.shape[1]), np.float32)
    w2_in = []
    for e in uniq:
        ep = f"{pre}experts.{e}."
        W1 = dequant_mxfp4(hf.fetch(ep + "w1.weight_packed"), hf.fetch(ep + "w1.weight_scale")).astype(np.float32)
        W3 = dequant_mxfp4(hf.fetch(ep + "w3.weight_packed"), hf.fetch(ep + "w3.weight_scale")).astype(np.float32)
        W2 = dequant_mxfp4(hf.fetch(ep + "w2.weight_packed"), hf.fetch(ep + "w2.weight_scale")).astype(np.float32)
        rows, slots = np.nonzero(topk == e)
        xe = lat[rows]
        h = situ_and_mul(lin(xe, W1), lin(xe, W3), beta, lb)
        for i, r in enumerate(rows):
            w2_in.append((int(r), int(e), h[i]))
        y[rows] += tw[rows, slots][:, None] * lin(h, W2)
    rec[f"L{L}.moe.w2_in_token_expert"] = np.array([(a, b) for a, b, _ in w2_in], np.int32)
    rec.put(f"L{L}.moe.w2.in", np.stack([c for _, _, c in w2_in]))
    y = bf16_round(y)
    yn = rms(y, hf.fetch(pre + "routed_expert_norm.weight"), cfg["rms_norm_eps"])
    rec.put(f"L{L}.moe.latent_up.in", yn)
    out = lin(yn, hf.fetch(pre + "routed_expert_up_proj.weight"))
    sh = pre + "shared_experts."
    hs = situ_and_mul(lin(x, hf.fetch(sh + "gate_proj.weight")), lin(x, hf.fetch(sh + "up_proj.weight")), beta, lb)
    rec.put(f"L{L}.moe.shared_down.in", hs)
    return bf16_round(out + lin(hs, hf.fetch(sh + "down_proj.weight")))


def run_layers(ids, n_layers, cfg, log=print):
    """Run decoder layers 0..n_layers-1 on token ids; returns the Recorder of activations."""
    rec = Recorder()
    rec["token_ids"] = np.array(ids, np.int32)
    x = hf.fetch_rows(P + "embed_tokens.weight", ids)
    T, Hd = x.shape
    eps = cfg["rms_norm_eps"]
    block_residual = np.zeros((T, 0, Hd), np.float32)
    prefix = x
    kda_layers = set(cfg["linear_attn_config"]["kda_layers"])
    for L in range(n_layers):
        pre = f"{P}layers.{L}."
        log(f"layer {L} ({'KDA' if (L + 1) in kda_layers else 'MLA'})")
        if block_residual.shape[1] > 0:
            h, p = apply_attn_res(prefix, block_residual, hf.fetch(pre + "self_attention_res_proj.weight"),
                                  hf.fetch(pre + "self_attention_res_norm.weight"), eps)
            rec.put(f"L{L}.attnres_attn.probs", p)
        else:
            h = prefix
        if L % cfg["attn_res_block_size"] == 0:
            block_residual = np.concatenate([block_residual, prefix[:, None, :]], 1)
            prefix = None
        hn = rms(h, hf.fetch(pre + "input_layernorm.weight"), eps)
        a = kda(L, hn, cfg, rec) if (L + 1) in kda_layers else mla(L, hn, cfg, rec)
        prefix = a if prefix is None else bf16_round(prefix + a)
        h, p = apply_attn_res(prefix, block_residual, hf.fetch(pre + "mlp_res_proj.weight"),
                              hf.fetch(pre + "mlp_res_norm.weight"), eps)
        rec.put(f"L{L}.attnres_mlp.probs", p)
        hn = rms(h, hf.fetch(pre + "post_attention_layernorm.weight"), eps)
        m = dense_mlp(L, hn, cfg, rec) if L < cfg["first_k_dense_replace"] else moe(L, hn, cfg, rec, log)
        prefix = bf16_round(prefix + m)
        rec.put(f"L{L}.out", prefix)
        log(f"  out rms per token: {np.sqrt((prefix ** 2).mean(1)).round(3).tolist()}")
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layers", type=int, default=4)
    ap.add_argument("--text", default=TEXT)
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "k3", "activations", "k3_layers0-3.npz"))
    args = ap.parse_args()
    cfg = json.load(open(os.path.join(ROOT, "data", "k3", "config.json")))["text_config"]
    t0 = time.time()

    def log(m):
        print(f"[{time.time() - t0:7.1f}s] {m}", flush=True)

    ids = [cfg["bos_token_id"]] + tokenize(args.text)
    log(f"tokens ({len(ids)}): {ids}")
    rec = run_layers(ids, args.layers, cfg, log)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    np.savez_compressed(args.out, **rec)
    log(f"saved {args.out} ({os.path.getsize(args.out) / 1e6:.1f} MB), keys={len(rec)}")


if __name__ == "__main__":
    main()
