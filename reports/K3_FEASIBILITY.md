# K3_FEASIBILITY.md — quantitative assessment

All numbers below are **analytical bounds** from datasheet-class parameters and the
user-supplied workload. **No device measurements were taken or invented.** Where a value
depends on the exact NAND/board, a generous bound is used and labeled.

## 1. Workload (user-supplied) and immediate physical gates

| Quantity | Value | Consequence |
|---|---|---|
| Total params | 2.78 T | At MXFP4 (~0.5 B/param) ⇒ **~1.4 TB** of weights (more with block scales). |
| Board NAND capacity (Cosmos+) | ~0.5–1 TB (2 SO-DIMM toggle modules) | **Capacity gate: the model does not fit on one board.** |
| Active params / token | 104 B (MoE) | ⇒ **~52 GB must be read per token** (only active experts, but still 52 GB). |
| Layers | 93, sequential | Autoregressive single-stream ⇒ **no batching to amortize**. |
| Format | MXFP4 (4-bit block float) | **Not binary.** In-NAND bitwise (if it existed) is binary; MXFP4 needs multi-bit. |

## 2. The bandwidth wall (dominates everything)

Cosmos+ NAND datapath is Toggle **DDR ~100–200 MT/s** per channel (`NFC_Toggle_Top_DDR100.v`,
`llnfc-ddr200mt`), ~8 channels. Aggregate sequential read bandwidth is therefore on the order
of **~1.5–3 GB/s** realistically; take an *optimistic* **10 GB/s** as a generous ceiling.

```
Per-token weight read  = 52 GB
Time/token @ 3 GB/s    = ~17 s      → 0.06 tok/s
Time/token @ 10 GB/s   = ~5.2 s     → 0.19 tok/s         (optimistic ceiling)
Target                 = 100–500 tok/s
Required read BW       = 52 GB × 100 … 500 = 5.2 … 26 TB/s
```

**The target needs ~1,000–10,000× the board's aggregate NAND read bandwidth** — above even
HBM-class memory. This gap is three to four orders of magnitude and is not closable by
firmware, RTL, or cleverness on this platform.

## 3. Does in-NAND compute remove the wall? No.

The appeal of in-flash compute is "don't move the weights." But:

- **The weights must still be *sensed*.** Flash-Cosmos-style multi-wordline sensing reduces
  *separate* reads when you bitwise-combine *many operands already stored in the array*; it
  does **not** raise the per-column sense throughput that gates a 52 GB/token weight stream.
  Sensing bandwidth is the same physical wall.
- **MXFP4 ≠ binary.** The only demonstrated in-NAND primitive family is *binary* bulk bitwise
  (AND/OR → XNOR/popcount). MXFP4 matmul requires 4-bit operands and shared block scales:
  either bit-plane decomposition (≈4 planes × shift-add, several× the operation count, each
  needing its own sense pass) or true analog MAC with an on-die ADC. The user's own caution
  applies: **do not treat a binary XNOR-popcount demo as MXFP4 inference.**
- **None of the in-NAND primitives are reachable anyway** (COMPUTE_CAPABILITIES #6–#14:
  NOT FOUND / REQUIRES SILICON).

## 4. Three architectures compared (analytical)

| Arch | Where compute happens | Available on these repos? | Token rate bound | Weights leave die? |
|---|---|---|---|---|
| **1. Normal reads → FPGA arithmetic** | FPGA fabric | **Yes** (reads verified; add popcount in RTL) | 0.06–0.19 tok/s (read-bound) | **Yes** (over ONFI bus) |
| **2. NAND Boolean → FPGA popcount** | Die (Boolean) + FPGA (count) | **No** — Boolean primitive NOT FOUND | ≤ arch 1 (still sense-bound) | Partially |
| **3. Fully in-die digital/analog current-sum** | Die | **No** — REQUIRES SILICON MODIFICATION; analog node not on any pin | N/A (not accessible) | No (if it existed) |

Only architecture **1** is buildable here, and it is ~500–8,000× short of target **and**
transfers weights out of the die — i.e. it does not satisfy the mission's own constraint.

## 5. The 93-layer sequential latency budget

At even 100 tok/s the per-token budget is 10 ms, ÷ 93 layers ≈ **107 µs/layer** to cover
activation delivery + sensing + partial-sum reduction + requantization + inter-layer movement
for ~10⁹-scale MACs/layer. On a platform whose single-page read latency is tens of µs and
whose aggregate sense bandwidth is ~GB/s, **meeting the per-layer budget is not plausible by
several orders of magnitude.**

## 6. Separation of bounds vs. measurement

- Everything above is an **analytical bound**. The audit produced **no** measured NAND
  timing, sense current, or error-rate data (none was run — static audit only).
- The capacity gate (§1) and bandwidth gate (§2) are robust to generous assumptions and do
  not depend on any unverified in-NAND behavior.
