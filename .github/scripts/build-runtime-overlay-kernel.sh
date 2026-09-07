#!/usr/bin/env bash
# Build private test artifacts; SOURCE must be a disposable ADI Linux checkout.
set -euo pipefail
if (( $# < 3 || $# > 4 )); then
    echo "Usage: $0 SOURCE OUTPUT {zynq|microblaze} [STOCK_INITRAMFS.cpio.gz]" >&2
    exit 2
fi
source_dir=$(realpath "$1")
mkdir -p "$2"
output_dir=$(realpath "$2")
repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
patch_file="$repo_dir/.github/patches/jesd204-skip-unregistered-callbacks.patch"
case "$3" in
    zynq)
        export ARCH=arm
        : "${CROSS_COMPILE:=arm-linux-gnueabihf-}"
        defconfig=zynq_xcomm_adv7511_defconfig
        ;;
    microblaze)
        (( $# == 4 )) || { echo "MicroBlaze requires the stock initramfs" >&2; exit 2; }
        rootfs=$(realpath "$4")
        export ARCH=microblaze
        : "${CROSS_COMPILE:=microblazeel-xilinx-linux-gnu-}"
        defconfig=adi_mb_defconfig
        ;;
    *) echo "Unsupported architecture: $3" >&2; exit 2 ;;
esac
export CROSS_COMPILE
command -v "${CROSS_COMPILE}gcc" >/dev/null
if ! patch --dry-run --reverse --batch -d "$source_dir" -p1 < "$patch_file" >/dev/null 2>&1; then
    patch --forward --batch -d "$source_dir" -p1 < "$patch_file"
fi
make -C "$source_dir" O="$output_dir" "$defconfig"
"$source_dir/scripts/config" --file "$output_dir/.config" \
    --enable MODULES --enable MODULE_UNLOAD --module IIO --module JESD204 \
    --module COMMON_CLK_AXI_CLKGEN \
    --enable OF_OVERLAY --enable OF_CONFIGFS --enable CONFIGFS_FS \
    --enable IKCONFIG --enable IKCONFIG_PROC \
    --set-str LOCALVERSION '-adidt-modular' \
    --disable ADAR1000 --disable AD7944 --disable MATHWORKS_IP_CORE
# These three unused drivers in the pinned ARM defconfig cannot build with
# modular IIO (syntax, namespace import, and built-in/module dependency bugs).
if [[ "$ARCH" == microblaze ]]; then
    "$source_dir/scripts/config" --file "$output_dir/.config" \
        --set-str INITRAMFS_SOURCE "$rootfs"
    cp "$repo_dir/test/hw/xsa/ref_data/vcu118_fmcdaq3_runtime.dts" \
        "$source_dir/arch/microblaze/boot/dts/"
fi
make -C "$source_dir" O="$output_dir" olddefconfig
make -C "$source_dir" O="$output_dir" -j"${JOBS:-8}" modules
make -C "$source_dir" O="$output_dir" \
    INSTALL_MOD_PATH="$output_dir/modules-root" INSTALL_MOD_STRIP=1 modules_install
tar -C "$output_dir/modules-root" -czf "$output_dir/modules.tar.gz" lib
if [[ "$ARCH" == microblaze ]]; then
    # Preserve device nodes/ownership in the original archive. Extracting and
    # repacking it as an ordinary user loses /dev/console. Linux accepts the
    # concatenated cpio archives; append only the new module tree.
    (
        gzip -dc "$rootfs"
        cd "$output_dir/modules-root"
        find lib/modules -print0 | cpio --null -o --format=newc --owner=0:0
    ) | gzip -1 > "$output_dir/rootfs-with-modules.cpio.gz"
    "$source_dir/scripts/config" --file "$output_dir/.config" \
        --set-str INITRAMFS_SOURCE "$output_dir/rootfs-with-modules.cpio.gz"
    make -C "$source_dir" O="$output_dir" -j"${JOBS:-8}" DTC_FLAGS=-@ \
        simpleImage.vcu118_fmcdaq3_runtime
    cp "$output_dir/arch/microblaze/boot/simpleImage.vcu118_fmcdaq3_runtime.strip" \
        "$output_dir/simpleImage.vcu118_fmcdaq3_runtime.strip"
else
    make -C "$source_dir" O="$output_dir" -j"${JOBS:-8}" LOADADDR=0x8000 uImage
    cp "$output_dir/arch/arm/boot/uImage" "$output_dir/uImage"
fi
cp "$output_dir/.config" "$output_dir/kernel.config"
sha256sum "$output_dir/modules.tar.gz"
