#!/bin/sh
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
mount -t proc none /proc
mount -t sysfs none /sys
mount -t devtmpfs none /dev 2>/dev/null
echo "K3TEST: boot ok"
insmod /lib/modules/nvme-keyring.ko 2>/dev/null
insmod /lib/modules/nvme-auth.ko 2>/dev/null
insmod /lib/modules/nvme-core.ko && echo "K3TEST: nvme-core loaded"
insmod /lib/modules/nvme.ko && echo "K3TEST: nvme loaded"
i=0; while [ ! -b /dev/nvme0n1 ] && [ $i -lt 90 ]; do sleep 1; i=$((i+1)); done
if [ ! -b /dev/nvme0n1 ]; then echo "K3TEST: NO NVME DEVICE"; ls /dev | head -20; poweroff -f; fi
echo "K3TEST: nvme0n1 present"
dd if=/pattern.bin of=/dev/nvme0n1 bs=2048 count=8 conv=fsync 2>/dev/null && echo "K3TEST: pattern written"
nvme io-passthru /dev/nvme0n1 --opcode=0x9a --namespace-id=1 --cdw10=8 --cdw11=2560 --cdw12=4 --cdw13=0 --cdw14=0 --cdw15=0 --data-len=32 -r -b > /partials.bin 2>/err1.txt
echo "K3TEST: passthru-binary rc=$?"; cat /err1.txt
hexdump -e '1/4 "%08x\n"' /partials.bin > /got.txt
echo "K3TEST: got partials:"; cat /got.txt
echo "K3TEST: exp partials:"; cat /expected_partials.txt
if cmp -s /got.txt /expected_partials.txt; then echo "K3TEST: PARTIALS PASS"; else echo "K3TEST: PARTIALS FAIL"; fi
echo "K3TEST: result-line call:"
nvme io-passthru /dev/nvme0n1 --opcode=0x9a --namespace-id=1 --cdw10=8 --cdw11=2560 --cdw12=4 --cdw13=0 --cdw14=0 --cdw15=0 --data-len=32 -r 2>&1 | head -5
echo "K3TEST: expected modeled ns = 38840 (0x97b8)"
echo "K3TEST: DONE"
poweroff -f
