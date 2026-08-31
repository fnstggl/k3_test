# Gate 9A — Physical NAND capability audit (from primary sources)

Machine-readable registry: `configs/nand_capabilities.yaml`. This report records
what each primary source ACTUALLY demonstrated, at the correct evidence level
(L1 measured-on-exact-target-family / L2 measured-on-other-3D-NAND / L3
proposed-or-simulated) and modification class (F0 commodity-firmware /
F1 existing-HW-needs-exposure / F2 tiny-periphery / F3 array-redesign). Papers
were read in full (extracts saved under `references/gate9/`).

## Headline: one source tested our EXACT part

MCFlash (arXiv:2605.05119, J.Supercomputing 2026) Table 2 lists
**`MT29F1T08EELEEJ4` (176-layer CT)** — the BABOL target family — among 50 tested
Micron chips. So user-mode read-offset (SET FEATURE read-retry) + Soft-Bit-Read
bitwise ops are **L1 on our exact part**. This is the strongest physical anchor in
the whole study — but the ops are 2-operand and give no reduction (below).

## Capability summary

| Capability | Op | Cross-bitline sum? | Runtime operand? | Evidence | Mod | Latency | Source |
|---|---|---|---|---|---|---|---|
| Ordinary read | sense 1 WL | no | no | L2 (L1-ish) | F0 | tR (SLC 22.5µs meas; 3µs Z-NAND) | Flash-Cosmos T1 |
| MCFlash read-offset | AND/OR/XNOR/NOT of 2 co-encoded operands | **no** | no (600µs program to stage) | **L1 (our part)** | F0 | 40–90µs | MCFlash §4.2 |
| Intra-block MWS | AND of ≤48 WLs (NAND w/ inverse) | **no** (per-bitline) | no | L2 | F1 (vendor test-mode) | +3.3% tR @48 WL | Flash-Cosmos §4.1 |
| Inter-block MWS | OR of ≤32 blocks | no | no | L2 | F1 | +36% tR @32blk; ≤4blk +3.3% | Flash-Cosmos §5.2 |
| Latch XOR | 2-op XOR in latches | no | maybe (uncharacterized) | L2 | F1 | ~1 sense | Flash-Cosmos §6.1 |
| ParaBit location-free | latch-chained bitwise, same bitline | no | no | L3 (ops simulated) | F2 (per-BL inverter ~1.2% die) | ~25µs/sense | ParaBit §4.2 |
| ESP SLC programming | zero-error compute reads | — | — | L2 | F0 (SET FEATURE) | tPROG ×1.9 | Flash-Cosmos §4.2 |
| cr-read (AiF) | recycle charge, consecutive WLs | — | — | L2–L3 | F1 (minor control) | see §cr-read | AiF ISCA'25 |
| Program-verify fail-bit count | popcount across bitlines | **YES (if exposed)** | no | **L3** | F1/F2 | HYPOTHESIS | generic PV; no public cmd |
| Source-line current sum | analog popcount | yes (analog) | via ref-V | L3 | F3 | HYPOTHESIS, non-exact | analog-flash class |

## The decisive structural fact

Every MEASURED commodity/near-commodity capability (MCFlash, Flash-Cosmos MWS,
ParaBit) produces **per-bitline Boolean results** — AND/OR/XOR of operands that
lie on the same bitline/string. **None sums across bitlines.** The exact K3 dot
product, via the proven decomposition, needs exactly one cross-lane primitive: a
**popcount across bitlines**. The only mechanisms that could provide it —
an exposed maskable program-verify fail-bit counter, or source-line current
summation — are **L3 (undocumented / non-exact)**. This is Gate 4's structural
conclusion, now confirmed against the full primary literature: **firmware-only
exact K3 GEMV is falsified because the cross-bitline sum does not exist in any
demonstrated commodity NAND behavior.**

MWS's headline (48 operands, +3.3% tR) is real and powerful for BULK BITWISE
(databases, bitmap indices) where the wanted result IS an AND/OR of 48 bitmaps.
For GEMV the reduction is ADDITION, so MWS contributes **0 exact GEMV MACs** — it
can only form the per-bitline product bits, which a plain sense already provides.

## cr-read (AiF) — the one genuinely useful physical lever

AiF's charge-recycling read makes CONSECUTIVE same-block WL reads cheaper by
reusing WL/BL charge (skip full precharge/discharge). K3 weight streaming is
exactly consecutive contiguous page reads, so cr-read applies to both the dense
pool and each expert's contiguous pages. Claimed anchors (verification in
`references/gate9/`; treated as L2–L3, F1 "minor flash-control change" — NOT
commodity-commandable on our part until BABOL): ~2.8× effective read bandwidth,
~72% read-energy reduction, conditional on chain length and same-block locality.
Gate 9D models it with optimistic/central/adversarial recycling multipliers
(1/2.8 … 1/1.6) and a chain-length penalty at expert boundaries. It is the single
biggest physically-grounded improvement over the frozen Gate-6 baseline.

## Evidence-level discipline applied downstream

- Anything the Gate 9D search builds on cr-read is capped at **L3 for our part**
  (no measurement on MT29F1T08EELEEJ4) and flagged as an unverified primitive.
- MWS/ParaBit require **vendor test-mode/command exposure (F1)** — not firmware-
  only — despite being measured on other 3D NAND.
- The exposed fail-bit count and analog SL-sum are **L3 HYPOTHESIS**; the search
  reports what they WOULD deliver and BABOL_TEST_SPEC turns them into physical
  tests, but no result depends on assuming they exist.

## Corroborated operating-point anchors (usable as MODEL/FACT inputs)

- SLC-mode tR = **22.5 µs** on 48-layer 3D TLC (Flash-Cosmos, measured) — a real
  anchor for the SLC-mode-on-TLC frontier (previously a MODEL guess).
- ESP zero-error SLC programming costs **≥1.9× tPROG** and **2× capacity** (SLC).
- Inter-block sensing power: **+34% @2 blocks, +80% @4 blocks**, cap at 4 blocks —
  a hard limit against aggressive multi-block fan-in.
- MCFlash: error-free 2-operand bitwise at **40–90 µs, RBER 0 fresh** on our exact
  part — the foundation BABOL E2 builds on.
