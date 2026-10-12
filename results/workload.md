# Kimi K3 inference workload — reconstructed from the released checkpoint

All numbers below are computed by `k3cim/workload.py` from `data/k3/config.json` (HF `moonshotai/Kimi-K3`, revision `f831ab66`) and the safetensors headers of all 96 shards (`scripts/fetch_k3_manifest.py`, 497,220 tensors). Nothing is taken from prior estimates.

## 1. Verified architecture

| item | value | source |
|---|---|---|
| decoder layers | 93 | config |
| hidden size | 7168 | config |
| attention layers | 69 KDA (linear, delta-rule) + 24 gated MLA (full, NoPE) | config `linear_attn_config` (1-based indices: MLA at 4,8,...,92,93) |
| KDA | 96 heads x 128, short conv k=4, full-rank output gate, gate lower bound -5.0 | config + modeling_kimi_linear.py |
| MLA | 96 heads, q_lora 1536, kv_lora 512, qk_nope 128 + rope-dim 64 (no RoPE applied), v 128, sigmoid output gate | config |
| MoE | 896 routed experts, top-16, 2 shared, latent dim 3584, expert FFN 3072 | config |
| router | sigmoid + e_score_correction_bias, top-16, renormalised, scale 1.0 | modeling code |
| dense layers | 1 (layer 0, FFN 33792) | config |
| activation | SiTU-GLU (beta=4.0, linear_beta=25.0) | config + code |
| attention residuals | block size 12 -> 8 blocks; softmax mix before every attention/MLP | code |
| vocab / context | 163840 / 1048576 | config |
| MTP / next-n layers | 0 | config (no MTP head in the release) |
| weight quantization | MXFP4 (E2M1, E8M0 scale per 32) for routed experts only; attention, shared experts, dense MLP, latent projections, router, lm_head, embeddings are BF16 | config `quantization_config.ignore` + tensor dtypes |
| activation quantization | model card: MXFP8 activations (QAT); checkpoint config lists `input_activations: null` | README + config (scope of MXFP8 activations per layer is NOT specified -> unverified) |

Checkpoint detail found while re-implementing: `self_attn.A_log` is stored with 128 entries; only the first 96 (one per KDA head) are non-zero — the rest are zero padding.

## 2. Storage (exact, from tensor headers)

| component | bytes | elements |
|---|---:|---:|
| MXFP4 packed codes (routed experts) | 1361.37 GB | 2.7227 T weights |
| MXFP4 E8M0 scales (1 byte / 32 weights) | 85.09 GB | |
| BF16 tensors (text) | 113.47 GB | 56.73 G |
| BF16 vision tower + projector | 0.89 GB | |
| F32 (A_log, dt_bias, conv kernels, router bias, o_norm) | 44.5 MB | 11.12 M |
| **total** | **1560.86 GB** | **2.7799 T params** |

Effective bits per routed-expert weight = 4 + 8/32 = **4.25**. BF16 share of bytes = 7.3% although BF16 is only 2.1% of parameters.

Op-graph cross-check: graph MXFP4 params = checkpoint (True); graph BF16 linear params + small norm/res-proj vectors = checkpoint (True).

## 3. Exact matrix dimensions per layer (decode, one token)

| layer type | count | matrix | K (in) | N (out) | copies active / stored | dtype |
|---|---|---|---:|---:|---|---|
| kda | 69 | q_proj | 7168 | 12288 | 1 / 1 | bf16 |
| kda | 69 | k_proj | 7168 | 12288 | 1 / 1 | bf16 |
| kda | 69 | v_proj | 7168 | 12288 | 1 / 1 | bf16 |
| kda | 69 | g_proj | 7168 | 12288 | 1 / 1 | bf16 |
| kda | 69 | f_a_proj | 7168 | 128 | 1 / 1 | bf16 |
| kda | 69 | b_proj | 7168 | 96 | 1 / 1 | bf16 |
| kda | 69 | f_b_proj | 128 | 12288 | 1 / 1 | bf16 |
| kda | 69 | o_proj | 12288 | 7168 | 1 / 1 | bf16 |
| mlp | 1 | gate_proj | 7168 | 33792 | 1 / 1 | bf16 |
| mlp | 1 | up_proj | 7168 | 33792 | 1 / 1 | bf16 |
| mlp | 1 | down_proj | 33792 | 7168 | 1 / 1 | bf16 |
| moe | 92 | router | 7168 | 896 | 1 / 1 | bf16 |
| moe | 92 | latent_down | 7168 | 3584 | 1 / 1 | bf16 |
| moe | 92 | shared_gate | 7168 | 6144 | 1 / 1 | bf16 |
| moe | 92 | shared_up | 7168 | 6144 | 1 / 1 | bf16 |
| moe | 92 | shared_down | 6144 | 7168 | 1 / 1 | bf16 |
| moe | 92 | expert_w1 | 3584 | 3072 | 16 / 896 | mxfp4 |
| moe | 92 | expert_w3 | 3584 | 3072 | 16 / 896 | mxfp4 |
| moe | 92 | expert_w2 | 3072 | 3584 | 16 / 896 | mxfp4 |
| moe | 92 | latent_up | 3584 | 7168 | 1 / 1 | bf16 |
| mla | 24 | q_a_proj | 7168 | 1536 | 1 / 1 | bf16 |
| mla | 24 | kv_a_proj | 7168 | 576 | 1 / 1 | bf16 |
| mla | 24 | g_proj | 7168 | 12288 | 1 / 1 | bf16 |
| mla | 24 | q_b_proj | 1536 | 18432 | 1 / 1 | bf16 |
| mla | 24 | uk_absorb | 128 | 512 | 96 / 96 | bf16 |
| mla | 24 | uv_absorb | 512 | 128 | 96 / 96 | bf16 |
| mla | 24 | o_proj | 12288 | 7168 | 1 / 1 | bf16 |
| head | 1 | lm_head | 7168 | 163840 | 1 / 1 | bf16 |

MLA is listed in the weight-absorbed decode form used by production engines: W_UK and W_UV (the two halves of `kv_b_proj`, 24576x512) act per head on the 576-value latent cache.

## 4. Active weights per token

| component | active params | bytes if streamed |
|---|---:|---:|
| routed experts (MXFP4) | 48.62 B | 25.83 GB |
| KDA attention projections | 30.61 B | 61.21 GB |
| MoE router + latent proj + shared experts (BF16) | 17.47 B | 34.95 GB |
| MLA attention projections | 5.57 B | 11.15 GB |
| lm_head | 1.17 B | 2.35 GB |
| dense MLP (layer 0) | 0.73 B | 1.45 GB |
| **total** | **104.17 B** (model card: 104B) | **136.9 GB** |

The BF16 *always-active* part (55.6 B params, 111 GB/token) dominates bandwidth; the MXFP4 experts dominate capacity (2.72 T of 2.78 T params). Estimates that assume ~4-bit storage everywhere (~55 GB/token) undercount by ~2.5x.

## 5. Routed-expert placement facts

* one expert = 3 matrices (w1,w3: 3584->3072; w2: 3072->3584) = 33.03 M weights = 17.55 MB (codes 16.52 MB + scales 1.03 MB)
* 92 MoE layers x 896 experts = 82,432 experts; 16 active per layer per token = 1.8% of each layer's experts

## 6. Attention state: KV cache and KDA recurrent state

MLA caches the 512-d compressed latent + 64-d decoupled key per token per MLA layer (576 values x 24 layers). KDA keeps a fixed 96x128x128 state per layer (fp32 in the reference kernels) plus a 3-step conv state.

| context | MLA latent KV (BF16) | (FP8) | naive expanded K/V (BF16, HF reference code) | KDA state (fp32, constant) |
|---|---:|---:|---:|---:|
| 32K | 0.91 GB | 0.45 GB | 48 GB | 449 MB |
| 128K | 3.62 GB | 1.81 GB | 193 GB | 449 MB |
| 1024K | 28.99 GB | 14.50 GB | 1546 GB | 449 MB |

KV is append-only (write once per token per layer: 27.6 KB/token in BF16); the KDA state is read *and rewritten* every token (2 x 449 MB/token) -> it cannot live in NAND (endurance) and needs DRAM/SRAM bandwidth of 0.45 TB/s at 500 tok/s.

## 7. Compute per token: decode vs prefill

| context L | linear MACs | MLA attention MACs | KDA MACs | total GFLOP/token | attention share |
|---|---:|---:|---:|---:|---:|
| short | 104.17 G | 2.51 M | 434.11 M | 209 | 0.0% |
| 32768 | 104.17 G | 82.14 G | 434.11 M | 373 | 44.0% |
| 131072 | 104.17 G | 328.56 G | 434.11 M | 866 | 75.9% |
| 1048576 | 104.17 G | 2.63 T | 434.11 M | 5466 | 96.2% |

MLA decode attention is compute-bound, not bandwidth-bound: all 96 heads attend over the same 576-value latent, so arithmetic intensity is ~181 FLOP/byte (BF16 cache). At 1M context one token needs 5.3 TFLOP of attention math (25x the weight MVMs) and 29 GB of KV reads.

| prompt length | prefill TFLOP (linear) | prefill TFLOP (attention, causal) | total |
|---|---:|---:|---:|
| 32K | 6,827 | 2,692 | 9,547 |
| 128K | 27,309 | 43,066 | 70,488 |
| 1024K | 218,469 | 2,756,206 | 2,975,585 |

Prefill is a different regime: batched over prompt tokens, compute-bound, and for a weight-stationary CIM device each prompt token still needs its own array operation per stage. This study targets decode; prefill throughput of each architecture is reported separately where modelled (`results/architecture_comparison.csv`).

## 8. Inter-layer communication and dependencies (per token)

* residual stream: 7168 values between every sub-block; attention residuals mix up to 9 stored 7168-d block vectors before every attention and MLP (softmax over blocks -> global reduction)
* MoE: latent 3584-d vector broadcast to the 16 selected experts; 16 x 3584 partial outputs gathered and combined, then RMSNorm over 3584 (global reduction), then latent_up
* MLA: latent (576) appended to the cache; scores/softmax over L tokens per head; KDA: per-head state update

**Critical path:** 698 matrix-vector operations must execute strictly in sequence per token (1396 sequential steps when global reductions — norms, attention-residual softmaxes, top-k, softmax, expert combine — are counted). With W_UK/W_UV folded into q_b (exact refactoring, +1.2 B params) the linear depth is 674.

Time budget per sequential step at 500 tok/s: 2 ms / 1396 = **1.43 µs** (or 2.87 µs per MVM if reductions were free). A commodity NAND page read (tR = 20-80 µs) is 10-50x this budget.

## 9. First-principles requirements at 100 / 500 / 1000 tok/s (single stream)

| requirement | 100 tok/s | 500 tok/s | 1000 tok/s |
|---|---:|---:|---:|
| weight bytes streamed (if not in-situ) | 13.7 TB/s | 68.5 TB/s | 136.9 TB/s |
| sense amplifiers needed for digital NVM streaming at tR=3 µs | 0.33 G | 1.64 G | 3.29 G |
| sense amplifiers needed for digital NVM streaming at tR=0.5 µs | 0.05 G | 0.27 G | 0.55 G |
| weight MAC rate | 10.4 TMAC/s | 52.1 TMAC/s | 104 TMAC/s |
| attention FLOP/s at 128K | 66 TFLOP/s | 329 TFLOP/s | 657 TFLOP/s |
| attention FLOP/s at 1M | 0.53 PFLOP/s | 2.63 PFLOP/s | 5.26 PFLOP/s |
| KV read bandwidth at 1M (BF16) | 2.9 TB/s | 14.5 TB/s | 29.0 TB/s |
| KDA state r/w | 0.09 TB/s | 0.45 TB/s | 0.90 TB/s |
| max latency per sequential step | 7.16 µs | 1.43 µs | 0.72 µs |

## 10. Unavailable or unverified data

* Exact scope of MXFP8 activation quantization (which linears; whether attention/KV use FP8): model card says MXFP8 activations, config says none.
* KV-cache dtype in production (BF16 assumed; FP8 shown as option).
* End-to-end accuracy of K3 under any re-quantization of its BF16 weights or under analog noise: not evaluable here (2.8T model, no GPU); only tensor-level and early-layer (0-3) propagation are measured on real data.
* Routing statistics beyond 16 tokens x 3 layers (expert popularity skew affects conflict modelling).
* Draft model / MTP acceptance rates for K3 (GPU measurements use MTP / DSpark drafts not contained in the release).
* Activations of layers > 3 (would require downloading ~17 GB per layer).
