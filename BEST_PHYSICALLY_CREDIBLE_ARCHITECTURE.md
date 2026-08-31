# The best physically-credible architecture for native Kimi K3 on NAND

Gate 9 synthesis. This is the single architecture that maximizes, in order,
(1) $/M output tokens, (2) tokens/sec, (3) exact native-K3 correctness,
(4) minimal physical modification, (5) energy efficiency — chosen from a
calibrated physics-aware search over 3,888 composed architectures × 3 cases
(`results/gate9_all_candidates.csv`), not the fastest simulation number.

## Name: **K3-FlashReduce** (cr-read + per-plane exact shift-add reducer)

### The machine, physically, end to end

1. **Weights at rest.** K3's routed-expert weights (1.45 TB, MXFP4) and the
   dense-active pool (0.11 TB, BF16) are ESP-programmed in **SLC mode** across
   many small commodity NAND dies (the search favors 128 channels × many small
   4 GB dies → ~8,192 planes, for planes-per-dollar). Each 32-element MX block is
   laid contiguously so its E8M0 scale sits with it and its pages form long
   same-block runs.

2. **Activation enters.** The MXFP8 activation vector for the current decode
   wave is broadcast over the ONFI channels (CE#-multiplexed, one broadcast per
   die group) into per-plane input registers — the LLM-on-the-Palm input path.
   No NAND programming per token.

3. **NAND electrical operation — charge-recycling streaming read (cr-read).**
   Weight pages stream out of each plane by **consecutive same-block reads that
   reuse word-line/bit-line charge** (AiF: skip precharge/discharge, recycle
   VPASS↔VREF). Measured effect: tR 28 µs → 9.7 µs (−64 %), read energy
   18.3 → 5.1 pJ/bit (−72 %). This is the single biggest physically-grounded
   lever; it turns the sense-bound array ~2.3× cheaper per token.

4. **Sensing → latched bits.** Each sense delivers a page of MXFP4 weight bits
   to the plane's page buffer (cache-register pipelined: sense page k+1 under
   compute of page k).

5. **Local exact reduction — the tiny per-plane shift-add reducer (Gate 7).**
   Because E2M1 weight magnitudes are k/2 (k ∈ {0,1,2,3,4,6,8,12}), each product
   is a **4-term conditional shift-add, no multiplier**. A per-plane datapath of
   ~4 lanes accumulates each 32-block in fixed point, applies the two E8M0 scales,
   and accumulates into 8 retained FP32 row accumulators. This is **bit-exact**
   (proven over 40 M random cases in Gate 7 and a full 3584-dim GEMV in Gate 9E,
   rel err 0.00e+00). It is the exact popcount/shift-add the K3 dot product needs,
   done per-bitline-group locally — no cross-bitline sum required because the
   reduction is folded into the local accumulator, not the array.

6. **Batch reuse + expert-stationary scheduling.** A sensed weight page is reused
   across the wave's activation positions (dense pool amortizes fully); tokens are
   grouped by routed expert so each sensed expert serves all its consumers. K3's
   native **MTP layer** optionally drafts K tokens per user and the full model
   verifies them in one pass — **exact, lossless** — converting array batch
   headroom into per-user speed (single-user 60 → 67 tok/s).

7. **Layer output.** Only 4-byte partial sums leave the die (≈0.3 GB/token vs
   137 GB of weights that stayed inside). Attention, KDA recurrent state, MLA over
   the compressed KV cache, routing, and norms run on a conventional side engine
   from DRAM (K3's dynamic, state-dependent work — not NAND's job).

### What it delivers (native precision, ≥25 tok/s/user)

| Case | $/Mtok | agg tok/s | per-user | J/token |
|---|---|---|---|---|
| Optimistic | **$0.26** | 107 | 27 (67 w/ MTP) | 1.08 |
| Central | **$0.61** | 103 | 26 | 2.27 |
| Adversarial | $1.79 | 89 | 22 | 5.10 |

### What each piece is, by evidence and modification class

| Piece | Demonstrated? | Class |
|---|---|---|
| SLC-mode + ESP programming | measured (48-layer TLC; SET FEATURE commodity) | L2 / F0 |
| Contiguous MX-block layout | layout only, exact | — / F0 |
| Activation broadcast | LLM-on-the-Palm; standard write path | L2 / F0 |
| **cr-read streaming** | **functional correctness measured on a fabricated 9×9 array; tR/energy calibrated-SPICE** — die-internal control change, NOT commodity-commandable | **L3 (our part) / F1** |
| Per-plane shift-add reducer | Gate-7 RTL bit-exact + synthesized ~0.03% die; **independently corroborated by Ares-Flash MICRO'24** (page-buffer full-adder+shift, 32-BL range = one MX block) | L3 / F2 |
| Batch reuse / expert-stationary | exact reordering; standard dataflow | L2 / F2 |
| MTP speculative decode | K3-native, lossless | L1 / F0 |

**Already physically demonstrated:** SLC/ESP, activation broadcast, the reducer's
arithmetic (bit-exact in sim + synthesized), MTP speculation, and — on our exact
part (MCFlash) — user-mode read-offset bitwise ops. **Probably exposable
(needs vendor/test-mode):** cr-read control (X-decoder + timer), multi-wordline
sensing. **Tiny modification (F2):** the per-plane shift-add reducer (Ares-Flash
class). **Still speculative (L3):** an exposed maskable fail-bit count and any
analog source-line sum — neither is needed by K3-FlashReduce, and both lose or
go non-exact, so they are excluded from the headline.

### Does it hit the Gate-9 targets?

**No, not fully — and this is the honest result.** K3-FlashReduce reaches
~$0.26/Mtok (opt) / ~$0.61 (central) at 25 tok/s/user, native precision. It does
**not** reach the $0.10/Mtok absolute target at interactive latency, and does not
beat the best at-scale GPU K3 serving ($0.11–0.36/Mtok, refreshed 2026-08-31).
It **does** beat naive single-node / low-concurrency GPU serving ($6–12/Mtok) by
**~10–40×**, and it delivers a minimum-deployment granularity GPUs cannot
(~$3 k / ~100 W appliance vs ~$550 k / ~12 kW node).

### The single highest-impact next physical experiment

**Can cr-read be triggered on the Micron MT29F1T08EELEEJ4-R:E via a BABOL-class
controller, and what tR/energy results?** cr-read is worth ~2.3× on $/Mtok and is
the one L3/F1 primitive the whole architecture leans on. BABOL (MICRO'24) already
proves a software-defined controller can drive vendor-specific command prefixes,
pSLC reads, and ns-timed sequences on a Micron part — so the experiment is
executable. If cr-read (or an equivalent charge-reuse read) is exposable on this
die at ≈10 µs SLC tR, K3-FlashReduce holds at ~$0.26–0.61/Mtok; if not, it
degrades to the L2-commodity floor (~$0.45 opt / ~$1.4 central) — still a strong
low-concurrency play, but further from the target. This is BABOL_TEST_SPEC E6.
