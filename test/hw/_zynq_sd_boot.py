"""Boot another release's design on a Zynq-7000 rig that boots its own SD card.

The card's boot files are left as they are. The bitstream, kernel and device
tree go into ``/boot/adidt`` beside them and are loaded by hand from the
card's U-Boot, so an ordinary power-on still boots the stock system.
"""

from __future__ import annotations

import shlex
import re
import time
import zlib
from pathlib import Path

from test.hw._zynqmp_boot import _uboot_command, serve_directory
from test.hw.hw_helpers import mark_dtb_for_boot, shell_out

_BITSTREAM_ADDRESS = "0x8000000"
_FOLDER = "adidt"


def _cached_name(path: Path) -> str:
    """Name the card keeps *path* under; changes whenever its content does."""
    return f"{path.name}-{zlib.crc32(path.read_bytes()):08x}"


def _stage_on_sd(shell, directory: Path, files: dict[str, Path]) -> None:
    """Download *files* (card name -> local path) that the card lacks."""
    links = []
    try:
        with serve_directory(directory) as url:
            shell.run_check(
                "i=0; until ip -4 -o addr show scope global | grep -q 'inet '; "
                "do i=$((i+1)); test $i -lt 90 || exit 1; sleep 1; done",
                timeout=120,
            )
            shell.run_check(f"mountpoint -q /boot && mkdir -p /boot/{_FOLDER}")
            keep = " ".join(f"! -name {shlex.quote(name)}" for name in files)
            shell.run_check(f"find /boot/{_FOLDER} -type f {keep} -delete")
            for name, source in files.items():
                link = directory / name
                if not link.exists():
                    link.symlink_to(source.resolve())
                    links.append(link)
                target = f"/boot/{_FOLDER}/{name}"
                shell.run_check(
                    f"test -s {target} || {{ wget -q -O {target}.part {url}/{name} "
                    f"&& mv {target}.part {target}; }}",
                    timeout=600,
                )
            shell.run_check("sync")
    finally:
        for link in links:
            link.unlink(missing_ok=True)


def boot_release_design_from_sd(board, dtb: Path, bitstream: Path, kernel: Path):
    """Boot *kernel* with *dtb* on *bitstream*; return the Linux shell.

    The card's own system boots first to receive the files and to supply the
    kernel command line, then the board is power-cycled and stopped in U-Boot.
    """
    if type(board).__name__ != "BootFPGASoCTFTP" or not board.sd_autoboot:
        raise ValueError("Release SD boot requires an sd-autoboot BootFPGASoCTFTP")
    marker = mark_dtb_for_boot(dtb)
    names = {
        "bitstream": _cached_name(bitstream),
        "kernel": _cached_name(kernel),
        "dtb": _cached_name(dtb),
    }
    board.transition("shell")
    shell = board.target.get_driver("ADIShellDriver")
    bootargs = shell_out(shell, "cat /proc/cmdline").strip()
    assert bootargs and "'" not in bootargs, f"Unusable stock bootargs: {bootargs!r}"
    _stage_on_sd(
        shell,
        dtb.parent,
        {names["bitstream"]: bitstream, names["kernel"]: kernel, names["dtb"]: dtb},
    )

    console = shell.console
    board.power.off()
    time.sleep(5)
    board.power.on()
    console.expect("Hit any key to stop autoboot", timeout=60)
    console.sendline("")
    console.expect(board.uboot_prompt, timeout=10)

    folder, kernel_addr, dtb_addr = _FOLDER, board.kernel_addr, board.dtb_addr
    _uboot_command(
        board,
        f"fatload mmc 0 {_BITSTREAM_ADDRESS} {folder}/{names['bitstream']} && "
        f"fpga loadb 0 {_BITSTREAM_ADDRESS} $filesize",
    )
    result = _uboot_command(
        board,
        f"fatload mmc 0 {kernel_addr} {folder}/{names['kernel']} && "
        f"crc32 {kernel_addr} $filesize",
    )
    loaded = re.search(r"==>\s*([0-9a-fA-F]{8})", result)
    assert loaded and int(loaded.group(1), 16) == zlib.crc32(kernel.read_bytes()), (
        result
    )
    output = _uboot_command(
        board,
        f"fatload mmc 0 {dtb_addr} {folder}/{names['dtb']} && fdt addr {dtb_addr} && "
        "fdt print / adidt,validation-id",
    )
    assert f'adidt,validation-id = "{marker}"' in output, output
    _uboot_command(board, f"setenv bootargs '{bootargs}'")
    console.sendline(f"bootm {kernel_addr} - {dtb_addr}")
    # The strategy's own wait covers the kernel banner and the login marker.
    board._boot_via_sd_autoboot()
    board.status = type(board.status).booted
    board.transition("shell")
    actual = shell_out(
        shell, "cat /proc/device-tree/adidt,validation-id | tr -d '\\000'"
    ).strip()
    assert actual == marker, f"Wrong booted DTB: expected {marker}, got {actual!r}"
    return shell
