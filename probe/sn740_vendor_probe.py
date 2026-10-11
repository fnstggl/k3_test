#!/usr/bin/env python3
"""
sn740_vendor_probe.py
=====================
Disciplined differential probe of WD SN740 vendor ADMIN opcodes via nvme-cli
admin-passthru, using the controller's completion status as an oracle.

  *** RUNS ON YOUR DELL / UBUNTU BOX, not in any cloud session. ***
  *** TARGET MUST BE THE SACRIFICIAL SECONDARY SN740 - never the boot/data drive. ***

Design principles (the safety ordering is what makes this yield DATA instead of a
dead drive on command #3):

  1. DRY-RUN BY DEFAULT. Nothing is sent until you pass --execute. Without it the
     tool only prints the exact nvme-cli command it *would* run.
  2. READ DIRECTION ONLY by default. Writes can erase/brick; they require
     --allow-write AND are still refused for opcodes flagged destructive.
  3. HARD BLOCK on effects-log-destructive opcodes (0xE5 = LBCC on this drive).
  4. LIVENESS CHECKPOINTS. The drive is re-identified every N commands; if it
     stops answering the run aborts immediately so you can power-cycle and see
     exactly which command was last sent.
  5. FULL JSONL LOG. Every attempt (opcode, all CDWs, len, status, data hash) is
     appended to a log so the run is reconstructable and the oracle is auditable.

Method: coordinate-descent. Find the sub-selector (usually CDW10 low byte), then
resolve each remaining field, watching for status != "Invalid Field (0x4002)".
Start by characterizing the KNOWN-GOOD FA command to learn WD's field conventions,
then apply them as a prior to EA and the other vendor opcodes.

Requires: Linux, root, nvme-cli (`sudo apt install nvme-cli`).
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

# --- Facts from the SN740 Command Effects Log the operator supplied -----------
VENDOR_ADMIN_OPCODES = [0xE2, 0xE4, 0xE5, 0xE6, 0xE9, 0xEA, 0xF1, 0xFA]
# 0xE5 is flagged LBCC (Logical Block Content Change): it can mutate stored data.
# Hard-blocked from being sent by this tool at all.
DESTRUCTIVE_OPCODES = {0xE5}
# FA (DUI / vs-internal-log) is experimentally confirmed to return Success.
KNOWN_GOOD_FA = dict(opcode=0xFA, nsid=0xFFFFFFFF, cdw10=0xFF, cdw14=1, data_len=1024)

# --- NVMe completion status codes used as the oracle --------------------------
STATUS_SUCCESS = 0x0
STATUS_INVALID_OPCODE = 0x1  # generic status (SCT 0) - command not supported
STATUS_INVALID_FIELD = 0x2   # generic status (SCT 0) - a field value is bad
# nvme-cli prints the full 11-bit "SCT<<8 | SC" sometimes (e.g. 0x4002). We mask SC.


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def build_cmd(dev, opcode, nsid, cdw, data_len, direction, timeout_ms, dry_run):
    """Construct the nvme-cli admin-passthru argv."""
    cmd = [
        "nvme", "admin-passthru", dev,
        f"--opcode={opcode:#x}",
        f"--namespace-id={nsid:#x}",
        f"--cdw10={cdw[0]:#x}", f"--cdw11={cdw[1]:#x}",
        f"--cdw12={cdw[2]:#x}", f"--cdw13={cdw[3]:#x}",
        f"--cdw14={cdw[4]:#x}", f"--cdw15={cdw[5]:#x}",
        f"--timeout={timeout_ms}",
    ]
    if data_len:
        cmd.append(f"--data-len={data_len}")
    if direction == "read":
        cmd.append("--read")
    elif direction == "write":
        cmd.append("--write")
    cmd.append("--raw-binary")  # emit returned buffer to stdout as bytes
    if dry_run:
        cmd.append("--dry-run")
    return cmd


_STATUS_RE = re.compile(r"\((0x[0-9a-fA-F]+)\)")


def parse_status(returncode, stderr_text):
    """
    Return (status_code_or_None, label). nvme-cli prints e.g.
    'NVMe status: INVALID_FIELD: ... (0x4002)' on a CQE error, and a success
    line otherwise. Parsing varies by nvme-cli version - verify against one
    real command and adjust if needed.
    """
    if "Success" in stderr_text or "SUCCESS" in stderr_text:
        return STATUS_SUCCESS, "SUCCESS"
    m = _STATUS_RE.search(stderr_text)
    if m:
        full = int(m.group(1), 16)
        return full, f"0x{full:04x}"
    # Fall back to process return code (nvme-cli often returns the status code).
    if returncode == 0:
        return STATUS_SUCCESS, "SUCCESS(rc0)"
    return None, f"rc={returncode}"


def send_admin(dev, opcode, nsid=0xFFFFFFFF, cdw=(0, 0, 0, 0, 0, 0),
               data_len=0, direction="read", timeout_ms=2000,
               dry_run=True, allow_write=False):
    """Send one admin command (or preview it). Returns a result dict."""
    if opcode in DESTRUCTIVE_OPCODES:
        sys.exit(f"REFUSED: opcode {opcode:#x} is flagged destructive (LBCC) in the "
                 f"effects log. Not sendable by this tool.")
    if direction != "read" and not allow_write:
        sys.exit("REFUSED: non-read direction needs --allow-write (writes can "
                 "erase/brick the drive).")

    argv = build_cmd(dev, opcode, nsid, cdw, data_len, direction, timeout_ms, dry_run)
    rec = {
        "ts": now_iso(), "opcode": opcode, "nsid": nsid, "cdw": list(cdw),
        "data_len": data_len, "direction": direction, "dry_run": dry_run,
        "argv": " ".join(argv),
    }
    if dry_run:
        rec["status"] = "DRY_RUN"
        return rec

    try:
        proc = subprocess.run(argv, capture_output=True,
                              timeout=timeout_ms / 1000 + 10)
    except subprocess.TimeoutExpired:
        rec["status"] = "TIMEOUT"
        return rec
    data = proc.stdout or b""
    stderr_text = (proc.stderr or b"").decode("utf-8", "replace")
    code, label = parse_status(proc.returncode, stderr_text)
    rec["status_code"] = code
    rec["status"] = label
    rec["data_len_returned"] = len(data)
    rec["data_sha256"] = hashlib.sha256(data).hexdigest() if data else None
    rec["data_head_hex"] = data[:64].hex() if data else None
    rec["nonzero_data"] = any(data) if data else False
    return rec


def alive(dev):
    """Liveness check: the drive must still answer a standard Identify Controller."""
    r = subprocess.run(["nvme", "id-ctrl", dev], capture_output=True)
    return r.returncode == 0


def log_row(logf, rec):
    logf.write(json.dumps(rec) + "\n")
    logf.flush()


def is_signal(rec):
    """Oracle: anything that is NOT the baseline 'Invalid Field' rejection is
    worth a human's attention - Success, returned data, or a *different* error."""
    if rec.get("status") in ("DRY_RUN",):
        return False
    code = rec.get("status_code")
    if code == STATUS_INVALID_FIELD or code == 0x4002:
        return False
    return True


def run_sweep(dev, opcode, field_index, values, base_cdw, data_len, args, logf):
    """Sweep one CDW field across `values`, hold the rest at base_cdw."""
    hits = []
    sent = 0
    for v in values:
        cdw = list(base_cdw)
        cdw[field_index] = v
        if args.execute and sent and sent % args.checkpoint == 0:
            if not alive(dev):
                print(f"\n!! DRIVE NOT RESPONDING after {sent} cmds "
                      f"(last cdw{10+field_index}={v:#x}). Aborting; power-cycle it.")
                log_row(logf, {"ts": now_iso(), "event": "LIVENESS_ABORT",
                               "after": sent, "last_value": v})
                sys.exit(2)
        rec = send_admin(dev, opcode, nsid=args.nsid, cdw=tuple(cdw),
                         data_len=data_len, direction=args.direction,
                         timeout_ms=args.timeout, dry_run=not args.execute,
                         allow_write=args.allow_write)
        log_row(logf, rec)
        sent += 1
        if is_signal(rec):
            hits.append(rec)
            print(f"  [SIGNAL] cdw{10+field_index}={v:#010x} -> {rec['status']}"
                  f"  ret={rec.get('data_len_returned')}B"
                  f"  nonzero={rec.get('nonzero_data')}")
        if args.execute and args.delay:
            time.sleep(args.delay)
    return hits, sent


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dev", required=True,
                    help="e.g. /dev/nvme1 -- the SACRIFICIAL SN740, NOT the boot drive")
    ap.add_argument("--mode", required=True,
                    choices=["fa-characterize", "baseline", "sweep-cdw10", "sweep-field"],
                    help="fa-characterize: map the known-good FA command first. "
                         "baseline: send the all-zero opcode once. "
                         "sweep-cdw10: 0x00..0xFF selector sweep. "
                         "sweep-field: sweep one field over a range.")
    ap.add_argument("--opcode", type=lambda s: int(s, 0), default=0xEA)
    ap.add_argument("--nsid", type=lambda s: int(s, 0), default=0xFFFFFFFF)
    ap.add_argument("--data-len", dest="data_len", type=lambda s: int(s, 0), default=512)
    ap.add_argument("--direction", choices=["none", "read", "write"], default="read")
    ap.add_argument("--field", type=int, default=0, help="0=CDW10 .. 5=CDW15")
    ap.add_argument("--range", default="0:256",
                    help="start:stop[:step] for sweep-field (hex ok, e.g. 0x0:0x10000:0x100)")
    ap.add_argument("--base-cdw", default="0,0,0,0,0,0",
                    help="comma CDW10..15 held while sweeping (hex ok)")
    ap.add_argument("--timeout", type=int, default=2000, help="per-command ms")
    ap.add_argument("--checkpoint", type=int, default=16, help="liveness every N cmds")
    ap.add_argument("--delay", type=float, default=0.0, help="sleep between cmds (s)")
    ap.add_argument("--log", default="probe_log.jsonl")
    ap.add_argument("--execute", action="store_true",
                    help="ACTUALLY SEND. Without this, commands are only printed.")
    ap.add_argument("--allow-write", action="store_true",
                    help="permit --direction write (NOT for destructive opcodes)")
    args = ap.parse_args()

    if args.direction == "none":
        args.direction = None

    mode_banner = "EXECUTE" if args.execute else "DRY-RUN (nothing sent)"
    print(f"== sn740_vendor_probe == dev={args.dev} mode={args.mode} "
          f"opcode={args.opcode:#x} [{mode_banner}] ==")
    if args.execute:
        print("   Sending real commands to", args.dev,
              "- confirm this is the SACRIFICIAL drive.")

    def parse_cdw(s):
        return tuple(int(x, 0) for x in s.split(","))

    with open(args.log, "a") as logf:
        log_row(logf, {"ts": now_iso(), "event": "RUN_START", "args": vars(args)})

        if args.mode == "fa-characterize":
            # Reproduce the confirmed-good FA command, then vary its selector so you
            # can SEE the structure of a command that already returns Success.
            print("Reproducing confirmed FA command, then sweeping its CDW10 selector:")
            base = (KNOWN_GOOD_FA["cdw10"], 0, 0, 0, KNOWN_GOOD_FA["cdw14"], 0)
            r0 = send_admin(args.dev, 0xFA, nsid=KNOWN_GOOD_FA["nsid"], cdw=base,
                            data_len=KNOWN_GOOD_FA["data_len"], direction="read",
                            timeout_ms=args.timeout, dry_run=not args.execute)
            log_row(logf, r0)
            print("  FA known-good ->", r0.get("status"),
                  "ret", r0.get("data_len_returned"), "B")
            hits, sent = run_sweep(args.dev, 0xFA, 0, range(0x100),
                                   (0, 0, 0, 0, KNOWN_GOOD_FA["cdw14"], 0),
                                   KNOWN_GOOD_FA["data_len"], args, logf)
            print(f"FA selector sweep: {len(hits)} live selectors / {sent} sent.")

        elif args.mode == "baseline":
            rec = send_admin(args.dev, args.opcode, nsid=args.nsid,
                             cdw=(0, 0, 0, 0, 0, 0), data_len=args.data_len,
                             direction=args.direction or "read",
                             timeout_ms=args.timeout, dry_run=not args.execute)
            log_row(logf, rec)
            print("baseline ->", rec.get("status"), rec.get("argv"))

        elif args.mode == "sweep-cdw10":
            hits, sent = run_sweep(args.dev, args.opcode, 0, range(0x100),
                                   parse_cdw(args.base_cdw), args.data_len, args, logf)
            print(f"CDW10 selector sweep: {len(hits)} signals / {sent} sent.")

        elif args.mode == "sweep-field":
            parts = [int(x, 0) for x in args.range.split(":")]
            start, stop = parts[0], parts[1]
            step = parts[2] if len(parts) > 2 else 1
            vals = range(start, stop, step)
            hits, sent = run_sweep(args.dev, args.opcode, args.field, vals,
                                   parse_cdw(args.base_cdw), args.data_len, args, logf)
            print(f"field CDW{10+args.field} sweep: {len(hits)} signals / {sent} sent.")

        log_row(logf, {"ts": now_iso(), "event": "RUN_END"})
    print(f"Log: {args.log}")


if __name__ == "__main__":
    main()
