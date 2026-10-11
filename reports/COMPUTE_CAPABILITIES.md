# COMPUTE_CAPABILITIES.md — evidence-classified physical primitives

Commits as in COMMAND_MAP.md (Cosmos+ `7860148`, CRZ `29f49e5`). Evidence levels:
**VERIFIED IN SOURCE** · **IMPLEMENTABLE IN CONTROLLER** (FPGA/fw can generate the
signals, NAND response unverified) · **SILICON SUPPORT UNKNOWN** · **REQUIRES SILICON
MODIFICATION** · **NOT FOUND**. "Not found" ≠ "proven absent in silicon."

Overriding rule applied throughout: a primitive counts as *in-NAND* only if the operation
happens inside the die. If it happens in the FPGA (ECC, scramble, arithmetic), it is marked
as such — because that moves weights **out** of the die, which defeats the stated objective.

| # | Required primitive | Level | Evidence / why |
|---|---|---|---|
| 1 | **Read a stored page** (weights out) | **VERIFIED IN SOURCE** | `00h/30h` read SM; `05h/E0h` random-out. `nsc_driver.c:98,110`. |
| 2 | **Raw read, ECC+scramble bypassed** | **VERIFIED IN SOURCE** | `V2FCommand_ReadPageTransferRaw=55`, `nsc_driver.c:119`. ECC (BCH) and scramble (`LFSR8`) live in `tiger4_nfc_substrate` (FPGA), so they can be skipped — but this reads *stored bits*, it is not compute. |
| 3 | **Multi-plane parallel read/program** | **VERIFIED IN SOURCE** (CRZ) | `32h` multi-plane read `read_AW30h.v:302`; `11h` program; `78h` enh. status. Parallel **independent** pages — bandwidth, not operand combination. |
| 4 | **Set/Get Features** (feature-register ops) | **VERIFIED IN SOURCE** | `EFh/EEh`, `setFT.v:329`/`getFT.v:325`, `nsc_driver.c:74,85`. This is the hook for #5. |
| 5 | **Read-retry / calibrated (shifted-Vref) sensing** | **IMPLEMENTABLE IN CONTROLLER** → **SILICON SUPPORT per datasheet** | No `read-retry` code exists, but it is just a `Set Feature (EFh)` to the NAND's read-level feature address, which the `setFT` SM can already issue. The *specific* feature addresses are Micron-part-specific and **NOT FOUND** in these repos (they live in the NAND datasheet). This is the one analog-adjacent lever that is actually reachable. |
| 6 | **Load an activation into a page-buffer latch without programming cells** | **NOT FOUND** → **REQUIRES SILICON / UNDOCUMENTED CMD** | No command loads the data latch except as the first half of a *program* (`80h`+data), which targets cells. Holding data in a latch for repeated compute is a test-mode/vendor behavior; no command exists and standard NAND does not expose it. |
| 7 | **Preserve that activation across many weight reads** | **NOT FOUND** | Depends on #6; moot. A normal read overwrites the page buffer. |
| 8 | **Latch↔latch XOR/XNOR/AND/OR inside the die** | **NOT FOUND** → **REQUIRES SILICON MODIFICATION or UNDOCUMENTED NAND CMD** | No Boolean command byte or datapath anywhere. The only XOR in-tree is the **BCH/CRC LFSR** in the FPGA (`CRC_serial_m_lfs_XOR.v`, `d_SC_*_lfs_XOR.v`) — FPGA error-coding math, explicitly **not** in-NAND. |
| 9 | **Internal fail-bit count / BitScan / popcount** | **NOT FOUND** | No count command/engine. Popcount, if done, happens in FPGA logic you would add (see K3_FEASIBILITY arch #2) — out of die. |
| 10 | **Simultaneous multi-wordline *sensing* (operand AND/OR on shared bitline)** | **NOT FOUND** → **REQUIRES SILICON / UNDOCUMENTED CMD** | This is the Flash-Cosmos mechanism. `32h` is multi-*plane* (separate bitlines), **not** multi-*wordline onto one bitline*. No command drives multiple WLs into one sense. |
| 11 | **Independent bitline-select / string-select group control** | **NOT FOUND** → **REQUIRES SILICON** | SSL/BSL biasing is internal to the die; no package-level command exposes per-string selection beyond normal addressing. |
| 12 | **Sum currents from multiple blocks at a shared sense node** | **NOT FOUND** → **REQUIRES SILICON MODIFICATION** | Analog current summation is a *physical* operation inside the array; it is not addressable by any command and the summed node is not routed to any package pin. |
| 13 | **Access internal analog sense / comparator / ADC outputs** | **NOT FOUND** → **REQUIRES SILICON MODIFICATION** | NAND returns *digitized* page data only. The sense-amp analog value never leaves the die. (The board's only ADC is the Zynq XADC chip monitor — wrong side of the bus, measures FPGA supply/temp.) |
| 14 | **Repeat compute without erase/program** | **NOT FOUND** | Depends on #6/#8; moot. |
| 15 | **Many dies/planes concurrent** | **VERIFIED IN SOURCE** | Multi-channel/way controller + multi-plane. Legitimate parallelism for bandwidth. |

## Bottom line of the capability audit

- **Everything required to read stored weights fast and flexibly is present and verified**
  (1–5, 15): including raw/ECC-off reads, multi-plane, and the Set-Feature hook for
  read-level shifting.
- **Everything required to compute *inside the die* (6–14) is NOT FOUND**, and the physical
  ones (8, 10, 12, 13) **require silicon modification or undocumented/vendor NAND commands**
  that no external controller — open or not — can conjure. The controller owns the bus; it
  does not own the die's internal micro-operations.
- **Every arithmetic/Boolean element that *does* exist in these repos is FPGA-side**
  (BCH/CRC XOR trees, scrambler). Using them means the weights have already crossed the
  ONFI/Toggle bus out of the die — which is exactly what the objective says to avoid.
