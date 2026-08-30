# LLM-on-the-Palm — extraction notes and discrepancies

Companion to `llm_on_the_palm_parameters.yaml`. Paper: ICCAD 2025,
DOI 10.1109/ICCAD66269.2025.11240826 (local: `references/LLM-on-the-Palm.pdf`).
Page numbers refer to the 15-page IEEE Xplore PDF (paper body = pp. 1–8 of content).

## Where the key numbers live
| Item | Location |
|---|---|
| ~100ms/token goal, 1 MAC/plane, 256 MACs/256GB | Abstract; Sec I |
| TPOT 100–120ms (6.7B), 155/356ms for 13B/30B w/ pruning | Sec I (p.2) |
| Flash-PIM architecture, PU beside column decoder, FP16 mul + FP32 add, demux/mux | Sec III-A, Fig 4 |
| 400MHz MAC, 3µs tR window, 1024 weights/page, 2.5µs MAC, 0.6ns/2B input, 1B reg, 4B out, 35ns | Sec III-B, Fig 5 (p.3) |
| 117 GB/s aggregate internal BW | Sec III-B (p.4, "117GB/s for our configuration"); Sec VI-B |
| ONFI opcode 36h, CE#-based multi-die input broadcast | Sec III-C (p.4) |
| Prefill→NPU, FC→Flash-PIM, QxK/SxV→NPU, long-ctx QxK→Flash-PIM | Sec IV-A/B, Fig 1(b), Fig 9 |
| 2KB cell row, 1024× row-utilization drop for SxV writes | Sec IV-B, Fig 7(c) (p.5) |
| Table I system config | p.5 |
| MQSim + DRAMSim + Micron power calc + 28nm Synopsys DC | Sec V-A (p.6) |
| TPOT results Fig 10; LLM-in-a-flash combo Fig 11 | p.6 |
| TTFT Fig 12; long-seq Fig 13 | p.7 |
| Area Fig 14 (0.05% vs 2.3%) | Sec V-E, p.7 |
| Energy Fig 15 + splits | Sec V-F, p.7 |
| Capacity/type/DRAM/NPU sensitivity Fig 16 | Sec V-G, p.8 |
| SLC/no-ECC justification | Sec VI-A (p.8) |
| ISP comparison (4.3×) | Sec VI-B (p.8) |

## Discrepancies / ambiguities found (do NOT silently resolve)
1. **Table I capacity typo**: Table I prints "SSD capacity = 56GB"; all body text,
   Fig 16a, and 32×8GB dies say **256GB**. Treated as 256GB (recorded as paper typo).
2. **117 GB/s vs theoretical 174.8 GB/s**: 256 planes × 2KB/3µs = 174.8 GB/s. The paper's
   "effective" 117 GB/s implies ≈4.48µs per page window. The loss mechanism is not spelled
   out (likely channel command/broadcast serialization modeled in MQSim). Gate 2 derives
   this rather than hardcoding; capacity-sweep TPOTs (Fig 16a) imply
   period ≈ tR + ~0.4µs×dies_per_channel (2→3.76µs, 4→4.55µs, 8→6.1µs, 16→9.1µs implied).
3. **"GPT-3 30B" doesn't exist** in Brown et al.; Fig 8 labels say OPT 6.7B/13B/30B.
   GPT-3 13B hidden=5140 (odd size, 40 layers) per Brown et al. Table 2.1. We use
   GPT-3 6.7B geometry (4096/32L) as primary calibration target; 13B/30B as secondary.
4. **M-NAND tR unspecified**: Fig 16(b) M-NAND is refs [9]/[16] (280-layer 1Tb 4b/cell,
   SK hynix ISSCC'24); the paper never states its tR, page size, or plane count, nor
   whether capacity/organization was held constant. The 4.6× Z-NAND advantage cannot be
   reproduced without assumptions → treated as sensitivity check only.
5. **Energy bar values** read from Fig 15 rendering (1.5/2.8/6.6 J ours) are consistent
   with stated 8.3×/4.5× reductions only approximately (7.1–7.4× computed); bar-label
   digits may be misread or reductions are geomeans incl. other configs. Flagged.
6. **Embedding/unembedding layers**: paper never says where token embedding / LM head
   run. FC GEMV on Flash-PIM presumably covers LM head (weight-activation), but not stated.
   Gate 2 treats "include LM head in Flash-PIM bytes" as a switch.
7. **Attention time vs context**: Fig 10 deltas (6.7B: 105→114ms for ctx 128→1024)
   are consistent with KV-cache streaming at DRAM-class bandwidth (~9ms per +896 ctx
   at 32 layers, h=4096, FP16 ≈ 537MB per 1024 ctx). Used as cross-check, not input.

## Reverse-engineering targets for Gate 2 (acceptance: within 10%)
- TPOT(6.7B, in128/out128) = 105 ms; avg = 112 ms.
- Effective internal BW ≈ 117 GB/s.
- Capacity scaling 185/112/75/56 ms at 128/256/512/1024 planes (6.7B).
- 13B avg 215 ms, 30B avg 495 ms (needs 13B/30B geometry assumptions → range).
