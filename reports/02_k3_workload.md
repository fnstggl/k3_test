# Gate 3 — Exact Kimi K3 decode workload on NAND-PIM

Run: `python3 experiments/k3_baseline.py` → `results/k3_baseline.json`.

## Parameter accounting cross-check (MODEL, asserted in code)

From configs/k3.yaml shapes (sources: TR Table 1/§2, HF config, vLLM kimi_k3):

| Quantity | Derived | Published | Error |
|---|---|---|---|
| Total params | 2.7795 T | 2.78 T | 0.02% |
| Active/token | 104.18 B | 104.2 B | 0.02% |

Pools (the structural split that drives everything):

| Pool | Params/token | Storage | Format | Bytes/token |
|---|---|---|---|---|
| Routed experts (16 of 896 × 92 layers) | 48.6 B active of 2.72 T stored | **1.45 TB** | MXFP4 (4.25 b) | **25.8 GB** |
| Dense-active (KDA 69L + MLA 24L + shared + W↓/W↑ + router + dense FFN + LM head) | 55.6 B — touched EVERY token | 111 GB (BF16) / 57 GB (FP8) | BF16 native; FP8 deploy option | **111.1 / 57.3 GB** |
| KV/state (dynamic) | — | grows with ctx | c_t 576×2B/layer; KDA state 6.3 MB/layer | 0.4–0.9 GB DRAM |

NAND-friendly (A): all fixed-weight GEMVs above. Dynamic (B, stays in logic/DRAM):
KDA recurrent state update (69 × 12.6 MB r+w), MLA attention over compressed KV,
AttnRes block attention (tiny), router top-k/softmax, norms, sampling.
MTP layer + vision encoder excluded (no speculative decode; text-only) — noted.

## Baseline architecture (Gate 5 sweeps all of it)

`znand-slc-2TB`: 32 ch × 8 dies × 8 planes = 2048 planes, 2 KB pages, tR = 3 µs
SLC (Z-NAND-class), calibrated Gate 2 command model (period = binding phase +
dies/ch × 290 ns). `tlc-2TB`: 8 ch × 2 × 4 = 64 planes of 1Tb TLC dies, 16 KB
pages, tR = 50 µs, 10% ECC. Dynamic side: DRAM 102.4 GB/s, NPU 50 TFLOPS class.

## Where every millisecond goes (ctx=4096, single stream)

Best 2 TB configuration (`4lanes-wide-fp8dense-bf16state`, **114.8 ms/token = 8.7 tok/s**):

| Component | ms | Notes |
|---|---|---|
| KDA projections (69 L) | 40.3 | 5×88 M params/layer — single largest dense cost |
| Routed experts (92 L) | 33.8 | 16×33 M MXFP4/layer, wide-striped serial |
| MoE pre (router+W↓+shared g/u) | 15.6 | |
| MLA projections (24 L) | 7.9 | incl. absorbed kv_b GEMV |
| shared down + W↑ | 8.5 | |
| KDA state (DRAM r+w) | 4.2 | bf16 state; 8.5 ms if FP32 |
| MLA attn (KV stream) | 1.1 | 0.55 MB/layer @ ctx 4096 |
| dense FFN + LM head | 2.6 | |
| AttnRes + misc | 0.4 | |

Progression from the faithful Palm PU (all at 2 TB SLC, ctx 4096):

| Config | TPOT | tok/s | What changed |
|---|---|---|---|
| palm-pu-grouped (1 MAC/plane, 16 expert groups) | 385.7 ms | 2.6 | faithful Palm PU |
| palm-pu-wide | 230.2 ms | 4.3 | experts wide-striped, serial |
| 4lanes-wide | 186.5 ms | 5.4 | 4 MAC lanes/plane |
| + FP8 dense pool | 119.0 ms | 8.4 | halves dense bytes (accuracy caveat: non-expert pools are higher-precision by design [TR 4.1.4]) |
| + BF16 KDA state | **114.8 ms** | **8.7** | |
| tlc-2TB (64 planes) | 7 374–11 877 ms | 0.08–0.14 | commodity high-density organization is ~100× short on plane-parallelism |
| dense pool in DRAM (102 GB/s) | 1 055.7 ms | 0.95 | dense pool must be weight-resident (NAND) or on HBM-class DRAM |

## Findings (each is load-bearing for Gates 4–6)

1. **MXFP4 breaks the single-MAC PU**: a 2 KB page holds 3 855 MXFP4 weights →
   9.6 µs at 1×400 MHz ≫ tR = 3 µs. K3 needs ≥4 lanes/plane (or equivalent rate)
   just to stay sense-bound. The Palm FP16 MAC is NOT the right unit for K3.
2. **Wide-striping every expert beats expert-grouping**: work is conserved
   (same windows/plane) and collision penalties (E[max load] ≈ 2.7 for 16-of-896
   into 16 groups, Monte Carlo) vanish. Routing locality is a non-problem for
   NAND-PIM — opposite of GPU expert-parallel intuition. Replication (r=2) helps
   grouped mode but costs 2×1.45 TB and still loses to wide (and does not fit 2 TB).
3. **The dense-active pool (55.6 B params, not the experts) is the #1 cost** at
   BF16 — 111 GB/token vs 25.8 GB/token for experts. FP8 for the non-expert pool
   halves it but deviates from K3's native precision choice (flagged, not assumed).
4. **Commodity TLC organization fails by ~100×** on plane count (64 planes of
   1Tb dies vs 2 048 planes of 8GB Z-NAND-class dies for the same 2 TB).
   Density and bandwidth-per-byte are in direct tension — Gate 5's central axis.
5. **ctx sensitivity is mild** (4 096 → 65 536: 114.8 → ~203 ms driven by KV
   stream at 102 GB/s and FP32 state; the fixed-weight side is ctx-invariant).
6. Energy/token (calibrated coefficients): best config **8.2 J/token** — cell
   reads 7.4 J (90%), I/O 0.7 J. Single-stream tokens/J ≈ 0.12. Batch
   amortization of the dense pool (NOT possible for per-token-distinct expert
   selections at small batch) is the decisive economics lever → Gate 6.
7. Traffic per token (best config): internal weight bytes 81 GB sensed;
   entering NAND 356 MB (broadcast inputs + cmds); leaving NAND 849 MB
   (partials). External:internal ratio ≈ 1:67.

## Honest caveats

- Step serialization is strict (each GEMV waits for the previous op's output);
  fills = first-sense + first-compute per op. No inter-layer speculation.
- Expert selection uniformity assumes Quantile Balancing works as advertised
  (TR 2.3.3); `hot_expert_alpha` models skew (Gate 5).
- FP8-dense variant is a deployment deviation from the native checkpoint —
  kept as a labeled option, never silently defaulted.
