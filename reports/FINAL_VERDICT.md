# FINAL_VERDICT.md

Audit of Cosmos+ OpenSSD (`7860148`) and CRZ OpenSSD-OpenChannelSSD (`29f49e5`,
`CosmosPlus/2025.1/Micron_NAND`). Static source only; no hardware touched.

## Direct answers

**1. Does the existing source expose enough operations for a true in-NAND binary dot product
(XNOR + popcount inside the die)?**
**No.** The controllers emit only the standard ONFI/Toggle command set
(`{00,05,10,11,27,30,32,60,70,78,80,85,D0,E0,EE,EF,FF}`, COMMAND_MAP §3–4). There is no
latch-Boolean, no in-die count, and no multi-wordline *sensing* command or datapath
(COMPUTE_CAPABILITIES #6–#10, all NOT FOUND). The only XOR/count logic in-tree is the FPGA's
BCH/CRC — out of die.

**2. Enough for analog current-summed matrix multiplication?**
**No, and not reachable in principle on commodity packaged NAND.** The summed analog node and
sense-amp outputs are internal to the die and routed to no package pin; NAND returns digitized
page data only. The board's sole ADC is the Zynq XADC chip monitor (wrong side of the bus).
This is **REQUIRES SILICON MODIFICATION** (COMPUTE_CAPABILITIES #12–#13).

**3. If not, what exactly is missing?**
Three things, in increasing hopelessness: (a) a command to **hold an activation in a latch
without programming** (#6); (b) **latch-level Boolean / in-die count** (#8–#9); (c) **access to
analog sense/current-sum** (#10–#13). (a)/(b) need undocumented vendor/test-mode commands plus
die support; (c) needs a modified NAND test chip. None are producible by any external
controller, open or not.

**4. Could a small commodity FPGA replace Cosmos+ for testing?**
**For the reachable experiments, yes.** The only physically-exposed lever — shifted-Vref
sensing via `Set Feature (EFh)` — plus normal/raw/multi-plane reads can be driven by any FPGA
(or dev board) wired to a single NAND package's Toggle/ONFI bus; you do **not** need Cosmos+ to
test G1–G2/G6 (HARDWARE_GATES). Cosmos+ only saves you the NAND-PHY bring-up. For the *in-die
compute* questions (G3–G5), **no** FPGA helps, because the gap is in the silicon, not the host.

**5. Which exact NAND to investigate first?**
The **Micron 3D TLC part targeted by CRZ `CosmosPlus/2025.1/Micron_NAND`** — because (i) an
open, working controller + PHY already exists for it, and (ii) its **read-retry feature-address
table** (the G1 datasheet question) is the single cheapest piece of evidence that gates the
only reachable analog-ish path. Confirm the exact part number from the board's NAND module /
`NPCG_Toggle_MNC_readID.v` expected-ID and get that datasheet first.

**6. Is purchasing hardware justified yet?**
**No — not for the K3 objective, and not yet for the research question.** Spend $0 first:
(a) pull the Micron datasheet and confirm read-retry/feature addresses (G1); (b) accept the
capacity + bandwidth math (K3_FEASIBILITY §1–§2), which kills the *K3-on-a-board* goal by
3–4 orders of magnitude independent of any in-NAND trick. Only if the datasheet shows rich
read-level control **and** you redefine the goal to a tiny demonstrator model does a board
purchase become justified — and then a single NAND + commodity FPGA, not necessarily Cosmos+.

**7. The single most efficient experiment to determine physical feasibility:**
**Shifted-Vref read characterization on the exact Micron part (G2).** Program known data;
sweep the read-reference level via `EFh` Set Feature (the `setFT` SM already issues it); record
how returned bits move with the shift. This one cheap, no-new-silicon test tells you whether
the die yields *any* exploitable multi-level/analog signal — the hinge the whole analog path
turns on. If it yields nothing usable, the in-NAND-MAC approach is dead on this part and no
purchase is warranted.

## Go / No-Go

- **In-NAND MatMul (binary or analog) without moving weights off-die, on commodity NAND via
  these open controllers: NO-GO.** The primitives are absent from source and, for the physical
  ones, absent from reach (silicon/NDA gates).
- **Near-storage compute (read weights → XNOR/popcount in the FPGA): buildable**, but it moves
  weights out of the die (violating the mission constraint) and is ~500–8,000× short of the K3
  throughput target. Fine as an SSD/accelerator learning project; not a path to K3.
- **K3-class inference on this hardware: NO-GO by capacity and bandwidth alone**, before any
  compute question.

## Adversarial review (trying to falsify the strongest claim)

Strongest claim to attack: *"These repos cannot do an in-NAND dot product."*

- *Could a command exist that the RTL doesn't name but the NAND still honors?* The audit proves
  absence **in the controller**, not in the silicon ("NOT FOUND ≠ proven absent"). A
  vendor/test-mode sequence could exist in the die. **But** reaching it needs the controller to
  *emit* it, which means adding an RTL state machine with the exact undocumented bytes/bias —
  i.e. you must already possess the vendor spec (G4), which is the gated unknown. So the claim
  stands for "via the released source," and weakens only to "undocumented and unreachable
  without vendor silicon docs."
- *Could multi-plane (`32h`) be repurposed as multi-operand compute?* No — multi-plane reads
  **separate** bitlines into **separate** buffers; nothing combines them in the array. Combining
  happens only in the FPGA (out of die).
- *Could shifted-Vref sensing (the one reachable lever) deliver analog MAC?* Possibly a weak
  multi-level signal (that's exactly experiment G2), but it is per-page sensing — it does not
  break the sense-**bandwidth** wall and does not by itself yield MXFP4 MACs. Even a positive G2
  does not flip the K3 verdict, because capacity+bandwidth fail independently.

What evidence would change the recommendation: a public/NDA Micron doc exposing a
latch-Boolean or multi-WL-sense command for the exact part **and** a redefinition of the target
to a model that fits the board's capacity and whose per-token weight read fits its ~GB/s
bandwidth. Absent both, the recommendation is stable: **do not buy hardware for the K3 goal;
spend $0 on the datasheet and the bandwidth math first.**
