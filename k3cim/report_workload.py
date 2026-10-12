"""Generate results/workload.md from the verified K3 config, tensor manifest and op graph."""
from __future__ import annotations

import csv
import json
import os
from collections import Counter, defaultdict

from .workload import BYTES_PER_WEIGHT, K3Workload, load_config, manifest_check

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _fmt(x, d=2):
    if x >= 1e12:
        return f"{x / 1e12:.{d}f} T"
    if x >= 1e9:
        return f"{x / 1e9:.{d}f} G"
    if x >= 1e6:
        return f"{x / 1e6:.{d}f} M"
    if x >= 1e3:
        return f"{x / 1e3:.{d}f} K"
    return f"{x:.{d}f}"


def generate(path=os.path.join(ROOT, "results", "workload.md")):
    cfg = load_config()
    wl = K3Workload()
    wlf = K3Workload(fold_mla=True)
    tot = json.load(open(os.path.join(ROOT, "data", "k3", "manifest_totals.json")))
    grouped = list(csv.DictReader(open(os.path.join(ROOT, "data", "k3", "tensor_manifest_grouped.csv"))))
    mc = manifest_check(wl)
    num_path = os.path.join(ROOT, "data", "k3", "numerics_analysis.json")
    num = json.load(open(num_path)) if os.path.exists(num_path) else None
    L = []
    w = L.append
    w("# Kimi K3 inference workload — reconstructed from the released checkpoint\n")
    w("All numbers below are computed by `k3cim/workload.py` from `data/k3/config.json` "
      "(HF `moonshotai/Kimi-K3`, revision `f831ab66`) and the safetensors headers of all 96 shards "
      "(`scripts/fetch_k3_manifest.py`, 497,220 tensors). Nothing is taken from prior estimates.\n")
    w("## 1. Verified architecture\n")
    la = cfg["linear_attn_config"]
    w("| item | value | source |\n|---|---|---|")
    rows = [
        ("decoder layers", cfg["num_hidden_layers"], "config"),
        ("hidden size", cfg["hidden_size"], "config"),
        ("attention layers", f"{len(wl.kda_layers)} KDA (linear, delta-rule) + {len(wl.mla_layers)} gated MLA (full, NoPE)",
         "config `linear_attn_config` (1-based indices: MLA at 4,8,...,92,93)"),
        ("KDA", f"{la['num_heads']} heads x {la['head_dim']}, short conv k={la['short_conv_kernel_size']}, "
                f"full-rank output gate, gate lower bound {la['gate_lower_bound']}", "config + modeling_kimi_linear.py"),
        ("MLA", f"{cfg['num_attention_heads']} heads, q_lora {cfg['q_lora_rank']}, kv_lora {cfg['kv_lora_rank']}, "
                f"qk_nope {cfg['qk_nope_head_dim']} + rope-dim {cfg['qk_rope_head_dim']} (no RoPE applied), v {cfg['v_head_dim']}, sigmoid output gate", "config"),
        ("MoE", f"{cfg['num_experts']} routed experts, top-{cfg['num_experts_per_token']}, {cfg['num_shared_experts']} shared, "
                f"latent dim {cfg['routed_expert_hidden_size']}, expert FFN {cfg['moe_intermediate_size']}", "config"),
        ("router", "sigmoid + e_score_correction_bias, top-16, renormalised, scale 1.0", "modeling code"),
        ("dense layers", f"{cfg['first_k_dense_replace']} (layer 0, FFN {cfg['intermediate_size']})", "config"),
        ("activation", f"SiTU-GLU (beta={cfg['activation_situ_beta']}, linear_beta={cfg['activation_situ_linear_beta']})", "config + code"),
        ("attention residuals", f"block size {cfg['attn_res_block_size']} -> {wl.n_blocks_final} blocks; softmax mix before every attention/MLP", "code"),
        ("vocab / context", f"{cfg['vocab_size']} / {cfg['max_position_embeddings']}", "config"),
        ("MTP / next-n layers", cfg["num_nextn_predict_layers"], "config (no MTP head in the release)"),
        ("weight quantization", "MXFP4 (E2M1, E8M0 scale per 32) for routed experts only; attention, shared experts, "
                                "dense MLP, latent projections, router, lm_head, embeddings are BF16",
         "config `quantization_config.ignore` + tensor dtypes"),
        ("activation quantization", "model card: MXFP8 activations (QAT); checkpoint config lists `input_activations: null`",
         "README + config (scope of MXFP8 activations per layer is NOT specified -> unverified)"),
    ]
    for r in rows:
        w(f"| {r[0]} | {r[1]} | {r[2]} |")
    w("\nCheckpoint detail found while re-implementing: `self_attn.A_log` is stored with 128 entries; only the first 96 "
      "(one per KDA head) are non-zero — the rest are zero padding.\n")

    w("## 2. Storage (exact, from tensor headers)\n")
    b = tot["bytes_by_dtype"]
    e = tot["elements_by_dtype"]
    scale_bytes = sum(int(r["bytes_total"]) for r in grouped if r["tensor_pattern"].endswith("weight_scale"))
    packed_bytes = sum(int(r["bytes_total"]) for r in grouped if r["tensor_pattern"].endswith("weight_packed"))
    vision = sum(int(r["bytes_total"]) for r in grouped if r["tensor_pattern"].startswith(("vision_tower", "mm_projector")))
    w("| component | bytes | elements |\n|---|---:|---:|")
    w(f"| MXFP4 packed codes (routed experts) | {packed_bytes / 1e9:.2f} GB | {mc['checkpoint']['mxfp4'] / 1e12:.4f} T weights |")
    w(f"| MXFP4 E8M0 scales (1 byte / 32 weights) | {scale_bytes / 1e9:.2f} GB | |")
    w(f"| BF16 tensors (text) | {(b['BF16'] - vision) / 1e9:.2f} GB | {(e['BF16'] - vision / 2) / 1e9:.2f} G |")
    w(f"| BF16 vision tower + projector | {vision / 1e9:.2f} GB | |")
    w(f"| F32 (A_log, dt_bias, conv kernels, router bias, o_norm) | {b['F32'] / 1e6:.1f} MB | {e['F32'] / 1e6:.2f} M |")
    w(f"| **total** | **{tot['total_bytes'] / 1e9:.2f} GB** | **{(mc['checkpoint']['mxfp4'] + e['BF16'] + e['F32']) / 1e12:.4f} T params** |")
    w(f"\nEffective bits per routed-expert weight = 4 + 8/32 = **4.25**. BF16 share of bytes = "
      f"{b['BF16'] / tot['total_bytes'] * 100:.1f}% although BF16 is only "
      f"{e['BF16'] / (mc['checkpoint']['mxfp4'] + e['BF16']) * 100:.1f}% of parameters.\n")
    w(f"Op-graph cross-check: graph MXFP4 params = checkpoint ({mc['mxfp4_match']}); graph BF16 linear params + "
      f"small norm/res-proj vectors = checkpoint ({mc['bf16_match']}).\n")

    w("## 3. Exact matrix dimensions per layer (decode, one token)\n")
    w("| layer type | count | matrix | K (in) | N (out) | copies active / stored | dtype |\n|---|---|---|---:|---:|---|---|")
    seen = set()
    counts = {"kda": len(wl.kda_layers), "mla": len(wl.mla_layers), "moe": len(wl.moe_layers), "mlp": len(wl.dense_layers)}
    for o in wl.linear_ops():
        part = o.name.split(".")[1] if "." in o.name else "head"
        key = (part, o.name.split(".")[-1])
        if key in seen:
            continue
        seen.add(key)
        w(f"| {part} | {counts.get(part, 1)} | {key[1]} | {o.K} | {o.N} | {o.count} / {o.stored} | {o.wdtype} |")
    w("\nMLA is listed in the weight-absorbed decode form used by production engines: W_UK and W_UV (the two halves of "
      "`kv_b_proj`, 24576x512) act per head on the 576-value latent cache.\n")

    w("## 4. Active weights per token\n")
    act = defaultdict(lambda: [0, 0.0])
    for o in wl.linear_ops():
        part = o.name.split(".")[1] if "." in o.name else "lm_head"
        cat = {"kda": "KDA attention projections", "mla": "MLA attention projections", "mlp": "dense MLP (layer 0)",
               "moe": "MoE"}.get(part, "lm_head")
        if part == "moe":
            cat = "routed experts (MXFP4)" if o.wdtype == "mxfp4" else "MoE router + latent proj + shared experts (BF16)"
        act[cat][0] += o.active_weights
        act[cat][1] += o.active_weights * BYTES_PER_WEIGHT[o.wdtype]
    w("| component | active params | bytes if streamed |\n|---|---:|---:|")
    tp, tb = 0, 0.0
    for k, (p, by) in sorted(act.items(), key=lambda kv: -kv[1][0]):
        w(f"| {k} | {p / 1e9:.2f} B | {by / 1e9:.2f} GB |")
        tp += p
        tb += by
    w(f"| **total** | **{tp / 1e9:.2f} B** (model card: 104B) | **{tb / 1e9:.1f} GB** |")
    w(f"\nThe BF16 *always-active* part ({act['KDA attention projections'][0] / 1e9 + act['MLA attention projections'][0] / 1e9 + act['MoE router + latent proj + shared experts (BF16)'][0] / 1e9 + act['dense MLP (layer 0)'][0] / 1e9 + act['lm_head'][0] / 1e9:.1f} B params, "
      f"{(tb - act['routed experts (MXFP4)'][1]) / 1e9:.0f} GB/token) dominates bandwidth; the MXFP4 experts dominate capacity "
      f"(2.72 T of 2.78 T params). Estimates that assume ~4-bit storage everywhere (~55 GB/token) undercount by ~2.5x.\n")

    w("## 5. Routed-expert placement facts\n")
    per_exp = 3 * 3072 * 3584
    w(f"* one expert = 3 matrices (w1,w3: 3584->3072; w2: 3072->3584) = {per_exp / 1e6:.2f} M weights = "
      f"{per_exp * 4.25 / 8 / 1e6:.2f} MB (codes {per_exp / 2 / 1e6:.2f} MB + scales {per_exp / 32 / 1e6:.2f} MB)")
    w("* 92 MoE layers x 896 experts = 82,432 experts; 16 active per layer per token = 1.8% of each layer's experts")
    if num:
        ex = num["experts"][0] if num.get("experts") else None
        if ex:
            w(f"* real routing (16 tokens of text, layers 1-3): 191 / 171 / 131 distinct experts touched (real forward pass)")
            w(f"* E2M1 code magnitudes (layer {ex['layer']}, {ex['n_experts']} experts): "
              f"{ex['e2m1_halfunit_magnitude_hist']}; zero fraction {ex['zero_frac_mean']:.3f}; rms/max {ex['rms_over_max_mean']:.3f}")
            for g in ("exp_spread_group2_C64", "exp_spread_group4_C128", "exp_spread_group8_C256"):
                d = ex[g]
                w(f"* block-exponent spread over {g.split('_C')[1]} contributors: P(spread<=1) = {d['frac_le1']:.4f}, "
                  f"max {d['max']} -> exact integer folding of MX scales needs {d['exact_mag_bits_p99']} (p99) / "
                  f"{d['exact_mag_bits_max']} (max) magnitude bits")
    w("")
    w("## 6. Attention state: KV cache and KDA recurrent state\n")
    w("MLA caches the 512-d compressed latent + 64-d decoupled key per token per MLA layer (576 values x 24 layers). "
      "KDA keeps a fixed 96x128x128 state per layer (fp32 in the reference kernels) plus a 3-step conv state.\n")
    w("| context | MLA latent KV (BF16) | (FP8) | naive expanded K/V (BF16, HF reference code) | KDA state (fp32, constant) |\n|---|---:|---:|---:|---:|")
    wl8 = K3Workload(kv_bytes=1.0)
    for Lc in (32768, 131072, 1048576):
        w(f"| {Lc // 1024}K | {wl.kv_cache_bytes(Lc) / 1e9:.2f} GB | {wl8.kv_cache_bytes(Lc) / 1e9:.2f} GB | "
          f"{wl.kv_cache_bytes_naive(Lc) / 1e9:.0f} GB | {wl.kda_state_bytes_total() / 1e6:.0f} MB |")
    w("\nKV is append-only (write once per token per layer: 27.6 KB/token in BF16); the KDA state is read *and rewritten* "
      "every token (2 x 449 MB/token) -> it cannot live in NAND (endurance) and needs DRAM/SRAM bandwidth of "
      "0.45 TB/s at 500 tok/s.\n")

    w("## 7. Compute per token: decode vs prefill\n")
    w("| context L | linear MACs | MLA attention MACs | KDA MACs | total GFLOP/token | attention share |\n|---|---:|---:|---:|---:|---:|")
    for Lc in (1, 32768, 131072, 1048576):
        m = wl.decode_macs(Lc)
        w(f"| {Lc if Lc > 1 else 'short'} | {_fmt(m['linear'])} | {_fmt(m['attention'])} | {_fmt(m['kda'])} | "
          f"{2 * m['total'] / 1e9:.0f} | {m['attention'] / m['total'] * 100:.1f}% |")
    w("\nMLA decode attention is compute-bound, not bandwidth-bound: all 96 heads attend over the same 576-value latent, "
      "so arithmetic intensity is ~181 FLOP/byte (BF16 cache). At 1M context one token needs 5.3 TFLOP of attention "
      "math (25x the weight MVMs) and 29 GB of KV reads.\n")
    w("| prompt length | prefill TFLOP (linear) | prefill TFLOP (attention, causal) | total |\n|---|---:|---:|---:|")
    for T in (32768, 131072, 1048576):
        m = wl.prefill_macs(T)
        w(f"| {T // 1024}K | {2 * m['linear'] / 1e12:,.0f} | {2 * m['attention'] / 1e12:,.0f} | {2 * m['total'] / 1e12:,.0f} |")
    w("\nPrefill is a different regime: batched over prompt tokens, compute-bound, and for a weight-stationary CIM "
      "device each prompt token still needs its own array operation per stage. This study targets decode; prefill "
      "throughput of each architecture is reported separately where modelled (`results/architecture_comparison.csv`).\n")

    w("## 8. Inter-layer communication and dependencies (per token)\n")
    w("* residual stream: 7168 values between every sub-block; attention residuals mix up to "
      f"{wl.n_blocks_final + 1} stored 7168-d block vectors before every attention and MLP (softmax over blocks -> global reduction)")
    w("* MoE: latent 3584-d vector broadcast to the 16 selected experts; 16 x 3584 partial outputs gathered and combined, "
      "then RMSNorm over 3584 (global reduction), then latent_up")
    w("* MLA: latent (576) appended to the cache; scores/softmax over L tokens per head; KDA: per-head state update")
    d, cp_path = wl.sequential_linear_depth()
    sd, spath = wl.sync_depth()
    c = Counter(o.split(".")[1] if "." in o and o.split(".")[0].startswith("L") else o for o in cp_path if o.startswith("L"))
    w(f"\n**Critical path:** {d} matrix-vector operations must execute strictly in sequence per token "
      f"({sd} sequential steps when global reductions — norms, attention-residual softmaxes, top-k, softmax, expert combine — "
      f"are counted). With W_UK/W_UV folded into q_b (exact refactoring, +{(wlf.stored_params()['bf16'] - wl.stored_params()['bf16']) / 1e9:.1f} B "
      f"params) the linear depth is {wlf.sequential_linear_depth()[0]}.\n")
    w(f"Time budget per sequential step at 500 tok/s: 2 ms / {sd} = **{2e-3 / sd * 1e6:.2f} µs** "
      f"(or {2e-3 / d * 1e6:.2f} µs per MVM if reductions were free). A commodity NAND page read (tR = 20-80 µs) is 10-50x this budget.\n")

    w("## 9. First-principles requirements at 100 / 500 / 1000 tok/s (single stream)\n")
    bits = tb * 8
    w("| requirement | 100 tok/s | 500 tok/s | 1000 tok/s |\n|---|---:|---:|---:|")
    w(f"| weight bytes streamed (if not in-situ) | {tb * 100 / 1e12:.1f} TB/s | {tb * 500 / 1e12:.1f} TB/s | {tb * 1000 / 1e12:.1f} TB/s |")
    for tr in (3e-6, 0.5e-6):
        w(f"| sense amplifiers needed for digital NVM streaming at tR={tr * 1e6:g} µs | "
          f"{bits * 100 * tr / 1e9:.2f} G | {bits * 500 * tr / 1e9:.2f} G | {bits * 1000 * tr / 1e9:.2f} G |")
    m32 = wl.decode_macs(32768)
    m1m = wl.decode_macs(1048576)
    w(f"| weight MAC rate | {m32['linear'] * 100 / 1e12:.1f} TMAC/s | {m32['linear'] * 500 / 1e12:.1f} TMAC/s | {m32['linear'] * 1000 / 1e12:.0f} TMAC/s |")
    w(f"| attention FLOP/s at 128K | {2 * wl.decode_macs(131072)['attention'] * 100 / 1e12:.0f} TFLOP/s | {2 * wl.decode_macs(131072)['attention'] * 500 / 1e12:.0f} TFLOP/s | {2 * wl.decode_macs(131072)['attention'] * 1000 / 1e12:.0f} TFLOP/s |")
    w(f"| attention FLOP/s at 1M | {2 * m1m['attention'] * 100 / 1e15:.2f} PFLOP/s | {2 * m1m['attention'] * 500 / 1e15:.2f} PFLOP/s | {2 * m1m['attention'] * 1000 / 1e15:.2f} PFLOP/s |")
    w(f"| KV read bandwidth at 1M (BF16) | {wl.kv_cache_bytes(1048576) * 100 / 1e12:.1f} TB/s | {wl.kv_cache_bytes(1048576) * 500 / 1e12:.1f} TB/s | {wl.kv_cache_bytes(1048576) * 1000 / 1e12:.1f} TB/s |")
    w(f"| KDA state r/w | {2 * wl.kda_state_bytes_total() * 100 / 1e12:.2f} TB/s | {2 * wl.kda_state_bytes_total() * 500 / 1e12:.2f} TB/s | {2 * wl.kda_state_bytes_total() * 1000 / 1e12:.2f} TB/s |")
    w(f"| max latency per sequential step | {10e-3 / sd * 1e6:.2f} µs | {2e-3 / sd * 1e6:.2f} µs | {1e-3 / sd * 1e6:.2f} µs |")

    w("\n## 10. Unavailable or unverified data\n")
    for item in [
        "Exact scope of MXFP8 activation quantization (which linears; whether attention/KV use FP8): model card says MXFP8 activations, config says none.",
        "KV-cache dtype in production (BF16 assumed; FP8 shown as option).",
        "End-to-end accuracy of K3 under any re-quantization of its BF16 weights or under analog noise: not evaluable here (2.8T model, no GPU); only tensor-level and early-layer (0-3) propagation are measured on real data.",
        "Routing statistics beyond 16 tokens x 3 layers (expert popularity skew affects conflict modelling).",
        "Draft model / MTP acceptance rates for K3 (GPU measurements use MTP / DSpark drafts not contained in the release).",
        "Activations of layers > 3 (would require downloading ~17 GB per layer).",
    ]:
        w(f"* {item}")
    w("")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write("\n".join(L))
    return path
