# SN740 vendor-command probe

Disciplined differential probe of the WD SN740's vendor ADMIN opcodes
(`0xE2 0xE4 0xE6 0xE9 0xEA 0xF1 0xFA`) over `nvme admin-passthru`, using the
controller's completion status as an oracle to recover each opcode's field
grammar.

> **Runs on your Dell/Ubuntu box, not in any cloud session.**
> **Target must be the SACRIFICIAL secondary SN740 — never the boot/data drive.**

## Why it's built the way it is

The safety ordering *is* the methodology — it's what makes a run yield data
instead of a dead drive on command #3:

| Guard | Effect |
|---|---|
| **Dry-run by default** | Nothing is sent until `--execute`; otherwise it only prints the `nvme` command it *would* run. |
| **Read direction only** | Writes can erase/brick; need `--allow-write`, still refused for destructive opcodes. |
| **Hard block** | `0xE5` (flagged **LBCC** in this drive's effects log) can never be sent. |
| **Liveness checkpoints** | Re-identifies the drive every N commands; aborts the instant it stops answering, naming the last command. |
| **JSONL log** | Every attempt (opcode, CDW10–15, len, status, data hash) is logged for audit/replay. |

## Method (coordinate-descent, not brute force)

1. `fa-characterize` — reproduce the **confirmed-good FA** command, then sweep its
   CDW10 selector. Learn WD's field conventions from a command that already
   returns `Success`.
2. `baseline` — send the all-zero opcode once (EA baseline returns *Invalid Field*,
   which already proves the transport works).
3. `sweep-cdw10` — sweep the sub-selector `0x00..0xFF`; a status **other than**
   `Invalid Field (0x4002)` is signal.
4. `sweep-field` — resolve each remaining CDW for a live selector.

## Examples

```bash
# Preview only (nothing sent) — see exactly what would go to the drive:
sudo python3 sn740_vendor_probe.py --dev /dev/nvme1 --mode sweep-cdw10 --opcode 0xEA

# Learn conventions from the known-good FA command, for real:
sudo python3 sn740_vendor_probe.py --dev /dev/nvme1 --mode fa-characterize --execute

# EA sub-selector sweep, for real, liveness check every 8 commands:
sudo python3 sn740_vendor_probe.py --dev /dev/nvme1 --mode sweep-cdw10 \
    --opcode 0xEA --data-len 512 --checkpoint 8 --execute
```

## Honest expectations

The oracle is coarse (`Invalid Field` doesn't say *which* field), and fields may
be validated jointly — so seed sweeps from the FA envelope, not from zero, and use
returned-length/timing as secondary signals. Most likely outcome: EA resolves to a
**diagnostic/log/config** function, not a NAND-compute primitive. That's still a
useful, bounded result — it's the clean test of whether the stock firmware exposes
anything before committing to an open-controller platform (OpenSSD), which is very
likely the better route for in-flash compute anyway.

Status parsing is tuned for common `nvme-cli` output; verify against one real
command and adjust `parse_status()` if your version differs.
