# Raw NAND command interface and tooling for low-level experiments on commercial NAND dies

Scope: public standards (ONFI, JEDEC JESD230), public open-source code (Linux MTD, U-Boot, other open code), public datasheets, open-source and commercial hardware, and the physical limits of pin-level access. Everything comes from publicly accessible material. No leaked, NDA or test-mode material was sought or used. Research date: 2026-10-17.

Source pins used throughout:
- Linux kernel: tag **v6.17** (`git ls-remote` ref value `6063257da111c7639d020c5f15bfb37fb839d8b6`). Files were downloaded from raw.githubusercontent.com/torvalds/linux/v6.17/... and line numbers checked locally. Elixir mirror: https://elixir.bootlin.com/linux/v6.17/source/drivers/mtd/nand/raw/
- U-Boot: tag **v2025.10** (ref `5588691f0bf823a0ab717527587cf2ceccb0b6f3`).
- Xilinx embeddedsw at commit `97f2baf7f69e9d5f447650110af0d8841e501277`. Cosmos+ OpenSSD at commit `78601486bb5581e40628ec7e841dea8e97eff034`. NANDO at commit `4d840b7afff7c1a1c02eacce3a72761cd0f58c93`.

---

## 1. Standards: ONFI / JEDEC JESD230 command set, feature addresses, read-level / sense-timing definitions

### Takeaway
The ONFI/JEDEC command set fixes the single-page read (00h–addr–30h), multi-plane read (00h…32h), cache read (31h/3Fh), status (70h/78h), Set/Get Features (EFh/EEh, one address byte plus 4 parameter bytes P1–P4), LUN Set/Get Features (D5h/D4h), Read Parameter Page (ECh), Volume Select (E1h), ZQ calibration (D9h/F9h) and others. I could confirm these bytes only from secondary public sources: open-source headers that quote ONFI 3.1, and a public ONFI-1.0-compliant Micron datasheet. onfi.org and jedec.org blocked every download attempt from this environment, so I could not check section or table numbers in the specs themselves. In everything I could verify, the only standard feature address is 01h (timing mode). The read-retry and read-offset feature addresses used in open-source code (89h, for example) are labelled **vendor-specific**. I found no evidence that ONFI standardizes read-reference offsets or sense timing.

### Cited Findings
**Command bytes (ONFI 3.1, from Xilinx's public ONFI header).** `xnandpsu_onfi.h` says "This file defines all the ONFI 3.1 specific commands and values" and lists (lines 41–111) — [Xilinx embeddedsw xnandpsu_onfi.h](https://github.com/Xilinx/embeddedsw/blob/97f2baf7f69e9d5f447650110af0d8841e501277/XilinxProcessorIPLib/drivers/nandpsu/src/xnandpsu_onfi.h#L41-L111):
- Mandatory commands: Read `0x00`/`0x30`; Change Read Column `0x05`/`0xE0`; Block Erase `0x60`/`0xD0`; Read Status `0x70`; Page Program `0x80`/`0x10`; Change Write Column `0x85`; Read ID `0x90`; Read Parameter Page `0xEC`; Reset `0xFF`.
- Optional commands: Multiplane Read `0x00`/`0x32`; Copyback Read `0x00`/`0x35`; Change Read Column Enhanced `0x06`/`0xE0`; Read Cache Random `0x00`/`0x31`; Read Cache Sequential `0x31`; Read Cache End `0x3F`; Multiplane Block Erase `0x60`/`0xD1`; Read Status Enhanced `0x78`; Multiplane Page Program `0x80`/`0x11`; Page Cache Program `0x80`/`0x15`; Copyback Program `0x85`/`0x10`; Small Data Move `0x85`/`0x10`; Change Row Address `0x85`; Volume Select `0xE1`; ODT Configure `0xE2`; Read Unique ID `0xED`; Get Features `0xEE`; Set Features `0xEF`; LUN Get Features `0xD4`; LUN Set Features `0xD5`; Reset LUN `0xFA`; Synchronous Reset `0xFC`.
- Status bits: FAIL `0x01`, VSP `0x10`, WP_n `0x80` (lines 114–120).

**ZQ calibration bytes.** An open-source NAND simulator header gives `CMD_ZQ_CALIBRATION_SHORT 0xd9` and `CMD_ZQ_CALIBRATION_LONG 0xf9`. The same header has every other byte above, e.g. `CMD_VOLUME_SELECT 0xe1` and `CMD_LUN_GET_FEATURE 0xd4` (lines 41–76) — [daxiali/NandSimulator nand.h](https://github.com/daxiali/NandSimulator/blob/7898e441e3af52190140e9b78a1fe24aefa40cdc/nand/nand.h#L41-L76). This is a hobby project, so treat it as secondary corroboration.

**Linux kernel generic command bytes.** v6.17 `include/linux/mtd/rawnand.h` lines 52–73 define: READ0 `0`, READ1 `1`, RNDOUT `5`, PAGEPROG `0x10`, READOOB `0x50`, ERASE1 `0x60`, STATUS `0x70`, SEQIN `0x80`, RNDIN `0x85`, READID `0x90`, ERASE2 `0xd0`, PARAM `0xec`, GET_FEATURES `0xee`, SET_FEATURES `0xef`, RESET `0xff`, READSTART `0x30`, READCACHESEQ `0x31`, READCACHEEND `0x3f`, RNDOUTSTART `0xE0`, CACHEDPROG `0x15` — [rawnand.h v6.17](https://elixir.bootlin.com/linux/v6.17/source/include/linux/mtd/rawnand.h#L52). The kernel core does not define multi-plane read, Volume Select, LUN features or ZQ.

**Set Features format.** The kernel sends `NAND_OP_CMD(NAND_CMD_SET_FEATURES)`, then a 1-byte feature address (tADL), then `ONFI_SUBFEATURE_PARAM_LEN` = 4 data bytes, then waits up to tFEAT_max (nand_base.c `nand_set_features_op`, lines 2018–2050; onfi.h line 55) — [nand_base.c v6.17](https://elixir.bootlin.com/linux/v6.17/source/drivers/mtd/nand/raw/nand_base.c#L2018).

**Feature-address status in the kernel.** v6.17 `include/linux/mtd/onfi.h` lines 44–51:
- `/* ONFI feature number/address */ ... #define ONFI_FEATURE_ADDR_TIMING_MODE 0x1`
- `/* Vendor-specific feature address (Micron) */ #define ONFI_FEATURE_ADDR_READ_RETRY 0x89` and `#define ONFI_FEATURE_ON_DIE_ECC 0x90`

The kernel therefore labels read-retry (89h) as vendor-specific, not ONFI-standard — [onfi.h v6.17](https://elixir.bootlin.com/linux/v6.17/source/include/linux/mtd/onfi.h#L44). The same header defines timing-mode bits `ONFI_TIMING_MODE_0..5` (lines 36–41) and the optional-command bits `ONFI_OPT_CMD_READ_CACHE` (BIT(1)) and `ONFI_OPT_CMD_SET_GET_FEATURES` (BIT(2)).

**Feature-address table in a public ONFI-1.0 datasheet.** Micron's 1Gb SLC (MT29F1G08ABAEA family, "Open NAND Flash Interface (ONFI) 1.0-compliant") Table 9 "Feature Address Definitions" (p.40) lists: 00h Reserved; **01h Timing mode**; 02h–7Fh Reserved; **80h Programmable output drive strength**; **81h Programmable RB# pull-down strength**; 82h–FFh Reserved; **90h Array operation mode** (Table 10, p.41: P1 = 00h Normal, 01h OTP). The same document says features are volatile: "When a feature is set, by default it remains active until the device is power cycled. It is volatile." There is **no read-retry feature address** on this SLC part — [Micron MT29F1G08 Rev. E datasheet (Digi-Key-hosted)](https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/306/MT29F1G08,16_Rev.E_July2012.pdf). The PDF carries Micron's usual "Micron Confidential and Proprietary" footer, but it is the standard product datasheet that the authorized distributor hosts publicly.

**Retail SLC command set (same datasheet, Table 5 "Command Set", pp.29–30).** RESET FFh; READ ID 90h; READ PARAMETER PAGE ECh; READ UNIQUE ID EDh; GET FEATURES EEh (1 address cycle); SET FEATURES EFh (1 address cycle, 4 data cycles); READ STATUS 70h; RANDOM DATA READ 05h–E0h; READ PAGE 00h–(4 addr)–30h; READ PAGE CACHE SEQUENTIAL 31h; READ PAGE CACHE RANDOM 00h–31h; READ PAGE CACHE LAST 3Fh; PROGRAM PAGE 80h–10h; PROGRAM PAGE CACHE 80h–15h; ERASE BLOCK 60h–D0h; READ FOR INTERNAL DATA MOVE 00h–35h; PROGRAM FOR INTERNAL DATA MOVE 85h–10h; BLOCK UNLOCK LOW 23h; BLOCK UNLOCK HIGH 24h; BLOCK LOCK 2Ah; BLOCK LOCK-TIGHT 2Ch; BLOCK LOCK READ STATUS 7Ah. This part has no multi-plane read — [Micron MT29F1G08 datasheet](https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/306/MT29F1G08,16_Rev.E_July2012.pdf).

**Other feature addresses seen in public vendor BSP code.** Allwinner's GPL BSP NAND driver logs "set feature(addr 0x02) NV-DDR2 Configuration failed!" and uses "feature address 81h, Programmable R/B# Pull-Down strength" — [CrealityTech/sonic_pad_os rawnand_timings.c](https://github.com/CrealityTech/sonic_pad_os/blob/7f37a7fbf4ad59907034715e3d967b9177de1cd4/lichee/linux-4.9/modules/nand/common1/phy-nand/rawnand/rawnand_timings.c). This is secondary corroboration that 02h is NV-DDR2 configuration.

**ONFI version history** — [Wikipedia: ONFI Working Group](https://en.wikipedia.org/wiki/Open_NAND_Flash_Interface_Working_Group):
- 1.0, Dec 28 2006: standard pinout (TSOP-48, WSOP-48, LGA-52, BGA-63), self-identification, standard command set and timing.
- 2.3, Aug 2010: EZ-NAND.
- 3.0, Mar 2011.
- 3.1, Oct 2012: "adds LUN SET/GET Features commands".
- 3.2, Jul 2013: 533 MB/s.
- 4.0, Apr 17 2014: NV-DDR3.
- 4.1, Dec 12 2017: up to 1200 MT/s, DCC, read/write training.
- 4.2, Feb 12 2020: up to 1600 MT/s; "addressing restrictions related to multi-plane operations are relaxed".
- 5.0, May 2021: NV-DDR3 to 2400 MT/s, NV-LPDDR4.

Cadence's ONFI VIP page lists ONFI 1.0 through 5.0, 5.1, 5.2 and 6.0 — [Cadence ONFI VIP](https://www.cadence.com/zh_TW/home/tools/system-design-and-verification/verification-ip/simulation-vip/memory-models/flash/onfi.html) (seen as a search snippet only).

**ONFI spec URLs.** The Wikipedia citations point to ONFI PDFs hosted at `media-www.micron.com/-/media/client/onfi/specs/onfi_4_2-gold.pdf` and `onfi_5_0_gold.pdf`, both marked "url-status=dead". Flash-Cosmos also cites the 4.2 PDF at that URL — [Wikipedia](https://en.wikipedia.org/wiki/Open_NAND_Flash_Interface_Working_Group); [Flash-Cosmos ref. 116](https://arxiv.org/abs/2209.05566). A University of Michigan course page hosts ONFI 2.2 — [UMich mirror](https://web.eecs.umich.edu/~prabal/teaching/eecs373-f11/readings/ONFI_OpenNandFlashInterface_v%202.2.pdf). From this environment it failed TLS verification and then returned 503.

**JEDEC JESD230** — [JEDEC JESD230 listing](https://www.jedec.org/standards-documents/results/jesd230); [BusinessWire, Nov 18 2024](https://www.businesswire.com/news/home/20241118637716/en/JEDEC-Announces-Enhanced-NAND-Flash-Interface-Standard-With-Increased-Speeds-and-Efficiency); [StorageNewsletter 2012](https://www.storagenewsletter.com/?p=120019). Per search summaries of these pages:
- Title: "NAND Flash Interface Interoperability"; developed jointly with ONFI.
- Covers Asynchronous SDR, Synchronous DDR and Toggle DDR.
- JESD230G (Nov 2024) reaches 4800 MT/s and adds a Separate Command Address (SCA) protocol.
- JEDEC lists JESD230G.01 (Sept 2025) as a free download after registration.

jedec.org returned 403 or a JavaScript challenge to direct fetches, so I could not check the document's contents.

### Inferences
- **Commands that select more than one block:** multi-plane read (00h…32h) and the multi-plane erase/program variants are the only documented ones. Each block in a multi-plane read sits in a different plane, and Flash-Cosmos states "The blocks in a plane share all the BLs in that plane" — i.e., different planes have different bitlines (see Q3). Multi-plane read therefore **cannot** put two NAND strings on the same bitline. Multi-LUN or Volume Select interleaving does not either; those are separate dies.
- Feature addresses are a single byte with 4 parameter bytes. Apart from the few addresses with a cross-vendor meaning in the sources above (01h timing mode; 02h NV-DDR2 configuration per Allwinner BSP code), the meaning is vendor-defined. Micron defines 80h/81h/90h on its ONFI-1.0 part. The full ONFI table, e.g. whether ONFI itself standardizes a drive-strength address, could not be verified. Read-retry/read-offset lives in that vendor space.
- **Destructive commands to flag:**
  - Erase 60h/D0h and 60h/D1h.
  - Program 80h/10h, 11h, 15h; copyback 85h/10h.
  - OTP entry (Micron feature 90h = 01h) followed by program or OTP-protect. Micron says "OTP area cannot be erased", and protection is permanent.
  - BLOCK LOCK-TIGHT 2Ch (lock persists until power cycle).
  - Vendor protection or randomizer features (Macronix A0h/B0h, see Q2).
  - Set Features EFh is volatile on Micron parts (cleared by power cycle), so it is reversible.

### Gaps
- I could not open the ONFI PDFs (onfi.org: F5 WAF 403; Wayback Machine: connection reset; UMich mirror: TLS/503) or JESD230 (jedec.org: 403). **ONFI section and table numbers, mandatory/optional status per version, and the full ONFI feature-address table are therefore unverified.** In particular, whether any ONFI 4.x/5.x revision defines a standardized read-retry or read-offset feature, or anything on sense timing, remains unconfirmed. Nothing in the kernel or the other public code suggests it does.
- I did not get exact byte values for ONFI 5.x additions such as training commands, DCC or NV-LPDDR4 from a primary source.

---

## 2. Publicly documented read-retry / read-level-shift mechanisms in open-source code

### Takeaway
Mainline Linux v6.17 implements read-retry for exactly three vendors: **Micron** (Set Features 0x89, mode count from the ONFI vendor block), **Macronix** (Set Features 0x89, fixed 6 modes, gated by an ONFI vendor-block bit) and **SK Hynix 1x-nm MLC** (vendor commands 0x36 / register writes / 0x16, with per-mode register values read from an on-die OTP table). Toshiba/Kioxia and Samsung have no read-retry in mainline. U-Boot v2025.10 implements only the Micron path. All of these select a **discrete, preset retry mode**. None exposes an arbitrary read-reference voltage. They mainly apply to MLC/TLC; the kernel notes "SLC NANDs don't require read-retry".

### Cited Findings
**Generic retry loop (Linux v6.17 `nand_base.c`).** `nand_setup_read_retry()` (lines 3532–3551) has the comment "Some vendors supply a special command to shift the Vt threshold, to be used when there are too many bitflips in a page (i.e., ECC error). After setting a new threshold, the host should retry reading the page." It rejects `retry_mode >= chip->read_retries` and calls `chip->ops.setup_read_retry`. `nand_do_read_ops()` (from line 3572; label `read_retry:` at 3630) increments `retry_mode` on an ECC failure while `retry_mode + 1 < chip->read_retries`, then resets to mode 0 at the end — [nand_base.c v6.17 L3532](https://elixir.bootlin.com/linux/v6.17/source/drivers/mtd/nand/raw/nand_base.c#L3532). A GitHub code search for `"setup_read_retry ="` in torvalds/linux returns only `nand_hynix.c`, `nand_micron.c` and `nand_macronix.c` — [GitHub code search](https://github.com/search?q=repo%3Atorvalds%2Flinux+%22setup_read_retry+%3D%22&type=code).

**Micron (`nand_micron.c`, v6.17)** — [nand_micron.c v6.17 L39](https://elixir.bootlin.com/linux/v6.17/source/drivers/mtd/nand/raw/nand_micron.c#L39):
- Lines 39–56: `struct nand_onfi_vendor_micron` fields, in order: two_plane_read, read_cache, read_unique_id, dq_imped, dq_imped_num_settings, dq_imped_feat_addr, rb_pulldown_strength, rb_pulldown_strength_feat_addr, rb_pulldown_strength_num_settings, otp_mode, otp_page_start, otp_data_prot_addr, otp_num_pages, otp_feat_addr, **read_retry_options** (vendor[14]).
- Lines 69–74: `micron_nand_setup_read_retry()` builds `u8 feature[4] = {retry_mode}` and calls `nand_set_features(chip, ONFI_FEATURE_ADDR_READ_RETRY /*0x89*/, feature)`. On the wire this is **EFh, 89h, P1=mode, P2..P4=00h**.
- Lines 86–87: `chip->read_retries = micron->read_retry_options;` — the number of levels is read from the chip's ONFI parameter page.
- Lines 91–94: features 0x89 and 0x90 (on-die ECC, `ONFI_FEATURE_ON_DIE_ECC_EN BIT(3)`) are whitelisted for Set and Get.
- Applies to: any Micron ONFI chip whose vendor block reports read_retry_options > 0. No part numbers are hard-coded.

**Macronix (`nand_macronix.c`, v6.17)** — [nand_macronix.c v6.17](https://elixir.bootlin.com/linux/v6.17/source/drivers/mtd/nand/raw/nand_macronix.c#L13):
- Line 13 `MACRONIX_READ_RETRY_BIT BIT(0)`; line 14 `MACRONIX_NUM_READ_RETRY_MODES 6`.
- Lines 45–48: `struct nand_onfi_vendor_macronix { u8 reserved; u8 reliability_func; }`.
- Lines 50–61: `macronix_nand_setup_read_retry()` sets `feature[0] = mode` and calls `nand_set_features(chip, ONFI_FEATURE_ADDR_READ_RETRY /*0x89*/, feature)`.
- Lines 139–149: enabled only if `reliability_func & BIT(0)`; then `chip->read_retries = 6`.
- Other vendor features in the same file:
  - 0xA0 block protection (0x38 all-lock / 0x0 unlock, lines 16–18) — **write-protect state change**.
  - 0xB0 randomizer (lines 20–23) — **changes how data is programmed**.
  - 0x90 OTP for 30LFxG18AC (line 35; OTP pages 2..31) — **OTP: potentially irreversible if programmed or locked**.
  - Command 0xB9 power-down (line 33).

**SK Hynix (`nand_hynix.c`, v6.17)** — [nand_hynix.c v6.17](https://elixir.bootlin.com/linux/v6.17/source/drivers/mtd/nand/raw/nand_hynix.c#L14):
- Lines 14–15: `NAND_HYNIX_CMD_SET_PARAMS 0x36` and `NAND_HYNIX_CMD_APPLY_PARAMS 0x16`. Line 17: `NAND_HYNIX_1XNM_RR_REPEAT 8`.
- Lines 87–104, `hynix_nand_reg_write_op(addr, val)`: one address cycle `addr` followed by one data byte `val`.
- Lines 107–139, `hynix_nand_setup_read_retry()`: CMD **0x36**, then for each register write (address = reg, data = value[mode][reg]), then CMD **0x16**.
- Lines 282–284, register list: `{0xcc, 0xbf, 0xaa, 0xab, 0xcd, 0xad, 0xae, 0xaf}`.
- Lines 190–250, `hynix_read_rr_otp()`, reading the retry table: Reset; 0x36; write reg **0x38 = 0x52**; 0x16; then CMDs **0x17, 0x04, 0x19** (the code's own comment is "Sequence to enter OTP mode?"); normal page read of page **0x21f** (784 bytes) or **0x200** (528 bytes) (lines 351–366); Reset; 0x36; reg 0x38 = 0; 0x16; dummy read of page 0.
- Lines 286–341: the number of modes (`nmodes`) and registers (`nregs`) come from majority voting over 8 redundant copies (`NAND_HYNIX_1XNM_RR_REPEAT`); `chip->read_retries = nmodes` (line 340).
- Applicability, lines 371–386: only if the chip has a valid JEDEC ID, `bits_per_cell > 1`, and `nand_tech == 4` ("1xnm technology", from `id.data[5] >> 4`). Comment: "We only support read-retry for 1xnm NANDs, and those NANDs all expose a valid JEDEC ID. SLC NANDs don't require read-retry."
- Lines 388–394: "FIXME: Hynix recommend to copy the read-retry OTP area into a normal page." The loop passes `hynix_mlc_1xnm_rr_otps` (the array base) on every iteration, so only the first OTP descriptor is effectively tried. This is an observation from reading the code.

**Toshiba/Kioxia (`nand_toshiba.c`, v6.17).** No read-retry. Only the vendor ECC status read `TOSHIBA_NAND_CMD_ECC_STATUS_READ 0x7A` for BENAND parts with on-die ECC (lines 18, 38) — [nand_toshiba.c v6.17](https://elixir.bootlin.com/linux/v6.17/source/drivers/mtd/nand/raw/nand_toshiba.c#L18).

**Samsung (`nand_samsung.c`, v6.17).** No read-retry. The file (139 lines) only decodes IDs — [nand_samsung.c v6.17](https://elixir.bootlin.com/linux/v6.17/source/drivers/mtd/nand/raw/nand_samsung.c).

**U-Boot v2025.10.** `drivers/mtd/nand/raw/nand_micron.c` lines 41–46 implement `micron_nand_setup_read_retry()` via `chip->onfi_set_features(..., ONFI_FEATURE_ADDR_READ_RETRY, ...)`. `nand_base.c` lines 2284–2304 hold the generic `nand_setup_read_retry` and lines 2431–2459 the retry loop. U-Boot's `nand_hynix.c`, `nand_macronix.c`, `nand_toshiba.c` and `nand_samsung.c` contain **no** read-retry code (grep count 0) — [U-Boot nand_micron.c v2025.10](https://github.com/u-boot/u-boot/blob/v2025.10/drivers/mtd/nand/raw/nand_micron.c#L41).

**How researchers use read-retry.** SAFARI/CMU papers use the chips' read-retry to measure threshold voltages:
- "We use the read-retry operation present in NAND flash devices to accurately read the cell threshold voltage... As absolute threshold voltage values are proprietary information to flash vendors, we present our results using normalized voltages" — [Cai et al., Proc. IEEE 2017, arXiv:1706.08642](https://arxiv.org/abs/1706.08642).
- Same source: "read-retry has been implemented in modern flash memories (typically those below 30 nm for planar flash)"; and the controller "reads the memory again with a different read reference voltage... until it either successfully reads the data using a certain set of read reference voltages or is unable to correctly read the data using all of the read reference voltages that are available to the mechanism."
- DATE 2013 (Cai, Haratsch, Mutlu, Mai) used read-retry on 2Y-nm MLC to sweep read reference voltages and model Vth distributions — [DATE 2013 PDF](https://past.date-conference.com/date16/files/proceedings/2013/pdffiles/09.6_1.PDF) (via search summary; not fetched by me).

**Other open code.** Allwinner's GPL BSP NAND stack (linux-sunxi / lichee trees on GitHub) contains its own vendor-specific NAND handling, including feature 0x02 (NV-DDR2 configuration) and 0x81 — [sonic_pad_os rawnand_timings.c](https://github.com/CrealityTech/sonic_pad_os/blob/7f37a7fbf4ad59907034715e3d967b9177de1cd4/lichee/linux-4.9/modules/nand/common1/phy-nand/rawnand/rawnand_timings.c). I deliberately did **not** extract vendor retry sequences from these BSP trees. Their provenance (possibly vendor-confidential datasheets) is unclear and mainline maintainers have not reviewed them.

### Inferences
- With only public code, you can change effective read references on **Micron MLC/TLC parts that report read_retry_options**, on **Macronix parts with reliability_func bit 0** (6 modes), and on **Hynix 1x-nm MLC** (OTP-defined modes). Each mode is a preset vector of offsets whose actual voltages are undisclosed. You get an ordinal sweep, not calibrated millivolts.
- Cheap SLC TSOP48 parts, which are the easiest to socket, generally have **no** public read-retry. The Micron 1Gb SLC feature table has none, and the Hynix code excludes SLC. A multi-level readout via "sweeping read reference levels" therefore needs an MLC/TLC part whose public interface includes retry. Even then, the sweep is coarse and unvalidated.
- The Hynix OTP-read sequence (0x36 / 0x38=0x52 / 0x16 / 0x17 / 0x04 / 0x19) enters a vendor OTP mode. Any program or erase while in that mode, or a power loss, could damage the factory retry table. Treat it as risky, and back up the table as the kernel FIXME recommends.

### Gaps
- No mainline Linux or U-Boot read-retry exists for Toshiba/Kioxia, Samsung, WD/SanDisk, YMTC, Intel/Solidigm or recent 3D NAND generations. I found no public documentation of their retry/offset features.
- The number of Micron retry levels is chip-specific (read from the parameter page). The code gives no typical values.
- I did not search other kernels (FreeBSD, NuttX, Zephyr, RTEMS) for additional retry code. The RTEMS tree carries the same Xilinx ONFI header ([RTEMS xnandpsu_onfi.h](https://github.com/RTEMS/rtems/blob/4bca987369df73718cdee1576323c9384fc728b2/bsps/include/dev/nand/xnandpsu_onfi.h)).

---

## 3. Public documentation of commands that activate multiple blocks simultaneously or alter sense-amp timing/reference

### Takeaway
**No public standard, datasheet or open-source driver documents a command that activates wordlines in multiple blocks on a shared bitline, or one that changes sense-amplifier timing or reference directly on retail parts.** The only public demonstration of simultaneous multi-block sensing on commercial chips is Flash-Cosmos (MICRO 2022). Its authors explicitly used manufacturer **test-mode commands** that "NAND flash vendors consider ... proprietary and do not reveal ... in publicly-accessible documentation". Even there the sensed result is a **binary** wired-OR/AND per bitline, not a multi-bit current sum.

### Cited Findings
- Flash-Cosmos abstract: in-flash bulk bitwise operations via "Multi-Wordline Sensing (MWS)... with a single sensing operation", "by testing 160 real 3D NAND flash chips" — [arXiv:2209.05566](https://arxiv.org/abs/2209.05566).
- Method, quoted from the paper's Section 5.1: "We use an FPGA-based testing platform that contains a custom NAND flash controller and a temperature controller. The flash controller supports all the commands implemented in our NAND flash chips, including not only basic read/program/erase commands but also various test-mode commands necessary to dynamically change operating parameters (e.g., the ISPP step voltage and other timing parameters) and simultaneously activate multiple WLs." Chips tested: "160 48-layer 3D TLC NAND flash chips" — [Flash-Cosmos PDF](https://arxiv.org/pdf/2209.05566).
- On public documentation (Section 6.2): "NAND flash vendors consider their test-mode command set design to be proprietary and do not reveal any details in publicly-accessible documentation." Also: "computer architects can build a system that leverages Flash-Cosmos, as long as they have access to the command interfaces used for our characterization" — [Flash-Cosmos](https://arxiv.org/pdf/2209.05566).
- Mechanism of inter-block MWS: "the chip simultaneously applies VREF to multiple WLs ... of different blocks while applying VPASS to all non-target WLs in those blocks. Doing so causes a BL to be discharged if at least one of the target cells in the corresponding NAND string is erased... equivalent to the bitwise OR operation." Intra-block MWS (multiple WLs at VREF in one string) gives AND — [Flash-Cosmos](https://arxiv.org/pdf/2209.05566).
- Why vendors build this in: "manufacturers commonly design a chip to support the activation of multiple WLs (i.e., intra-block MWS) and multiple blocks (i.e., inter-block MWS), to perform multi-page reads/writes and multi-block erases that are critical for rapid testing of the chip [92]" ([92] = Micheloni, Crippa, Marelli, *Inside NAND Flash Memories*, 2010). Also, erase-verify applies VREF to all cells of a block at once — [Flash-Cosmos](https://arxiv.org/pdf/2209.05566).
- Measured cost: "when simultaneously reading WLs in 32 different blocks, tMWS is 36.3% higher than tR". With 4 blocks, "about 80% power increase compared a regular read" and a "negligible latency increase (3.3%)". "Until we activate four blocks, the power consumption of inter-block MWS remains lower than that of an erase operation" — [Flash-Cosmos](https://arxiv.org/pdf/2209.05566).
- Shared bitlines: "The blocks in a plane share all the BLs in that plane, which implies that a single BL is shared by thousands of NAND strings... A NAND flash chip (or a die) contains multiple (e.g., 2 or 4) planes" — [Flash-Cosmos](https://arxiv.org/pdf/2209.05566).
- Flash-Cosmos proposes new commands (MWS with up to four address slots plus a page bitmap, ESP, XOR) as **proposals**, not existing retail commands — [Flash-Cosmos §6.2](https://arxiv.org/pdf/2209.05566).
- Public tunables only: Flash-Cosmos says commodity chips "can tune ISPP parameters ... using the SET FEATURE command [64, 116]", citing a SAFARI read-retry paper and ONFI 4.2. It does not say any public feature address does this; the specific feature addresses appear only in vendor documentation — [Flash-Cosmos](https://arxiv.org/pdf/2209.05566).
- None of the following define a multi-block-same-plane read or a sense-timing/reference control: the Linux/U-Boot drivers above, the ONFI-3.1 command list in Xilinx's header, or the Micron SLC datasheet command/feature tables (see Q1/Q2).

### Inferences
- With only public commands, the closest you can get to "reading several blocks at once" is a **multi-plane read**, which uses different planes and therefore different bitlines and page buffers. Doing several **sequential** reads and summing digitally off-chip does not test analog current summation.
- Any experiment that needs simultaneous same-bitline activation of independently controlled strings needs one of the following. Vendor test-mode access, which is not public and is out of scope here. A vendor or academic collaboration (Flash-Cosmos's authors had such access). Or custom silicon or test structures.
- Even with multi-block activation, the on-chip sense path is a threshold comparator per bitline (binary). A multi-bit sum would have to come indirectly, e.g. by sweeping the reference across repeated reads with read-retry. Whether retry offsets apply during a vendor MWS operation is not publicly documented.

### Gaps
- I found no public datasheet, application note or open-source code with a multi-block-select or sense-amp-timing command for retail parts. I searched kernel code, U-Boot, ONFI-derived headers and the Micron datasheet. This is a negative result, not proof that none exists.
- Reference [92] (*Inside NAND Flash Memories*) is a commercial book that I did not consult. It may describe test-mode architecture in general terms.

---

## 4. Open-source FPGA / MCU raw-NAND controller projects

### Takeaway
The only mature open FPGA NAND controller tied to real hardware is **Cosmos+ OpenSSD** (GPLv3 Verilog plus firmware, Toggle/DDR NAND modules on a Zynq-7045 board). Its low-level NAND controller is a set of **fixed-function FSMs** (read 00h/30h, change column 05h/E0h, Set Features EFh, and so on). Arbitrary command, address and data sequences require editing the HDL. Small async-ONFI cores (OpenCores `nand_controller` and its descendants) and MCU or FTDI readers (NANDO, NANDReader_FTDI) are simpler to modify for arbitrary byte sequences. Their timing granularity is coarse (MCU FSMC or FTDI host-bus emulation), and they speak only the asynchronous SDR interface. I found no LiteX NAND core, no open SAFARI FPGA NAND tester, and no working Raspberry-Pi-GPIO parallel-NAND tool.

### Cited Findings
**Cosmos+ OpenSSD.**
- Repo: https://github.com/Cosmos-OpenSSD/Cosmos-plus-OpenSSD (263 stars). License: GNU GPL v3 (root LICENSE); the Verilog headers read "Copyright (c) 2015 Hanyang University ENC Lab" and are GPL — [repo](https://github.com/Cosmos-OpenSSD/Cosmos-plus-OpenSSD).
- The README says the project homepage moved to https://www.openssd.dev/. That site failed TLS (certificate name mismatch) from this environment.
- Low-level NFC source: `source/hardware/low-level-nfc/llnfc-ddr200mt-1.0.0/` with files such as `NPCG_Toggle_BNC_P_read_DT00h.v`, `NPCG_Toggle_BNC_P_read_AW30h.v`, `NPCG_Toggle_MNC_setFT.v`, `NPCG_Toggle_MNC_getFT.v`, `NPhy_Toggle_Top_DDR100.v`. The names indicate a Toggle-DDR PHY ("ddr200mt").
- Hard-coded bytes: `rCAData <= 8'h30` (read_AW30h.v line 242); `8'h05` / `8'hE0` (read_DT00h.v lines 261, 267); `rPM_CAData[7:0] <= 8'hEF` (setFT.v line 329).
- Firmware command abstraction (`nsc_driver.h` lines 60–69): `V2FCommand_Reset 1`, `SetFeatures 6`, `GetFeatures 46`, `ReadPageTrigger 13`, `ReadPageTransfer 18`, `ProgramPage 28`, `BlockErase 37`, `StatusCheck 41`, `ReadPageTransferRaw 55`. There is no raw command/address passthrough — [nsc_driver.h](https://github.com/Cosmos-OpenSSD/Cosmos-plus-OpenSSD/blob/78601486bb5581e40628ec7e841dea8e97eff034/source/software/GreedyFTL-3.0.0/nsc_driver.h#L60-L69).
- Hardware: "HYU Tiger3 controller ... implemented on a Zynq-7000 XC7Z045 FPGA" with dual Cortex-A9, 1 GB DDR3, "2x SO-DIMM NAND Flash Slots" (4-way per slot), "Hynix 128Gbit MLC NAND". Contact openssd@enc.hanyang.ac.kr — [Technion PSL page](https://psl.technion.ac.il/?p=1591).
- CRZ Technology's releases cover Cosmos, CosmosPlus, Daisy and DaisyPlus. CosmosPlus supports Hynix 8C8W, Toshiba 8C8W and Micron 8C2W NAND modules (including a "Vivado 2025.1" Micron build); DaisyPlus supports Hynix/Toshiba 4C8W and Micron 4C2W NAND modules — [CRZ-Technology/OpenSSD-OpenChannelSSD](https://github.com/CRZ-Technology/OpenSSD-OpenChannelSSD).

**Jasmine OpenSSD.** "an OpenSSD platform based on the commercially successful Barefoot™ controller from Indilinx". Firmware only; the NAND controller is fixed ASIC hardware — [openssd/jasmine](https://github.com/openssd/jasmine).

**Other OpenSSD derivatives.** [antmicro/openssd-nvme](https://github.com/antmicro/openssd-nvme) (Verilog, 39 stars; not inspected), [OCSSD-plus](https://github.com/Cosmos-OpenSSD/OCSSD-plus), [OpenSSD-CN/OpenSSD_8CH8WAY](https://github.com/OpenSSD-CN/OpenSSD_8CH8WAY).

**OpenCores `nand_controller` and descendants.**
- [nbstrong/nand_avalon](https://github.com/nbstrong/nand_avalon): "NAND Controller (ONFI compliant)... work done to improve the nand_controller listed at https://opencores.org/projects/nand_controller". Avalon bus (Intel DE1-SoC). LGPL-2.1. "tested on hardware successfully with ... MT29F256G08CBCBB".
- [thesourcerer8/nand_controller](https://github.com/thesourcerer8/nand_controller): "NAND Controller, targeting ONFI and non-compliant flash". A Verilog port of the OpenCores VHDL, verified against Free Model Foundry flash models. LGPL-2.1. Status in its own words: "It is currently being verified, it does not seem to behave properly in all situations yet."
- Both target the async SDR interface.

**NANDO (bbogush/nand_programmer).** "NANDO is open source NAND programmer based on STM32 processor". Features: TSOP-48 socket adapter "compatible with TL866 adapter", 8-bit parallel NAND, 3.3 V supply, KiCad PCB. GPLv3 (with ST library exceptions). Notice: "THE PROJECT IS NOT ACTIVELY SUPPORTED". The firmware uses the STM32 FSMC (`fsmc_nand.c`). The host protocol has only high-level commands (`NP_CMD_NAND_READ_ID 0x00`, `ERASE 0x01`, `READ 0x02`, `WRITE_S/D/E 0x03–0x05`, `CONF 0x06`, `READ_BB 0x07`, ...) at `nand_programmer.c` lines 36–49. Arbitrary sequences need firmware changes — [bbogush/nand_programmer](https://github.com/bbogush/nand_programmer). An STM32F407 fork exists ([darkspr1te/nand_flasher](https://github.com/darkspr1te/nand_flasher)).

**NANDReader_FTDI (bkerler).** "Universal Nand reader for 8 bit NAND memories using FTDI FT2223H [sic]. Based on http://spritesmods.com/?art=ftdinand"; "Write support disabled". It uses `FT_SetBitMode(m_ftdi,0,BITMODE_MCU)` (MCU Host Bus Emulation) with `sendCmd(char cmd)` and `sendAddr(addr, noBytes)` primitives (`FtdiNand.cpp` lines 160, 185, 191). Any command byte can be issued by editing the C++, but timing is set by the FTDI host-bus emulation. I found no LICENSE file at the repo root — [bkerler/NANDReader_FTDI](https://github.com/bkerler/NANDReader_FTDI).

**OpenFlash (bobberdolle1/openflash).** MIT license. Its "Honest status" says: "Parallel NAND, SPI NAND, eMMC and UFS have host-side chip databases and parsers, but no device firmware that can drive them", and "Linux GPIO timing makes this hard — the microcontrollers are the better home for it" (re: parallel NAND on Raspberry Pi-class SBCs) — [openflash README](https://github.com/bobberdolle1/openflash).

**SPI-NAND-only tools** (not raw parallel NAND): [McMCCRU/SNANDer](https://github.com/McMCCRU/SNANDer) (CH341A), [981213/spi-nand-prog](https://github.com/981213/spi-nand-prog). Also [maximus64/STM32_NAND_Programmer](https://github.com/maximus64/STM32_NAND_Programmer), "NAND programmer for Google Chromecast" on an STM32F4 Discovery.

**SAFARI test infrastructure.** Their papers describe "an FPGA-based testing platform that contains a custom NAND flash controller and a temperature controller" ([Flash-Cosmos](https://arxiv.org/pdf/2209.05566)) and cite Cai et al., "FPGA-Based Solid-State Drive Prototyping Platform" (FCCM 2011) ([arXiv:1805.02819 ref. 7](https://arxiv.org/abs/1805.02819)). A GitHub search of the CMU-SAFARI organization for "flash" returned only CertiFlash, a Rocq/Coq FTL verification framework. I found no open-source release of the NAND tester — [CMU-SAFARI/CertiFlash](https://github.com/CMU-SAFARI/CertiFlash).

### Inferences
- **Best fit for arbitrary sequences with precise timing:** a small custom FPGA design. Either an async-SDR bit-level sequencer (a soft CPU or host-PC-driven FSM that emits CLE/ALE/WE#/RE# edges on an FPGA clock grid, e.g. 10 ns at 100 MHz) or a modified OpenCores-derived core. Cosmos+ is overkill: fixed FSMs, Toggle-DDR modules, and its own NAND SO-DIMMs rather than a TSOP socket.
- MCU (FSMC) and FTDI approaches can issue any command byte after a code change. They control inter-command delays only loosely (µs-scale software), which is fine for read-retry sweeps but not for nanosecond-level timing studies.
- "Precise timing control" at the pins never controls **internal** sense timing. tR is internal and only visible as R/B# busy (see Q6).

### Gaps
- **OpenExpress:** not researched (no search done). Per its authors it targets the NVMe front-end rather than NAND, but I did not verify that.
- I could not access the openssd.dev site, so Cosmos+/Daisy+ pricing and interface specs (e.g., exact NV-DDR2/Toggle mode) are unconfirmed.
- No results for "LiteX NAND" or "Raspberry Pi GPIO parallel NAND" repositories on GitHub. Gitee and GitLab were not searched.
- Licenses of Spritesmods' original ftdinand code and of NANDReader_FTDI are unknown.

---

## 5. Commercial hardware: sockets, FPGA boards, programmers, characterization systems, ATE

### Takeaway
TSOP48 sockets are cheap (about $50–60 for an Enplas OTS-48-0.5 open-top socket). BGA132/152 NAND sockets or adapters are costly and quoted on request (about $583–765 for comparable BGA130 programmer adapters). Entry FPGA boards cost about $85–460. **No universal programmer I found offers publicly documented user-defined raw NAND command scripting**; custom NAND algorithms are vendor-built services. Dedicated NAND characterization systems (NplusT NanoCycler) and production ATE (Advantest T5800 family, Teradyne Magnum) exist, but they publish no prices and are far outside a $2,000 budget.

### Cited Findings
**Sockets / adapters**
- Enplas **OTS-48-0.5-01** TSOP48 test and burn-in socket: **$59.99** — [Waveshare](https://waveshare.com/ots-48-0.5-01.htm).
- Enplas **OTS-48-0.5-014**: **$50.99** (interchangeable with -12) — [Waveshare](https://www.waveshare.com/product/sockets-adapters/tsop-msop-sot/sockets/ots-48-0.5-014.htm). Wells 648-0482211-A01 / SA01H are listed at about AU$55 — [Waveshare](https://www.waveshare.com/648-0482211-a01.htm). (Prices come from search snippets; currency pages vary.)
- Dataman **DIL48/BGA152-1 ZIF NAND-1**: price "Please Contact Us" — [Dataman](https://dataman.com/dil48-bga152-1-zif-nand-1.html).
- Elnec **DIL48/BGA130-1 ZIF NAND-1**: US $583 — [Elnec](https://elnec.com/en/products/programming-adapters/DIL48_BGA130-1_ZIF_NAND-1). Dataman BGA130 version: $765 — [Dataman](https://dataman.com/dil48-bga130-1-zif-nand-1.html). Both via search summary.
- No BGA132 socket listing found.

**FPGA / interface boards**
- Digilent **Arty A7-100T**: launch price $249 — [Digilent blog](https://digilent.com/blog/arty); now $311 at Jameco — [Jameco](https://www.jameco.com/z/410-319-1-Digilent-Arty-A7-100T-Artix-7-FPGA-Development-Board-for-Makers_2306039.html).
- **Cmod A7-35T**: $99 — [FPGA Developer](https://boards.fpgadeveloper.com/boards/Cmod-A7-35T); $117.95 at Jameco — [Jameco](https://www.jameco.com/z/410-328-35-Digilent-Cmod-A7-35T-Artix-7-FPGA-Module-Breadboard-Compatible_2283879.html).
- **Zybo Z7-20**: $399 — [TEquipment](https://www.tequipment.net/Digilent/Zybo-Z7-20/FPGA/).
- **FTDI FT2232H Mini Module**: $29.40 (Digi-Key, out of stock with a long lead time) — [Digi-Key](https://www.digikey.com/en/products/detail/ftdi-future-technology-devices-international-ltd/FT2232H-MINI-MODULE/2027252).
- **Cosmos+ OpenSSD**: no public price found; contact Hanyang ENC Lab — [Technion PSL](https://psl.technion.ac.il/?p=1591). Its XC7Z045 FPGA alone lists at roughly $1,444–2,263 per chip at distributors (search summary) — [electronicspecifier/Digi-Key](https://electronicspecifier.com/product-centre/distributors/digi-key/part/598ad0ea03aac6a1cdff8325).

**Logic analyzers**
- Saleae **Logic 8 $499**, **Logic Pro 8 $999**, **Logic Pro 16 $1,499** — [Saleae discounts table](https://blog.saleae.com/saleae-discounts/).
- Student programme: 50% off the Logic 8 or Logic MSO 2×100 — [Saleae student discount](https://new.saleae.com/discounts/student).

**NAND chips**
- Kioxia **TC58NVG0S3HTA00** (1 Gb SLC, TSOP48): about $2.18 per single unit at LCSC — [LCSC](https://www.lcsc.com/product-image/C84581.html); $3.21 via a Digi-Key aggregator — [electronicspecifier](https://electronicspecifier.com/product-centre/distributors/digi-key/part/598aad1b03aac6a1cdf47177).
- Micron MT29F1G08ABAEA (1 Gb SLC, ONFI 1.0, VCC 2.7–3.6 V) — [Micron datasheet](https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/306/MT29F1G08,16_Rev.E_July2012.pdf).

**Universal programmers**
- Xeltek SuperPro listings mention a "customized ... Programming algorithm" option and a "customer-specific NAND solution". A SuperPro 6000 "batch command" combines existing operations (program, verify, etc.) "at any sequence" — [6TL/etesters SuperPro 6100N](https://6tl.etesters.com/product/E4CD6E93-7EB6-4594-8B79-A6B54EB8360F/universal-programmer-superpro-6100n/); [TheDebugStore SuperPro 6000](https://thedebugstore.com/products/superpro-6000-universal-programmer-xeltek).
- BPM documents fixed vendor NAND algorithms with bad-block options — [BPM Microsystems](https://www.bpmmicro.com/?p=98440).
- These come from search summaries. I found no public documentation of user-defined raw command scripts for Xeltek, BPM, Dataman or Elnec.

**NAND characterization systems**
- NplusT (Italy) **NanoCycler HS 20**: "next-gen NAND characterization system", 2.0 GT/s, BGA132/BGA152/BGA154 sockets, independent sockets with per-package temperature control, data-pattern generation, bitmap transfer, "high-resolution timing measurement, and power profiling". An HS24 (2.4 GT/s) was announced as in development. No price published — [StorageNewsletter, 2022-08-12](https://www.storagenewsletter.com/2022/08/12/availability-of-italian-nplust-nanocycler-hs-20-nand-characterization-system/).

**Production ATE**
- Advantest **T5835**: "cost-efficient, high-volume memory tester" for NAND and DRAM, up to 5.4 Gbps, up to 768 devices in parallel, configurable "as an engineering station for R&D" — [Advantest press release 2021-11-30](https://www.advantest.com/en/news/2021/20211130.html).
- Teradyne **Magnum EPIC** targets DRAM, while "Magnum 7" and "Magnum VUy" target NAND/MCP — [Teradyne Magnum EPIC](https://www.teradyne.com/products/magnum-epic/).
- No prices or university-access programmes found.

### Inferences
- **Under $2,000** the practical options are: a TSOP48 socket plus an FPGA board or MCU/FTDI plus a logic analyzer, using cheap async SDR parts. BGA/Toggle-DDR parts or Cosmos+ quickly push past the budget.
- Commercial programmers are built to dump and program. They do not, publicly, offer the arbitrary command sequencing an analog-compute experiment needs.
- Professional characterization systems (NanoCycler) and ATE add timing, power and temperature metrology. They are still limited to the chip's pins and to whatever command set the user is entitled to; they cannot reach internal bitlines. Their costs are unpublished; ATE likely costs far more than the budget (no citation found for a figure).

### Gaps
- I found no public prices for NplusT NanoCycler, Siglead or other NAND testers, Advantest/Teradyne memory ATE, Cosmos+ boards, or BGA132/152 NAND sockets.
- Dataman, Elnec and BPM user manuals were not checked for scripting features. The "no scripting" conclusion rests on search summaries.
- XGecu T48/T56 (TL866 successors) and their NAND support were not researched.
- University ATE access programmes (Advantest V93000 / Teradyne university programmes) were not found.

---

## 6. Physical limits of pin-level access

### Takeaway
At the package pins you control only the **digital interface**: command bytes, address bytes and data bytes (latched by CLE/ALE/WE#/RE# on DQ[7:0]); CE# selection; WP#; the timing *between* operations (subject to datasheet minimums); and VCC/VCCQ within spec, plus ambient temperature. You observe DQ data, the status register, R/B# busy duration (tR/tPROG/tBERS) and supply current. Everything analog stays internal and is set by on-die circuits and microcode: wordline voltages (VREF, VPASS, program/erase voltages from internal pumps/DACs), string/ground select gates, bitline precharge and sense timing, sense-amp references, and the page-buffer latches. Read-retry (Q2) is the only publicly documented lever on effective read reference. I found no public method for measuring bitline current directly on packaged parts.

### Cited Findings
- **String architecture:** "all cells in the same column are connected in series to form a bitline (BL) or string. All cells in a bitline share a common ground (GND) on one end, and a common sense amplifier (SA) on the other... Bitline operations are controlled by turning the ground select line (GSL) and string select line (SSL) transistor of each bitline on or off" — [Cai et al., Proc. IEEE 2017](https://arxiv.org/abs/1706.08642).
- **Read biasing:** "In order to read from a single cell on the bitline, all of the other cells (i.e., unread cells) on the same bitline must be switched on... by applying the pass-through voltage onto the wordlines of the unread cells" — [Cai et al.](https://arxiv.org/abs/1706.08642).
- **Vth values are proprietary:** "As absolute threshold voltage values are proprietary information to flash vendors, we present our results using normalized voltages" — [Cai et al.](https://arxiv.org/abs/1706.08642).
- **Internal parameters need test modes:** changing operating parameters ("ISPP step voltage and other timing parameters") and "simultaneously activat[ing] multiple WLs" required "test-mode commands" — [Flash-Cosmos](https://arxiv.org/pdf/2209.05566).
- **Latches:** Flash-Cosmos's proposed commands would add host control of "(i) inverse-read mode, (ii) sensing-latch (S-latch) initialization, (iii) cache-latch (C-latch) initialization, and (iv) data transfer from S-latch to C-latch". These latch controls are not exposed by today's public commands — [Flash-Cosmos](https://arxiv.org/pdf/2209.05566).
- **Plane/channel structure:** "Multiple chips in a NAND flash package can operate independently of each other but share the package's command/data buses (i.e., channel)" — [Flash-Cosmos](https://arxiv.org/pdf/2209.05566).
- **Supply range for a typical retail SLC part:** "VCC: 2.7–3.6V"; ONFI 1.0-compliant; R/B# open-drain with programmable pull-down strength (feature 81h) — [Micron MT29F1G08 datasheet](https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/306/MT29F1G08,16_Rev.E_July2012.pdf).
- **Interface timing modes** (ONFI timing modes 0–5) are host-selectable via feature 01h. They set I/O timing, not array timing — [onfi.h v6.17 L36–L47](https://elixir.bootlin.com/linux/v6.17/source/include/linux/mtd/onfi.h#L36).

### Inferences
- **Controllable from pins:**
  - Which page or block is read (one block per plane per operation).
  - Read-retry mode, where supported.
  - Cache/multi-plane modes.
  - Program/erase history: P/E cycling, program patterns, and retention/read-disturb stress, which shift Vth.
  - Timing gaps between commands (e.g., read-disturb or relaxation studies).
  - VCC within spec, and temperature (with external heating, as SAFARI does).
  - Interface drive strength and timing mode.
- **Not controllable:** absolute wordline voltages, simultaneous selection of strings in multiple blocks on one bitline, sense/precharge durations, SA trip point (except through vendor retry presets), and latch operations. Internal regulators/pumps probably make VCC changes only weakly coupled to array biases (inference; no public source found).
- **Observable analog-ish quantities:** R/B# busy time (tR) and ICC during reads, measured with a shunt and scope. These might show aggregate array activity, but they are not per-bitline currents.
- **Direct bitline current measurement** on a packaged die would need decapsulation and microprobing of internal metal. No public reference found. Bitlines are not bonded to package pins.

### Gaps
- I found no public source describing on-die charge-pump/DAC architecture for a specific retail part, or how VCC variation affects array biases.
- I found no public report of probing NAND bitlines on decapped commercial dies. I did not search the failure-analysis literature.
- *Inside NAND Flash Memories* (Micheloni et al.), the standard architecture text, was not consulted (commercial book).

---

## 7. Practical cost breakdown for a starter setup (< ~$2,000)

### Takeaway
A pin-level async-SDR rig is easily affordable at roughly $700–1,500: TSOP48 socket, FPGA board, a handful of NAND parts and a logic analyzer. But the publicly available command set cannot do the target experiment (same-bitline multi-block summation; see Q3). The budget rig fits experiments that are possible: read-retry Vth sweeps on MLC parts that support retry, read-disturb and timing studies, and digital emulation of the dot product.

### Cited Findings (component prices; all from sources cited in Q5)
| Item | Example | Price | Source |
|---|---|---|---|
| TSOP48 socket | Enplas OTS-48-0.5-01 / -014 | $59.99 / $50.99 | [Waveshare -01](https://waveshare.com/ots-48-0.5-01.htm), [Waveshare -014](https://www.waveshare.com/product/sockets-adapters/tsop-msop-sot/sockets/ots-48-0.5-014.htm) |
| SLC TSOP48 NAND | Kioxia TC58NVG0S3HTA00 (1 Gb) | ~$2.18–3.21 each | [LCSC](https://www.lcsc.com/product-image/C84581.html), [Digi-Key via electronicspecifier](https://electronicspecifier.com/product-centre/distributors/digi-key/part/598aad1b03aac6a1cdf47177) |
| FPGA (small) | Digilent Cmod A7-35T | $99–117.95 | [FPGA Developer](https://boards.fpgadeveloper.com/boards/Cmod-A7-35T), [Jameco](https://www.jameco.com/z/410-328-35-Digilent-Cmod-A7-35T-Artix-7-FPGA-Module-Breadboard-Compatible_2283879.html) |
| FPGA (mid) | Arty A7-100T / Zybo Z7-20 | ~$249–311 / $399 | [Digilent](https://digilent.com/blog/arty), [Jameco](https://www.jameco.com/z/410-319-1-Digilent-Arty-A7-100T-Artix-7-FPGA-Development-Board-for-Makers_2306039.html), [TEquipment](https://www.tequipment.net/Digilent/Zybo-Z7-20/FPGA/) |
| USB-parallel alternative | FT2232H Mini Module | $29.40 | [Digi-Key](https://www.digikey.com/en/products/detail/ftdi-future-technology-devices-international-ltd/FT2232H-MINI-MODULE/2027252) |
| MCU programmer alternative | NANDO (open KiCad + STM32) | PCB/BOM cost not published | [NANDO](https://github.com/bbogush/nand_programmer) |
| Logic analyzer | Saleae Logic 8 / Pro 8 / Pro 16 | $499 ($250 student) / $999 / $1,499 | [Saleae](https://blog.saleae.com/saleae-discounts/), [Saleae student](https://new.saleae.com/discounts/student) |

### Inferences
Illustrative totals. These are my arithmetic on the prices above, excluding shipping, tax, breakout PCB and supply instrumentation:
- **Minimal:** socket $60 + Cmod A7 $99–118 + 20 SLC chips about $45–65 + Saleae Logic 8 $499 (or $250 student) ≈ **$700–750** (≈ $460–500 with the student analyzer).
- **Comfortable:** socket $60 + Arty A7-100T about $311 + chips about $65 + Logic Pro 8 $999 ≈ **$1,435**. That leaves about $500 for a custom socket breakout PCB, a bench supply or SMU-lite for VCC/ICC, and a temperature fixture.
- **Ultra-low-cost:** FT2232H module $29 + socket $51–60 + chips ≈ **$100–150**, with NANDReader_FTDI-style software. Timing control is coarse.

**Chip choice caveat.** SLC parts are easy to buy in TSOP48, but public information shows no read-retry or reference shift on them (Micron SLC feature table; Hynix "SLC NANDs don't require read-retry"). A read-reference sweep needs an MLC/TLC part whose public interface exposes retry: Micron with read_retry_options, Macronix with reliability_func bit 0, or Hynix 1x-nm MLC.

**Interface caveat.** TSOP48 retail parts use 3.3 V async SDR at ONFI timing modes 0–5. Artix-7 HR banks can drive 3.3 V LVCMOS (general knowledge, not separately sourced here). Check bank voltage and pin count on the chosen board.

**Risk note.** Only use erase, program, OTP (Micron feature 90h; Macronix 0x90) and lock commands deliberately. OTP protection is permanent. Set Features changes on Micron parts are volatile until power cycle.

### Gaps
- No verified price for TSOP48 MLC parts that support read-retry (e.g., Micron MLC in TSOP48); I did not search distributor stock.
- No pricing for a breakout PCB, level shifting or precision current measurement. ICC-based observation is speculative.
- Live Digi-Key/Mouser prices could not be fetched directly (403s); the figures are from search snippets and may be dated.

---

### Unsuccessful searches and access failures (for the report writer)
- **onfi.org** (specs page and PDF URLs): F5 WAF "Request Rejected" / HTTP 403 for both curl and WebFetch.
- **Wayback Machine:** connection reset.
- **media-www.micron.com ONFI 4.2 URL:** 404.
- **UMich ONFI 2.2 mirror:** TLS failure, then 503.
- **jedec.org JESD230 pages:** 403 / JavaScript challenge.
- **openssd.dev:** TLS hostname mismatch. **openssd-project.org:** 404.
- **digilent.com shop:** 403.
- **saleae.com pricing:** no prices on the page.
- **GitHub searches with 0 or irrelevant results:** "litex nand flash" and "raspberry pi gpio parallel nand dump"; "user:CMU-SAFARI flash" found only CertiFlash.
- **Web searches without specific answers:** NplusT NanoCycler command or SDK details; BGA132 socket prices; user-scriptable raw-NAND command support in universal programmers; ATE prices and university programmes.
- **Not researched:** OpenExpress, Gitee and GitLab searches, XGecu programmers.
