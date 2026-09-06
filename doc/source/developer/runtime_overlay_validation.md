# Runtime JESD overlay validation

Runtime overlay tests need a different boot environment from ordinary generated-DTB
tests. The ADI JESD framework builds its topology when it loads and rejects an
overlay change while that topology is registered. A fully configured merged DTB
also conflicts with the SPI children and phandles created by the overlay.

The ZC706 and FMCDAQ3 test profiles therefore use this sequence:

1. Boot a base with the PL targets and symbols, without overlay-owned SPI children.
2. Stop iiod and unbind the AXI IIO consumers, releasing their converter references.
3. Unload all topology clients and the JESD core. Require its module and bus absent.
4. Apply the generated DTBO through configfs and verify its unique live-tree marker.
5. Load JESD, clocks, and converters; restart iiod. Require IIO, JESD DATA, and DMA.
   On FMCDAQ3, initialize TX before RX because TX owns the shared AD9528
   synchronization callbacks.
6. Quiesce/unload again before removing the overlay. Require the marker absent,
   then reload the overlay and verify devices and links again.

Busy modules, kernel faults, missing markers, and failed captures remain failures.
The harness never uses forced module removal or disables the JESD overlay guards.

## Build private test kernels

Use a disposable checkout of ADI Linux revision
`2e8908932dfd9faf40ec9220a508aa1ce02699a8` (6.1.70). The build script applies
`.github/patches/jesd204-skip-unregistered-callbacks.patch` to that checkout.
That kernel needs lifetime fixes for callbacks to already unregistered clients
and repeated device cleanup during JESD module exit. Keep this patch with the
kernel artifacts; installing the Python package does not patch a board's kernel.

Put the matching cross compiler, make, DTC, patch, depmod, and cpio on PATH:

```sh
# ARM Linux cross compiler on PATH; source/output are private directories.
bash .github/scripts/build-runtime-overlay-kernel.sh "$linux_src" "$overlay_build" zynq

# Little-endian MicroBlaze Linux cross compiler on PATH.
bash .github/scripts/build-runtime-overlay-kernel.sh \
    "$linux_src" "$overlay_build" microblaze "$stock_initramfs"
```

The script enables configfs overlays and module unloading, makes IIO/JESD clients
modules, and retains the resolved `kernel.config`. Three unrelated drivers in the
pinned ARM defconfig are disabled because they do not build with modular IIO:
ADAR1000, AD7944, and MathWorks IP core.

For MicroBlaze, the input is the matching reference `cpio.gz` initramfs. The script
appends the new modules to the original archive, preserving its device nodes and
ownership without root access. It builds the supplied
`test/hw/xsa/ref_data/vcu118_fmcdaq3_runtime.dts` wrapper, which retains the reference
carrier, exposes XSA-name aliases, and removes the SPI children owned by the overlay.
Use the matching reference FPGA bitstream.

## Select artifacts for labgrid

ZC706 test boots prepare their private runtime base automatically from the merged
tree and DTBO. The kernel override is a runner-local file. The harness stages it
under the basename requested by U-Boot, even if the override has a custom filename.

```sh
export ADIDT_OVERLAY_KERNEL_IMAGE_ZYNQ="$overlay_build/uImage"
export ADIDT_OVERLAY_MODULES_ARCHIVE="$overlay_build/modules.tar.gz"
export ADIDT_OVERLAY_MODULES_HOST=RUNNER_LAB_IPV4
```

The harness serves only this archive on a temporary HTTP port, computes its SHA256,
and shuts down the server at fixture teardown (including after a failed test).
The board must be able to reach the runner's chosen interface and port. For an
existing artifact server, use `ADIDT_OVERLAY_MODULES_URL` together with
`ADIDT_OVERLAY_MODULES_SHA256` instead of the local archive option.

The board verifies the checksum and extracts the bundle under
`/tmp/adidt-overlay-modules`; `modprobe -d` uses it without replacing SD-card modules.
The archive must contain `lib/modules/<running-kernel-release>/` and depmod indexes.
For a preinstalled or embedded matching module tree, leave the archive and both
URL variables unset.

MicroBlaze's kernel and module tree are one JTAG image. Copy the output to the
exporter and set its absolute exporter-side path:

```sh
export ADIDT_OVERLAY_FABRIC_KERNEL_IMAGE=/private/simpleImage.vcu118_fmcdaq3_runtime.strip
```

These overlay-specific overrides leave ordinary boot tests on their normal kernels,
so both test modules can run in one pytest invocation.

Acquire the appropriate place through the coordinator, prepare `LG_ENV`, and run
the board's complete six-test overlay module. Retain its JUnit and serial/kernel
logs. A configfs `applied` status alone is not proof of an applied overlay.

The pinned kernel warns that changes to properties of boot-time nodes may leak
memory when an overlay is removed. These tests validate a bounded lifecycle on a
fresh boot; they do not qualify unlimited overlay cycling for production use.


## Provisioned release runners

The 2026-09-05 validated kernels/modules are installed under
`~/.cache/adidt/runtime/2026-09-05/` on `bq`, `nemo`, and `nuc`.
`prepare-hardware-env.sh` loads the selected board's runner-local configuration
from `~/.config/pyadi-dt/hardware/$BOARD-$CARRIER.env` (override the directory
with `ADIDT_HARDWARE_CONFIG_DIR`). Installed configurations are:

- `bq`: `adrv9371-zc706.env`, including the private TFTP-capable U-Boot.
- `nemo`: `adrv9009-zc706.env`, including the private TFTP-capable U-Boot.
- `nuc`: `daq3-vcu118.env`, selecting the complete MicroBlaze runtime image.

These files use shell default expansions so explicit artifact overrides remain
possible. Shared stock boot images and coordinator tags are preserved. Kernel
rebuilds require updating the matching module bundle as a unit.
