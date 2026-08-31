# Gate 9C — Architecture / physics hypotheses for native-K3 on NAND

>=100 raw hypotheses in >=20 materially distinct families. Each carries a physical
mechanism, an evidence level (L1/L2/L3), a modification class (F0/F1/F2/F3), and a
STAGE-A screen verdict (survives to simulation, or rejected with reason). Sources
in `configs/nand_capabilities.yaml` + `reports/07a`. Exactness is judged against
the bit-serial popcount decomposition proven in `tests/test_gate9_exact.py`:

    an exact dot product = sum_{b,c} 2^(b+c) * popcount_i( w_i[b] AND a_i[c] )
    => the ONLY cross-lane primitive needed is an exact POPCOUNT across lanes.
    MWS AND/OR is per-bitline (vertical); it does NOT sum across bitlines.

Screen key: KEEP = simulated in Gate 9D; REJECT = fails info-flow / exactness /
latency / capacity / economics at first principles.

## Family 1 — Conventional page-sense + local digital reducer (baseline, frozen)
1. Page-sense + Gate-7 shift-add reducer, token-stationary [L2/F2, KEEP — Gate6 baseline].
2. + 4/8/16/32 lanes/plane [L2/F2, KEEP].
3. + cache-register pipelining (sense k+1 under compute k) [L1/F0, KEEP, standard].
4. Wide-striped experts vs grouped [L2/F2, KEEP — Gate3 found wide wins].
5. Export-only (compute in controller) [L1/F0, KEEP as control — Gate4 floor].
6. Failbit-count reducer instead of shift-add [L3/F1, KEEP — shows it loses].

## Family 2 — Charge-recycling read (AiF cr-read) for weight streaming
7. cr-read over contiguous dense-pool pages [L2-L3/F1, KEEP — biggest tR lever].
8. cr-read within each expert's contiguous pages [L2-L3/F1, KEEP].
9. cr-read + shift-add reducer combined [KEEP].
10. cr-read chain length = block pages; interruption penalty at expert boundaries [KEEP, modeled].
11. cr-read on random expert access (short chains) [KEEP — shows benefit shrinks].
12. cr-read + SLC-mode (fast reads amplify recycling) [KEEP].
13. cr-read voltage-reuse for MLC-mode multi-page [L3/F1, KEEP-adversarial].

## Family 3 — Flash-Cosmos MWS as an exact-arithmetic element
14. MWS-AND of weight-bitplane WL with activation-mask WL -> per-bitline product bit
    [L2/F1, KEEP — exact product, but reduction still needed].
15. MWS-AND to form sign bitplanes (two's-complement) in one sense [L2/F1, KEEP].
16. Inter-block MWS-OR for expert-union masking [L2/F1, KEEP-limited (<=4 blocks power cap)].
17. MWS 48-WL AND for a 48-way K3 reduction — REJECT: GEMV reduction is ADDITION,
    not AND; MWS gives 0 exact GEMV MACs (proven).
18. MWS + De Morgan OR-in-block for activation broadcast [L2/F1, KEEP-marginal].
19. ESP-programmed SLC weights for zero-error MWS [L2/F0, KEEP — required for any MWS].

## Family 4 — Cross-bitline popcount via program-verify fail-bit counter
20. Exposed maskable fail-bit count = one popcount/sense [L3/F1, KEEP — the key L3].
21. Count masked to 32-column MX blocks [L3/F1, KEEP].
22. Multi-block count (count across inter-block-MWS result) [L3/F1, KEEP-adversarial].
23. Count folding multiple bitplane-pairs via multi-level verify thresholds [L3/F2,
    KEEP-optimistic — the only path to >conventional density].
24. Count at <=1us (BABOL E2 target) [L3/F1, KEEP — latency-gated].

## Family 5 — MCFlash dynamic-sensing bitwise (exact, L1 on OUR part)
25. Read-offset AND/OR/XNOR/NOT on co-encoded LSB/MSB pages [L1/F0, KEEP — but
    2-operand, no reduction; used only for exact bitplane pre-products].
26. Soft-Bit-Read XNOR for sign/parity bitplanes [L1/F0, KEEP-marginal].
27. Stage runtime activation as MLC-programmed operand — REJECT: 600us program/token
    (4-5 orders over budget).
28. MCFlash bitwise + host popcount — REJECT: = export baseline.

## Family 6 — Vertically-mapped same-bitline reduction (layout invention)
29. Map a 32-elem MX block along ONE NAND string (32 of 48 WLs) [L3/F2, KEEP —
    exactness needs a per-string sum, which the string does NOT give (series
    conduction = AND, not sum); REJECT for exact sum, KEEP as analog branch].
30. Map SUM and CARRY bitplanes to separate WL groups; ripple via repeated MWS
    [L3/F3, KEEP-adversarial — carry propagation across WLs needs a lateral path].
31. Carry-save along the string with latch accumulation [L3/F3, KEEP-adversarial].
32. K3 block scales co-located on the same string as their 32 weights [L3/F2, KEEP —
    layout only, exact].
33. Sign-magnitude bitplanes on distinct WLs for one-sense sign handling [L3/F2, KEEP].

## Family 7 — Persistent-latch accumulation (ParaBit-style)
34. Cache-read-random senses feeding a retained latch accumulator [L3/F1, KEEP].
35. Latch XOR (existing) as carry-save half-adder element [L2/F1, KEEP — needs carry].
36. Chained MWS results accumulated in cache latch (>48 operands) [L2-L3/F1, KEEP].
37. Latch popcount by shift-and-count over the cache register [L3/F2, KEEP].

## Family 8 — Source-line current summation (analog popcount)
38. SL current ~ #conducting cells = analog popcount [L3/F3, KEEP as NON-QUALIFYING].
39. Analog coarse sum + digital residue correction -> exact [L3/F3, KEEP — the only
    exact analog path; needs ADC + residue passes].
40. Multi-threshold TLC classification as multi-bit ADC [L3/F3, KEEP-adversarial].
41. Time-to-discharge coding of the popcount [L3/F3, REJECT-exactness (analog noise)].

## Family 9 — Batch reuse / page residency (exact, the real lever)
42. Sense dense-pool page once, reuse across B activations in page buffer [L2/F2, KEEP].
43. Activation lanes = B held in broadcast registers [L2/F2, KEEP].
44. Dense pool fully batched (81% of bytes amortizes /B) [KEEP — dominant lever].
45. Page-resident weight across a whole expert-stationary pass [L2/F2, KEEP].
46. B sweep 1..256 with per-user latency tracking [KEEP — the tension].

## Family 10 — Expert-stationary MoE dataflow
47. Group queued tokens by routed expert; sense each expert once/wave [L2/F2, KEEP].
48. Delayed expert scheduling to grow per-expert consumer count [L2/F0, KEEP].
49. Hot-expert replication (Quantile-Balanced routing) [L2/F0, KEEP-costed].
50. Expert placement to maximize cr-read chains per expert [L3/F1, KEEP].
51. Pipeline users through 92 MoE layers with per-layer expert-stationary passes [KEEP].
52. Expert-union bound D(B)=896(1-(1-16/896)^B) [KEEP — caps amortization].

## Family 11 — Organization: planes-per-dollar
53. Many small SLC dies vs few dense dies [L2/F0, KEEP — search winner lever].
54. Max plane count per channel [KEEP].
55. Multi-plane simultaneous sensing [L2/F1, KEEP].
56. Package/channel fanout for aggregate BW [KEEP].
57. SLC-mode capacity penalty (2x cells) vs speed [L2/F0, KEEP].
58. Die-stacking / channel topology for BW/$ [L3/F2, KEEP-coarse].

## Family 12 — Hybrid DRAM-dense / NAND-expert
59. Dense-active pool (111GB) in DRAM, experts (1.45TB) in NAND [L1/F0, KEEP —
    but DRAM BW ~= NAND array BW so no free win unless HBM; REJECT-as-win, KEEP-analysis].
60. Dense pool in HBM stack + NAND experts — REJECT: HBM cost = GPU, defeats thesis.
61. Dense pool cached in controller SRAM — REJECT: 57-111GB SRAM impossible.

## Family 13 — Runtime-activation participation without programming
62. Activation as read-reference-voltage modulation [L3/F2, KEEP-adversarial (analog)].
63. Activation as bitline gating mask in page buffer [L3/F2, KEEP].
64. Activation as WL/SSL/GSL select [L3/F2, KEEP-limited].
65. Activation broadcast register + digital page-buffer mask [L2/F2, KEEP — exact].
66. Activation as MWS mask-WL (one activation bitplane per sense) [L2/F1, KEEP].

## Family 14 — tR reduction beyond cr-read
67. Pseudo-SLC / SLC-mode tR (measured 22.5us) [L2/F0, KEEP].
68. Reduced-voltage-swing reads [L3/F2, KEEP-adversarial].
69. Read only required threshold boundaries (fewer sensing phases) [L3/F1, KEEP].
70. Optimized read-reference sequence for MXFP4 levels [L3/F1, KEEP].
71. Cache-read look-ahead pipelining [L1/F0, KEEP].

## Family 15 — Lossless weight compression + local decode
72. Lossless-compress MXFP4 experts, decode in page buffer [L3/F2, KEEP — but MXFP4
    is near-incompressible (~0.98 ratio measured class); REJECT-marginal].
73. Sparsity exploitation — REJECT: not part of official K3 (would change model).
74. Shared-scale dedup across blocks [L3/F2, KEEP-marginal].

## Family 16 — ECC/randomizer datapath reuse
75. Reuse on-die BCH/LDPC syndrome hardware as a popcount [L3/F2, KEEP-speculative].
76. Data-randomizer XOR as carry-save element [L2/F1, KEEP-marginal].
77. Fail-bit counter in ECC engine exposed for masked count [L3/F1, KEEP = Family 4].

## Family 17 — Mixed-mechanism (different K3 ops on different physics)
78. Dense pool: cr-read + shift-add; experts: MWS-assisted bitplane products [KEEP].
79. Attention/KDA state: DRAM/NPU (dynamic); weights: NAND [L1/F0, KEEP — Gate3].
80. LM head: export (small, once); FFN: in-NAND [KEEP].
81. Sign/exponent: MWS; mantissa: shift-add [KEEP-adversarial].

## Family 18 — Multi-pass exact analog (digitally corrected)
82. Analog SL sum (MSBs) + digital residue senses (LSBs) [L3/F3, KEEP-exact-branch].
83. Successive-approximation threshold reconstruction [L3/F3, KEEP-adversarial].
84. Digital verification pass over analog result [L3/F3, KEEP].

## Family 19 — Charge-recycling + MWS combined
85. MWS group, retain result, recycle charge, next MWS group, combine [L3/F1, KEEP].
86. cr-read chain of MWS-AND ops for bitplane products [L3/F1, KEEP].
87. Interaction-overhead-modeled cr+MWS (not perfectly multiplicative) [KEEP].

## Family 20 — CrossBit / Ares-class minimal inter-bitline reduction
88. Add smallest inter-bitline popcount tree in page-buffer periphery [L3/F2, KEEP =
    Gate-7 reducer, already the minimum-silicon answer].
89. Local carry-save adder per 32-column block [L3/F2, KEEP = Gate-7].
90. Tree reduction across page-buffer segments [L3/F2, KEEP].

## Family 21 — Speculative / MTP acceleration (K3-native)
91. Use K3's own MTP layer (EAGLE-3 draft) for speculative decode [L1/F0, KEEP —
    exact if verified; ~2-4x per-user tok/s, model-native, NON-throughput-multiplying].
92. Draft on NPU, verify on NAND [KEEP].

## Family 22 — Economics-structural
93. Min-deployment granularity ($3k/100W appliance) [KEEP — the real niche].
94. Utilization-maximizing multi-tenant scheduling [KEEP].
95. 3-yr amortization + refresh-cost endurance [KEEP — Gate6 viable].
96. NRE-separated prototype vs high-volume unit cost [KEEP].

## Additional first-principles hypotheses
97. Bit-serial exact MAC with no multiplier (E2M1 = shift-add) [L3/F2, KEEP = Gate-7].
98. Two's-complement bitplane layout for one-pass signed accumulate [KEEP].
99. Per-32-block E8M0 scale applied as exponent add post-popcount [KEEP — exact].
100. Wallace/carry-save tree per plane for the popcount [L3/F2, KEEP = Gate-7 class].
101. Threshold-coded population count via multi-level verify [L3/F2, KEEP-optimistic].
102. Read-disturb-bounded refresh scheduling as a background program stream [L2/F0, KEEP].
103. Channel-BW relief via ONFI 4.8GB/s for high-batch input broadcast [L2/F0, KEEP].
104. Inverse-read free NOT for two's-complement negation [L2/F1, KEEP].

## Stage-A rejections (recorded, not simulated)
- 17, 27, 28, 41, 60, 61, 73: fail exactness / info-flow / capacity / economics as noted.
- All "analog assumed harmless" variants are routed to the NON-QUALIFYING branch
  unless paired with exact digital residue correction (Family 18).

## What survives to Gate 9D simulation
Families 1-16, 19-22 (composable). The optimizer combines: read mode (conv | cr-read
| MWS-assisted) x reducer (shift-add | failbit-count | export) x dataflow (token |
expert-stationary) x batch x organization x precision (native | fp8-NONQUALIFYING).
Result: `results/gate9_all_candidates.csv`, analyzed in `reports/07c`.
