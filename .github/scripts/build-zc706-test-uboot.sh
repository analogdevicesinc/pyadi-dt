#!/usr/bin/env bash
# Build a private JTAG U-Boot with the managed TFTP driver's port variable.
set -euo pipefail

: "${1:?Usage: build-zc706-test-uboot.sh OUTPUT_DIRECTORY}"
export CROSS_COMPILE="${CROSS_COMPILE:-arm-linux-gnueabihf-}"
command -v "${CROSS_COMPILE}gcc" >/dev/null
output=$(realpath -m "$1")
mkdir -p "$output"
work=$(mktemp -d "$output/build-XXXXXX")
revision=f06dec3cab5b3ba295a3d171527b7b45fe692469
git init -q "$work"
git -C "$work" fetch --depth 1 https://github.com/analogdevicesinc/u-boot-xlnx.git "$revision"
git -C "$work" checkout -q --detach FETCH_HEAD

python3 - "$work" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1])
header = source / "include/configs/zynq_zc70x.h"
header.write_text(header.read_text() + "\n#define CONFIG_TFTP_PORT\n")
tftp = source / "net/tftp.c"
text = tftp.read_text()
assert 'env_get("tftpdstp")' in text
tftp.write_text(text.replace('env_get("tftpdstp")', 'env_get("tftpdstport")'))
PY

make -C "$work" zynq_zc706_defconfig
make -C "$work" -j"${ADIDT_BUILD_JOBS:-8}" HOSTCFLAGS=-fcommon
cp "$work/u-boot" "$output/u-boot.elf"
git -C "$work" diff > "$output/source.patch"
{
    printf 'source_revision=%s\n' "$revision"
    "${CROSS_COMPILE}gcc" --version
    sha256sum "$output/u-boot.elf"
} > "$output/build-metadata.txt"
printf 'Set ADIDT_ZYNQ_UBOOT_IMAGE=%s on this exporter\n' "$output/u-boot.elf"
