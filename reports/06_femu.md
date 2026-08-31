# Gate 8 — FEMU: build, TCG execution, and PIM command integration

Reproduce: `make femu-build` then `make femu-guest`
(`scripts/femu_guest_run.sh`; auto-selects KVM when `/dev/kvm` exists, TCG otherwise).
Artifacts: `patches/femu_pim_gemv_and_tcg_irq.patch` (also applied in-tree),
`results/femu_guest_serial.log`.

## What was attempted, in order (per the FEMU environment rule)

1. **KVM mode**: impossible on this host — `/dev/kvm` absent (container inside a
   KVM hypervisor without nested virt exposed; verified Gate 0). FACT, evidenced,
   not assumed.
2. **Build**: FEMU @ pinned 34bbe45 built with its official scripts
   (`pkgdep.sh` + `femu-compile.sh`), exit 0.
3. **TCG smoke test** (Gate 0): device initializes
   (`vCSD0,CSD mode initialized`), machine runs.
4. **Full TCG guest run** (this gate): custom minimal guest (Ubuntu 6.8 kernel +
   busybox initramfs + nvme-cli), FEMU CSD device with pg_rd_lat=3000ns.

## PIM command added (minimum set from Gate 4)

`NVME_CMD_CSD_PIM_GEMV` (opcode 0x9A) in FEMU's computational-storage mode:
- **Input broadcast**: via the existing `WRITE_AFDM` path (AFDM id in cdw13;
  all-ones vector when 0) — matching the architecture's channel-broadcast input.
- **NAND-local weight processing**: per-page reduction computed inside the
  device model against the NAND backend data (weights never DMA to the host).
- **Partial-result return**: n_pages × 4B partials via PRP — the only data
  leaving the "die".
- **Timing**: charges FEMU's *modeled* device time with the Gate-2-calibrated
  window model: `op = (tR + compute) + n_pages × (max(tR, compute) + dies/ch × 290ns)`,
  applied to `req->expire_time` (completion released by FEMU's pqueue at
  modeled time — never host wall clock). The modeled nanoseconds are also
  returned in `cqe.result` so a guest can cross-check the model under TCG,
  where wall-clock ratios are meaningless.

## Two real FEMU bugs found and fixed (both in the patch)

1. **Pure-CSD mode never completes IO** (accelerator-independent): the poller
   enqueues every IO request to the `to_ftl[]` ring, but
   `femu_needs_ftl_thread()` only started the FTL/completion thread for
   BBSSD/ZNS namespaces → in CSD-only configs the ring is never drained and
   every IO times out (reproduced: guest `I/O QID timeout, reset controller`).
   Fix: CSD namespaces also start the FTL thread (`femu_ftl_process_req`
   returns lat=0 for CSD; CSD handlers self-charge latency via `expire_time` —
   consistent with the mode's design).
2. **TCG interrupt delivery**: with no KVM, the irqfd route fails (by design)
   and FEMU falls back to `msix_notify()` — called from FEMU's poller threads
   *without the BQL*, which under TCG drops/races the MSI-X write. Fix: the
   legacy notify path takes `bql_lock()` when not already held.
   (Isolation test: the same guest against QEMU's stock `-device nvme` in the
   same binary worked, pinning the fault to FEMU's poller path.)

## Result (TCG, this host)

```
K3TEST: pattern written                      <- weights via normal NVMe write
K3TEST: passthru-binary rc=0                 <- PIM_GEMV opcode 0x9A accepted
K3TEST: PARTIALS PASS                        <- all 8 partials BIT-EXACT vs host-computed
IO Command Vendor Specific ... result: 0x000097b8
K3TEST: expected modeled ns = 38840 (0x97b8) <- FEMU-charged modeled time ==
                                                Python window model, exactly
```

End-to-end through a real guest kernel + NVMe driver + nvme-cli: weights stay
in the device, partials return, and the FEMU-modeled latency for 8 pages at
tR=3µs, 4 dies/channel, 2.56µs compute equals the calibrated analytic model to
the nanosecond (fill 5 560 ns + 8 × 4 160 ns = 38 840 ns).

## Cross-check status and honest limits

- FEMU here validates the *command/data/timing plumbing* of the PIM design and
  that the analytic window model transfers into an event-driven SSD emulator
  unchanged. It does NOT prove any capability exists in real Micron NAND
  (project rule; that is BABOL's job) and TCG forbids wall-clock throughput
  claims — modeled time only, which is what we used.
- Multi-plane concurrency in FEMU CSD is limited (`pls_per_lun=1` upstream);
  plane-level parallelism is represented by LUNs for timing purposes. The
  Python simulator + MQSim (Gate 2) remain the quantitative sources; FEMU is
  the functional integration proof.
- On a KVM host, `scripts/femu_guest_run.sh` runs identically with
  hardware acceleration (one command; auto-detected).
