# GPU K3 serving baseline — refreshed 2026-08-31 (Gate 9)

Measured K3 serving data exists publicly (vLLM/SGLang day-0, SemiAnalysis
InferenceX, Wafer.ai, CoreWeave, provider monitors). Full datapoint table +
sources in this session's audit; key anchors:

## Best-defensible GPU K3 serving baseline

| Regime | node/GPU throughput | per-user | $/Mtok | J/token | source class |
|---|---|---|---|---|---|
| At-scale disagg fp4 (B200/B300, wide-EP) | 2,036–5,615 tok/s/GPU | 57–154 tok/s | **$0.11–0.36** (hyperscaler TCO) | 0.4–1.2 (MODEL) | measured (InferenceX) |
| Specialist rental, at scale | — | interactive | $0.3–0.6 | — | measured + rental prices |
| Naive single-node, small batch (8×B300 / 16×B200) | 313–1,568 tok/s/node | 16–110 | **$6–12** | ~12 (MODEL) | measured (Wafer.ai, NVIDIA forum) |
| API market floor (list) | — | 67–144 | $3 in / $15 out (Moonshot) | — | listed |

Measured per-user: 67–144 tok/s at leading providers (median ~105); 331–423
tok/s B=1 with DSpark speculative decoding. Comparable at-scale J/token: DeepSeek
R1 on GB200 ≈0.26 J/tok; gpt-oss-120b on B200 ≈0.36 J/tok.

## Implication for Gate 9 targets

- **$0.10/Mtok absolute** ≈ PARITY with the best at-scale GPU K3 serving ($0.11),
  i.e. ~3× better than mid-range specialist serving, and ~60–120× better than
  naive single-node GPU serving.
- **10× below best GPU K3 serving** = ~$0.011/Mtok — a very hard bar because
  at-scale Blackwell K3 serving is already extremely cheap per token.
- The Gate-6 GPU anchor ($0.96/Mtok, 1.9 J/tok at B=256) is now **conservative by
  ~2–4×** for at-scale serving → the >10× throughput-serving falsification is
  STRENGTHENED. NAND's only credible opening is the low-concurrency / capacity-$
  -bound regime, where GPU serving costs $6–12/Mtok and ~12 J/token.

Sources: vllm.ai/blog/2026-07-27-k3; lmsys.org K3 day-0; inferencex.semianalysis.com
(K3 B200-vs-B300 compare + per-dollar); wafer.ai/blog/kimi-k3-mi355x;
coreweave K3 blog; artificialanalysis.ai/models/kimi-k3/providers;
thundercompute B200/B300 pricing; getdeploying B300. (Full URL list in session log.)
