#!/usr/bin/env bash
# Gate 8: run the PIM_GEMV functional test in a FEMU CSD guest.
# Works under TCG (slow) or KVM (-accel kvm if /dev/kvm exists).
# Prereqs: make femu-build; apt install busybox-static nvme-cli zstd linux-image-virtual
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRATCH="${SCRATCH:-/tmp/k3nand-scratch}"; mkdir -p "$SCRATCH"
KV="$(ls /lib/modules | sort -V | tail -1)"
IR="$SCRATCH/initramfs"; rm -rf "$IR"
mkdir -p "$IR"/{bin,sbin,usr/sbin,usr/bin,proc,sys,dev,lib/modules,etc}
cp /bin/busybox "$IR/bin/"
for a in sh mount insmod sleep dd hexdump cat echo poweroff cmp grep ls sed head; do ln -sf busybox "$IR/bin/$a"; done
cp /usr/sbin/nvme "$IR/usr/sbin/"
for lib in $(ldd /usr/sbin/nvme | grep -oE '/[^ ]+'); do mkdir -p "$IR$(dirname "$lib")"; cp "$lib" "$IR$(dirname "$lib")/"; done
for m in $(find "/lib/modules/$KV/kernel/drivers/nvme" -name '*.ko*'); do
  b="$(basename "$m")"; case "$b" in *.zst) zstd -dcq "$m" > "$IR/lib/modules/${b%.zst}";; *) cp "$m" "$IR/lib/modules/";; esac
done
python3 - "$IR" <<'EOF'
import sys
ir = sys.argv[1]
pat = bytearray(); exp = []
for p in range(8):
    acc = 0
    for i in range(2048):
        b = ((i + p*11) * (i + 7)) & 0xFF
        pat.append(b); acc = (acc + b) & 0xFFFFFFFF
    exp.append(acc)
open(f"{ir}/pattern.bin","wb").write(pat)
open(f"{ir}/expected_partials.txt","w").write("".join(f"{e:08x}\n" for e in exp))
EOF
cp "$ROOT/scripts/femu_guest_init.sh" "$IR/init" && chmod +x "$IR/init"
(cd "$IR" && find . | sed 's|^\./||' | grep -v '^\.$' | cpio -o -H newc --quiet | gzip -1) > "$SCRATCH/k3_initramfs.cpio.gz"
ACCEL=tcg; [ -e /dev/kvm ] && ACCEL=kvm
"$ROOT/third_party/FEMU/build-femu/qemu-system-x86_64" \
  -machine q35 -accel $ACCEL -m 2G -smp 2 -display none -monitor none \
  -kernel "/boot/vmlinuz-$KV" -initrd "$SCRATCH/k3_initramfs.cpio.gz" \
  -append "console=ttyS0 rdinit=/init nokaslr panic=-1" -no-reboot \
  -serial file:"$SCRATCH/guest_serial.log" \
  -device femu,devsz_mb=256,namespaces=1,femu_mode=4,secsz=512,secs_per_pg=8,pgs_per_blk=256,blks_per_pl=32,pls_per_lun=1,luns_per_ch=8,nchs=8,pg_rd_lat=3000,pg_wr_lat=100000,blk_er_lat=2000000,ch_xfer_lat=0,gc_thres_pcent=75,gc_thres_pcent_high=95,fdm_size=64,nr_cu=4,nr_thread=4,time_slice=200000,context_switch_time=200,csf_runtime_scale=3
grep K3TEST "$SCRATCH/guest_serial.log"
