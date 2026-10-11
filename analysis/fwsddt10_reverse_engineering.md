# Static reverse‑engineering of `fwsddt10.exe` (Lenovo SSD Firmware Update Tool)

**Scope:** static, offline analysis only. No firmware was flashed, no NVMe command was
issued to hardware, no drive was modified. All conclusions are derived from the bytes of
the executable and the files embedded in it.

**Analyst target:** WD PC SN740 `SDDQMQD-1T00-1201`, PCI `15b7:5016`, vendor‑specific
admin opcodes reported by the drive's Command Effects Log
(`0xE2 0xE4 0xE5 0xE6 0xE9 0xEA 0xF1 0xFA`, I/O `0x80`).

---

## 0. TL;DR — highest‑priority answers first

1. **What does admin opcode `0xEA` do on this SN740?**
   **Cannot be answered from this package.** `0xEA` does not appear anywhere in any of the
   three executables (0 occurrences, in any form — immediate, byte compare, or data). This
   is a *field firmware updater*, not a diagnostic/manufacturing tool, and it never
   constructs `0xEA`. The grammar for `0xEA` is implemented **controller‑side** (in the
   SN740 firmware) and is simply not exercised by this host tool.

2. **Which of the drive's vendor opcodes does this tool actually use?**
   Exactly **one**: **`0xE2`**, and only inside the **Intel RST/RSTe disk‑enumeration**
   path (labelled *"adapter info"*). The remaining opcodes you listed
   (`0xEA 0xE9 0xE4 0xE5 0xE6 0xF1 0xFA`, I/O `0x80`) are **not present** as command
   opcodes anywhere in the package. (`0xE4`/`0xE9` occur only as unrelated `cmp`/stack
   constants; `0xE5 0xE6 0xEA 0xF1 0xFA` do not occur at all.)

3. **Does firmware update use standard NVMe or vendor opcodes?**
   **100% standard NVMe.** The update path is
   **Identify (0x06) → Firmware Image Download (0x11) → Firmware Commit/Activate (0x10)**,
   with slot selection and deferred‑vs‑immediate activation. No vendor opcode participates
   in the actual flash.

4. **Any NAND / channel / die / LUN / block / page / wordline / Vref / read‑retry /
   ECC‑bypass / raw‑flash / test‑mode / factory / RMA / authenticated‑debug path?**
   **None found.** Every scary‑looking string in the binary is benign on inspection
   (`Threshold` = *temperature* SMART threshold; `block` = firmware *download chunk*;
   `sense`/`lun` = SCSI; `debug`/`auth`/`challenge`/`unlock` = EULA legal text). See §8.

5. **Authentication / unlock?**
   A SanDisk/WD **VSC "send‑key" enable handshake** exists (`ac`/`fc` grammar), but it is
   wired **only for ATA and SAS/SCSI** transports (`_vsc4/_vsc5_ata/_vsc5_scsi_execute_send_key`;
   **no NVMe variant**). Your NVMe SN740 is never taken through it by this tool. See §9.

Confidence legend used throughout: **[CONFIRMED]** = directly read from bytes/disassembly;
**[LIKELY]** = strong inference from consistent evidence; **[SPECULATIVE]** = plausible but
not proven here.

---

## 1. File inventory, provenance & signatures

### 1.1 Outer file — `fwsddt10.exe`

| Property | Value |
|---|---|
| SHA‑256 | `7a87340dca9c0964b4ede0960065af7e0e6cb30a0d693a2e34f2115c39dacd43` |
| SHA‑1 | `612d4fa3f3e9d37d85e4819d82851bc30353fc76` |
| MD5 | `95ed4a9d15fc7ade0a435458f99620fb` |
| Size | 4,102,960 bytes |
| Type | PE32 (x86, GUI), 10 sections, Delphi/Inno stub |
| PE TimeDateStamp | 2020‑01‑06 06:31:46 UTC |
| **Packaging** | **Inno Setup 5.5.7 (Unicode)** — overlay `zlb\x1a` @ file 0x2C000; marker "Inno Setup Setup Data (5.5.7) (u)"; 95.6% of the file is the compressed installer overlay |
| **Code signature** | **Authenticode, signed "Lenovo"** — DigiCert *Trusted G4 Code Signing RSA4096 SHA384 2021 CA1*; RFC‑3161 timestamp via DigiCert 2022. **[CONFIRMED]** provenance is genuine Lenovo. |

### 1.2 Embedded payload (extracted with `innoextract`)

| File | Size | SHA‑256 | Role |
|---|---|---|---|
| `fwwinsd.exe` | 420,944 | `91876b316c967d1f75f2832495eb512f2b8bada700fca76a1805eebcda951d6e` | Lenovo MFC GUI **detector + launcher** |
| `WDC/sanupdater-3.12.1-win32.exe` | 378,520 | `8e4f4f79f489691a8334418406deedcbe628ef9a6a7e6dd91c34bcb20adb9726` | **SanDisk/WD worker** — issues the device commands |
| `WDC/73110101.fluf` | 2,822,144 | `f90d020567291f0d951aa34c5e7a8558bb988bde724552cfda01153ddb94aea9` | **Firmware image** (FLUF Format 002, encrypted) |
| `FWWINSD.PRO` | 1,484 | `1434359df218d98f42423e3f519fb6d5fee2a87f05322c25e2570670b8bc1051` | Model→firmware compatibility table (CSV) |
| `README.txt` | 7,496 | `761c88e60805d62c624bb6fdeb0aa6a7d113d5e8ed808145a93eaa02901ad80d` | User instructions |

No other executables, DLLs, drivers, certificates‑as‑files, or archives are embedded.
`sanupdater` has a tiny 6,808‑byte overlay; `fwwinsd` a 13,392‑byte overlay — both are
Authenticode certificate tables, not hidden payloads.

### 1.3 Compatibility table — `FWWINSD.PRO`

CSV columns: `model, (blank), targetFW, image, updaterExe, (blank), flag, vendor`.
Your drive's row:

```
"WD PC SN740 SDDQMQD-1T00-1201","","73110101","73110101.fluf","sanupdater-3.12.1-win32.exe","","S","WDC"
```

**Note:** the target firmware in this package is **`73110101`**, which is *older* than the
`73117101` currently on your drive (and older than the `73116101` alternate slot). This
specific package would therefore detect your drive as *not requiring an update* and would
not re‑flash it. The command‑construction code, however, is fully present and is what this
report analyses.

---

## 2. Architecture & data flow  **[CONFIRMED]**

```
fwsddt10.exe  (Inno Setup 5.5.7 self‑extractor, Lenovo‑signed)
   └─ extracts to a temp dir, runs ──► fwwinsd.exe   (Lenovo MFC GUI, requireAdministrator)
                                          │  • enumerates drives (SetupDi + \\.\ScsiN:/PhysicalDrive)
                                          │  • reads NVMe Identify (model, fw rev) via
                                          │    IOCTL_STORAGE_QUERY_PROPERTY / IOCTL_SCSI_MINIPORT
                                          │  • matches model+rev against FWWINSD.PRO
                                          │  • CFWWinDlg::runUpdater → CreateProcessA
                                          ▼
                              sanupdater-3.12.1-win32.exe  "/S:<args>"   (SanDisk/WD worker)
                                          │  • re‑opens the device, re‑reads Identify
                                          │  • streams 73110101.fluf via NVMe FW Download (0x11)
                                          │  • Commit/Activate (0x10), picks safe slot
                                          ▼
                                     WD PC SN740 controller  (validates + installs image)
```

`fwwinsd` never writes firmware; `sanupdater` does. The README states this explicitly:
*"This utility contains several executable files. DO NOT RUN THESE PROGRAMS except
FWWINSD.EXE. Running these programs other than FWWINSD.EXE could ruin your Solid State
Drive."*

Internal SDK identity of `sanupdater` (from build paths): SanDisk **"yupd"** updater SDK
`1.12.1`, modules `yadl` (device abstraction layer), `yextnvme`, `yextata`, `yextvuc`
(vendor unique command), `yextfirmware`. Build root
`C:\jenks2\win32\workspace\yworkspace_yupd-release_1.12.1\`. It is OEM‑generic (also
contains Dell component‑ID matching).

---

## 3. `sanupdater` — transports & device I/O  **[CONFIRMED]**

Imports of interest: `KERNEL32!DeviceIoControl`, `CreateFileA/W`, `ReadFile/WriteFile`;
`SETUPAPI` device enumeration (`SetupDiGetClassDevsA`, `CM_Get_Parent`, …). All drive
communication is via `DeviceIoControl` (45 call sites, all in the `yadl` layer,
0x410000–0x41B600).

IOCTL control codes present in code:

| IOCTL | Value | # refs | Used for |
|---|---|---|---|
| `IOCTL_SCSI_MINIPORT` | `0x0004D008` | 23 | WD/HGST NVMe driver passthru (SRB_IO_CONTROL) & SCSI |
| `IOCTL_STORAGE_QUERY_PROPERTY` | `0x002D1400` | 4 | protocol/device property (Identify data) |
| `IOCTL_STORAGE_PROTOCOL_COMMAND` | `0x002DD3C0` | 1 | Windows in‑box NVMe driver passthru |
| `IOCTL_SCSI_PASS_THROUGH` | `0x0004D004` | 1 | ATA/SCSI transport |

Driver back‑ends are auto‑detected (trace strings): `WINDOWS_INBOX_NVME`,
`WD/HGST NVMe driver` (`WINDOWS_NVME_WD_IUO`), `WINDOWS_NVME_INTEL_RST`,
`WINDOWS_NVME_INTEL_RSTE`.

### 3.1 The WD NVMe passthru structure  **[CONFIRMED]**

`sanupdater` contains a debug dumper that prints the exact structure it builds, field by
field (`.rdata` @ ~0x44C1CC):

```
passthru->srb_io_ctrl.HeaderLength / ControlCode / Length / Timeout   ← SRB_IO_CONTROL
passthru->version / path_id / target_id / lun
passthru->cmd.dw0  … dw15                                             ← raw NVMe command
```

`cmd.dw0[7:0]` is the NVMe opcode; `dw1` = NSID; `dw10…dw15` = CDW10…CDW15. This is the
classic `IOCTL_SCSI_MINIPORT` + `SRB_IO_CONTROL` vendor passthru used by WD's own driver.

---

## 4. The NVMe command builder & the complete opcode set  **[CONFIRMED]**

All NVMe commands funnel through a single executor/dispatcher at **`0x410270`**
(`yadl_nvme_execute`). It reads a driver‑type field at `[dev+0x100]` and jumps, via table
at `0x4102E4`, to the matching back‑end (in‑box `0x41DEF0`, others `0x417310`, `0x418610`,
`0x41D7E0`, `0x418DC0`). Every command builder fills an 80‑byte command struct and calls
`0x410270`.

### 4.1 Command struct layout (recovered)

| Struct offset | Field | Evidence |
|---|---|---|
| `+0x00` | opcode (dw0[7:0]) | identify writes `0x6` @ 0x40C323 |
| `+0x04` | NSID (dw1) | |
| `+0x08` | CDW10 | identify: `(CNTID<<16)|CNS` @ 0x40C2E4–0x40C32A |
| `+0x0C` | CDW11 | |
| `+0x10` | CDW12 | |
| `+0x14` | CDW13 | |
| `+0x3C` | data length (bytes) | identify arg; `0x1000` in 0xE2 cmd |
| `+0x40` | direction (1=host→ctrl, 2=ctrl→host) | identify `2`; download `1` |
| `+0x44` | timeout | global @ ds:0x45786C; `0x1F4`=500 ms in 0xE2 cmd |

### 4.2 Every opcode the tool issues (all 7 executor call sites)

| Call site | Opcode @ struct+0 | Command | Notes |
|---|---|---|---|
| 0x40C25C, 0x40C33B | **0x06** | Identify | CDW10 = `(CNTID<<16)\|CNS`; ctrl→host |
| 0x40C497 | **0x09** | Set Features | standard admin (leaf builder) |
| 0x40C0F9 | **0x10** | Firmware Commit/Activate | |
| 0x40C1A5 | **0x11** | Firmware Image Download | direction=1 (host→ctrl) |
| 0x41DBB0, 0x41DD54 | **0xE2** | **vendor "adapter info"** | see §6 |

`get_safe_firmware_slot` (`yextfirmware/firmware.c`, 0x40B1B6, *"no read/write slot
exists"*) selects the writable slot from Identify's FRMW field — no extra command needed.
There is **no Get Log Page (0x02)** and **no I/O opcode 0x80** anywhere in the command path.

---

## 5. Firmware‑update path — standard NVMe only  **[CONFIRMED]**

Trace strings enumerate the whole state machine and confirm it is textbook NVMe:

- *"Attempting deferred download followed by activation"* → Commit action 0x02 (download to
  slot, activate on reset).
- *"does not support deferred download … immediate download with offsets"* → chunked
  Firmware Image Download (0x11) with increasing offsets, then Commit (0x10).
- *"cannot detect a safe target firmware slot, fall back to slot 1"* → slot selection.
- Parallel ATA (`ATA download`, DLMC "download microcode" min/max **blocks** = *transfer
  chunk sizes*, not NAND blocks) and SCSI (`SCSI download`) paths exist for non‑NVMe drives.
- On the Windows in‑box driver, download/activate go through
  `IOCTL_STORAGE_PROTOCOL_COMMAND` / the storage firmware IOCTLs, so the `0x11`/`0x10`
  bytes are added by the OS driver rather than appearing as immediates — semantically
  identical.

**No vendor opcode is used to download, verify, or activate firmware.**

---

## 6. The one vendor opcode present: `0xE2` (Intel‑RST "adapter info")

**[CONFIRMED]** the tool builds this NVMe‑format admin command at 0x41DB38 and 0x41DD08
(function `0x41DA50`):

```yaml
opcode:    0xE2            # cmd struct +0x00
NSID:      0x00000000      # +0x04
CDW10:     0x000003FF      # +0x08   (1023 = 1024 dwords − 1  →  4096‑byte transfer)
CDW11:     0x00000000      # +0x0C
CDW12:     0xE0  or  0xE1  # +0x10   (two calls; a sub‑selector / object id)
CDW13:     0x00000000      # +0x14
data_len:  0x1000 (4096)   # +0x3C
direction: controller → host (2)     # +0x40
timeout:   0x1F4 (500 ms)  # +0x44
```

**Context / caller chain [CONFIRMED]:**
`0x41DA50` (labelled *"adapter info"*, in `yadl/windows/yadl_nvme_windows_rste.c`) ← called
only from `0x415280` = `yadl_windows_enumerate_disk` / `yadl_windows_enumerate_rste`
(opens `\\.\Scsi%d:`, parses `PCI\VEN_%x&DEV_%x`) ← `0x40EF51`. It runs during **device
enumeration on Intel RST/RSTe systems**, to discover NVMe drives hidden behind the RAID
controller.

**Interpretation:**
- **[LIKELY]** this `0xE2` is an **Intel RST(e) management/passthru "get adapter info"**
  query, i.e. it coincidentally shares the opcode number `0xE2` with the SN740's advertised
  vendor opcode. It is a 4 KiB log‑style read with a sub‑selector in CDW12 (`0xE0`/`0xE1`).
- **[SPECULATIVE]** whether the SN740 controller interprets `0xE2` the same way on a
  *direct* (non‑RST) path is **not determinable from this binary** — the direct NVMe paths
  here only ever emit the standard opcodes in §4.2. If you want to probe `0xE2` on your own
  drive, the recovered shape above (NSID 0, CDW10 = `(len/4)-1`, CDW12 selector, ctrl→host)
  is the only concrete grammar this package provides, and even that is via the RST path.

---

## 7. The VSC (Vendor Unique Command) module `yextvuc/wd`  **[CONFIRMED present, ATA/SAS‑only]**

Files `yextvuc/wd/fill_and_execute.c` and `.../parse.c`. This is SanDisk/WD's vendor
command framework, with a clear grammar:

- **"send key" enable/disable handshake** — `_vsc4_execute_send_key`,
  `_vsc5_ata_execute_send_key`, `_vsc5_scsi_execute_send_key`; strings *"failed to enable
  vsc"* / *"failed to disable vsc"*. This is a fixed enable sequence, not a cryptographic
  auth.
- **command selectors** `ac` (action code) + `fc` (function code) — string
  *"VSC send key (ac %u/fc %u) failed: %xh/%xh"*.
- **implementation level** check — *"vsc implementation level (%d) must be <= 4"*;
  `yextvuc_wd_identify_parse_vsc_implementation_level` reads the level from Identify.
- `yextvuc_wd_vsc_execute_vsc_id` + `yextvuc_wd_vscid_parse_native_firmware` — reads a
  vendor "VSC ID" structure and parses the drive's *native firmware* version.

**Crucially:** there is **no `_vsc*_nvme_*` handler**. The generation vtable is only
populated for ATA (level 4) and ATA/SCSI (level 5). VSC init (`0x409E40`) is reachable only
inside the yextvuc (SATA/SAS) module. **Your NVMe SN740 is never routed through the VSC
send‑key / ac‑fc path by this tool.** So, for NVMe, this package exposes *no* vendor unlock,
challenge/response, token, or authenticated‑debug interface — those checks, if any, live in
the controller and are not spoken to here.

---

## 8. What is **not** in the package (with the strings that could have fooled us)

Searched (ASCII + UTF‑16) across all three binaries for the full NAND/diagnostic
vocabulary. Findings:

| You asked about | Present? | What the matching bytes actually are |
|---|---|---|
| NAND, wordline/WL, plane, die, CE, channel, PBA, raw page | **No** | absent entirely |
| read‑retry, Vref, sense‑level, read‑level | **No** | absent |
| ECC / LDPC bypass, raw page‑buffer | **No** | absent |
| NAND test mode, direct flash cmds | **No** | absent |
| factory / manufacturing / RMA | **No** | only EULA legal text |
| `Threshold` | *misleading* | `execute_storage_temperature_threshold`, `stt->Threshold/OverThreshold` = **SMART temperature** |
| `block` | *misleading* | ATA **download‑microcode chunk** size (`DLMC min/max blocks`, `block count: 0x%04x`) |
| `sense`, `lun` | *misleading* | **SCSI** sense buffer / SCSI LUN |
| `debug` | *misleading* | a `/debug` verbosity flag + global gate `ds:0x4583DC` |
| `auth`, `challenge`, `unlock`, `security`, `service` | *misleading* | all inside the **WD software EULA** text block |
| `DUI`, opcode `0xFA` | **No** | not referenced (your 0xFA DUI capture lives in a *different* WD tool) |

**[CONFIRMED]** This updater contains no physical‑NAND, ECC/Vref/read‑retry, test‑mode,
factory/RMA, or authenticated‑debug command construction — reachable or dead.

---

## 9. Answers to your enumerated questions

- **Q5/Q6 (command grammar & subcommands):** recovered for the opcodes the tool uses — see
  §4 (struct layout + opcode table) and §6 (`0xE2`). Subcommand dispatch exists only as (a)
  the `0x410270` driver jump‑table, (b) the VSC `ac`/`fc` selectors (ATA/SAS only), and (c)
  the `0xE2` CDW12 selector (`0xE0`/`0xE1`). No jump table keyed by `0xEA/0xE9/…` exists,
  because those opcodes are never built. What made your all‑zero `0xEA` fail with *Invalid
  Field* is decided **in the controller firmware**, which this host binary does not model.
- **Q7 (firmware path):** standard NVMe download/commit only — §5.
- **Q8 (hidden diagnostics/manufacturing):** none, including in dead code — §8. The only
  latent vendor machinery is the ATA/SAS VSC framework (§7) and the RST `0xE2` enumeration
  read (§6).
- **Q9 (authentication/locking):** a fixed ATA/SAS "send‑key" enable exists; no NVMe auth,
  no challenge/response, no signed token, no certificate/password gate on the host side —
  §7. Any real authorisation is controller‑side and not communicated with here.
- **Q3 firmware image (`.fluf`):** see §10.

---

## 10. Firmware container `73110101.fluf`  **[CONFIRMED]**

Plaintext header (first ~0x1D0 bytes), then a small binary sub‑header, then the body:

```
FLUF Format 002
Created 20220608_154022
on host R0110E1B04-140
by user fwuser
using BotCreate built 20220608_154022
From BOTfile   time 20220608_154022   CRC32 NotCalcd
named c:\WDLABS\BuildTrees\workspace\ci_task_runner_a_bat\fw\_out_cleared\vulcan_sed_perf\BOT\CFG.bot
```

| Property | Value / finding |
|---|---|
| Format | **FLUF Format 002** (WD firmware container) |
| Size | 2,822,144 bytes |
| Internal target rev | 73110101 (matches `FWWINSD.PRO`) |
| Controller platform codename | **`vulcan_sed_perf`** (SED = self‑encrypting drive) |
| Build | WD CI ("BotCreate", `ci_task_runner`), 2022‑06‑08, from `CFG.bot` |
| Entropy | **≈ 7.9996 across every window** (overall 7.9996) |
| Encrypted? | **Yes [LIKELY]** — near‑maximal uniform entropy, zero recoverable structure/strings after the header |
| Compressed? | possible, but indistinguishable from encryption at this entropy |
| Signed? | **[LIKELY]** — WD field firmware is signed; the controller validates on Commit. No signature block is exposed in the plaintext header |
| Host decrypts it? | **No [CONFIRMED]** — the host streams the opaque image verbatim via Firmware Image Download; all validation/decryption is controller‑side |

There is therefore no plaintext firmware code, no NAND layout, and no vendor‑command table
to extract from the image with static analysis.

---

## 11. Confidence summary

**CONFIRMED**
- Provenance: Lenovo‑signed Inno Setup 5.5.7; payload inventory & hashes (§1).
- Architecture: fwwinsd detects/launches, sanupdater flashes (§2).
- Transports & IOCTLs; the WD SRB passthru `cmd.dw0…dw15` structure (§3).
- The command‑struct layout and the complete opcode set `{0x06, 0x09, 0x10, 0x11, 0xE2}` (§4).
- Firmware update = standard NVMe Download/Commit (§5).
- `0xE2` command shape and that it fires only in RST enumeration (§6).
- VSC send‑key/`ac`/`fc` framework exists but is ATA/SAS‑only, not NVMe (§7).
- No NAND/physical/ECC/Vref/test‑mode/factory/RMA/auth‑debug construction (§8).
- `.fluf` = FLUF Format 002, encrypted, controller‑validated (§10).

**LIKELY**
- `0xE2` is an Intel‑RST(e) "get adapter info" query rather than a SN740‑specific command.
- `.fluf` body is encrypted and signed.

**SPECULATIVE**
- Whether the SN740 interprets `0xE2` identically on a direct path.
- Semantics of `0xEA/0xE9/0xE4/0xE5/0xE6/0xF1/0xFA/0x80` — **not present in this package**;
  they are implemented only in the controller firmware and must be studied from the drive
  side (e.g. its Command Effects Log + controlled experiments), not from this updater.

---

## 12. Method / tooling

`pefile` + `capstone` (x86) for PE parsing and disassembly; `objdump -M intel` for the
linear listing; `innoextract 1.9` to unpack the Inno Setup overlay; `strings`/`grep` for the
ASCII+UTF‑16 corpus; a Python entropy/window scan for the firmware image. Opcode claims were
verified by (a) enumerating all call sites of the executor `0x410270` and reading the
immediate written to struct+0 before each, and (b) an exhaustive immediate/operand sweep for
`0xE2 0xE4 0xE5 0xE6 0xE9 0xEA 0xF1 0xFA` across the disassembly.

*No firmware was flashed and no NVMe command was sent to any device during this analysis.*
