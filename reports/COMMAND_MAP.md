# COMMAND_MAP.md — C → register → RTL → NAND bus, for the OpenSSD controllers

**Audited sources (exact commits):**
- Cosmos+ OpenSSD — `github.com/Cosmos-OpenSSD/Cosmos-plus-OpenSSD` @ **`78601486bb5581e40628ec7e841dea8e97eff034`** (2022-07-29)
- CRZ OpenSSD-OpenChannelSSD — `github.com/CRZ-Technology/OpenSSD-OpenChannelSSD` @ **`29f49e53c012ec7b2094686976374782858b52fd`** (2026-09-30); audited path `CosmosPlus/2025.1/Micron_NAND/` (Vivado 2025.1, Micron NAND target, same `v2nfc` IP lineage).

Method: static read only. No hardware, no build, no execution. Generated Xilinx IP
(`pcie_7x_0_core_top_funcsim.v`, `zynq_fsbl_bsp/…`) excluded from command analysis.

---

## 1. The two namespaces (keep them separate)

The user's critical distinction, confirmed in source:

| Layer | What it is | Example |
|---|---|---|
| **Controller command ID** | An integer the ARM firmware writes to a memory-mapped register to select an NFC state machine. **Not a NAND byte.** | `V2FCommand_ProgramPage = 28` |
| **Raw NAND bus byte** | The 8-bit value the RTL drives onto the NAND command latch (CLE) | `8'h80` (program setup) |

## 2. Firmware → register (the C side)

`source/software/GreedyFTL-3.0.0/nsc_driver.h` defines the controller command IDs, and
`nsc_driver.c` issues them by writing the `cmdSelect` register of the NAND storage
controller (`V2FMCRegisters*`):

```
nsc_driver.h:60-69   #define V2FCommand_NOP                  0
                     #define V2FCommand_Reset                1
                     #define V2FCommand_SetFeatures          6
                     #define V2FCommand_GetFeatures          46
                     #define V2FCommand_ReadPageTrigger      13
                     #define V2FCommand_ReadPageTransfer     18
                     #define V2FCommand_ProgramPage          28
                     #define V2FCommand_BlockErase           37
                     #define V2FCommand_StatusCheck          41
                     #define V2FCommand_ReadPageTransferRaw  55
nsc_driver.c:62      *((volatile unsigned int*)&(dev->cmdSelect)) = V2FCommand_Reset;      // etc.
```

`dev` is a `V2FMCRegisters*` mapped at a channel base from `memory_map.h`. So the full
host path is: **NVMe cmd → FTL (`request_*.c`) → `nsc_driver.c` → `dev->cmdSelect` write →
Tiger4 NFC → low-level NFC state machine → NAND pins.**

## 3. Register → RTL → exact NAND bytes (the hardware side)

Low-level NFC = `source/hardware/low-level-nfc/llnfc-ddr200mt-1.0.0/` (Toggle-mode DDR).
Each controller command maps to one state machine that drives `rCAData`/`rPM_CAData` onto
the command latch. **Exact bytes, with file:line (Cosmos+ commit above):**

| Controller cmd (ID) | NAND operation | Raw bytes | RTL evidence |
|---|---|---|---|
| ReadPageTrigger (13) | Page read, setup+confirm | `00h` … `30h` | `NPCG_Toggle_BNC_P_read_AW30h.v:230,242` |
| ReadPageTransfer (18) | Random-out within page (+ECC/descramble) | `05h` … `E0h` | `NPCG_Toggle_BNC_P_read_DT00h.v:261,267` |
| ReadPageTransferRaw (55) | Same, **ECC + descramble bypassed** | `05h`…`E0h` (raw datapath) | `nsc_driver.c:119`; raw vs. corrected datapath in `tiger4_nfc_substrate` |
| ProgramPage (28) | Page program, setup+confirm | `80h` … `10h` | `NPCG_Toggle_BNC_P_program.v:275,287` |
| BlockErase (37) | Block erase, setup+confirm | `60h` … `D0h` | `NPCG_Toggle_BNC_B_erase.v:221,229` |
| StatusCheck (41) | Read status | `70h` | `NPCG_Toggle_MNC_readST.v:318` |
| SetFeatures (6) | Set features | `EFh` | `NPCG_Toggle_MNC_setFT.v:329` |
| GetFeatures (46) | Get features | `EEh` | `NPCG_Toggle_MNC_getFT.v:325` |
| Reset (1) | Reset | `FFh` | `NPCG_Toggle_MNC_N_init.v` |

**The complete set of NAND command bytes the Cosmos+ RTL can emit is**
`{00,05,10,30,60,70,80,D0,E0,EE,EF,FF}` (verified by exhaustive grep of
`rCAData`/`rPM_CAData` assignments in `low-level-nfc/`). That is the **standard
ONFI/Toggle command set** — nothing else.

## 4. CRZ 2025.1 Micron variant — same architecture, adds multi-plane

Path: `CosmosPlus/2025.1/Micron_NAND/cosm-plus-sys.ipdefs/ip-repo_0/v2nfc/src/`.
Same `NPCG_Toggle_*` state-machine family. Command bytes emitted (unique, grepped):
`{00,05,10,11,27,30,32,60,70,78,80,85,D0,E0,EE,EF,FF}` plus status variants `71h/73h`.
Deltas vs. Cosmos+ 2022, all still **standard array operations**:

| Byte | Meaning | Evidence |
|---|---|---|
| `32h` | **Multi-plane** page read confirm (`rMultiPlane?32h:30h`) | `NPCG_Toggle_BNC_P_read_AW30h.v:302` |
| `11h` | **Multi-plane** program (dummy/continue) | `NPCG_Toggle_BNC_P_program.v` |
| `85h` | Change-row / random data-in during program | `NPCG_Toggle_BNC_P_program.v` |
| `27h`,`FAh` | Micron erase preset / multi-plane-suspend erase | `NPCG_Toggle_BNC_B_erase.v:247,~`; `rMultiplaneSuspend` at `:111,182,192` |
| `78h` | Read Status Enhanced (per-LUN/plane) | `NPCG_Toggle_MNC_readST.v` |

Multi-plane (`32h`/`11h`/`78h`) gives **plane-level parallelism** — reading/porgramming N
independent planes at once (bandwidth). It is **not** multi-wordline *sensing* and does not
combine operands; see COMPUTE_CAPABILITIES.md.

## 5. What is NOT in either command map

Exhaustive grep across both repos' custom source (`.v/.vh/.c/.h`, generated IP excluded)
for `xnor|popcount|bitscan|multi.?wordline|current.?sum|sense.?amp|analog|read.?retry|
dot.?prod|matmul|in.?flash.?comp`: **no compute command, state machine, or datapath found.**
The only `ADC`/`analog` hits are the Xilinx **Zynq XADC** system monitor (chip
supply/temperature), e.g. `…/zynq_fsbl_bsp/…/xadcps.h` — unrelated to NAND sensing.
