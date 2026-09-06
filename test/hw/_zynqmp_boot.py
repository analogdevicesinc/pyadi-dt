"""Boot a generated ZynqMP DTB from RAM using production U-Boot and SD Linux."""

from __future__ import annotations

import uuid
import re
import zlib
from pathlib import Path

from test.hw.hw_helpers import mark_dtb_for_boot, shell_out

_DTB_ADDRESS = "0x20000000"
_SREC_SIZE_PATTERN = r"Total Size\s*=\s*0x([0-9a-fA-F]+)\s*="


def _uboot_command(board, command: str) -> str:
    """Require an actual U-Boot exit status, distinct from command echo."""
    token = uuid.uuid4().hex
    board.shell.console.sendline(command + f"; echo '{token[:16]}''{token[16:]}:'$?")
    _, before, match, _ = board.shell.console.expect(
        r"\r\n" + token + r":([0-9]+)\r\n", timeout=120
    )
    output = before.decode(errors="replace")
    assert match.group(1) == b"0", f"U-Boot command failed: {output}"
    board.shell.console.expect(board.production_uboot_prompt, timeout=10)
    return output


def _srecords(data: bytes, address: int) -> bytes:
    """Encode bounded RAM data as checksummed S3 records with an S7 terminator."""
    if not data or len(data) > 2 * 1024 * 1024 or address + len(data) > 2**32:
        raise ValueError("Invalid DTB size/address for the serial RAM handoff")
    records = []
    for offset in range(0, len(data), 32):
        block = data[offset : offset + 32]
        body = bytes([len(block) + 5]) + (address + offset).to_bytes(4, "big") + block
        records.append("S3" + body.hex().upper() + f"{(~sum(body)) & 255:02X}")
    body = b"\x05" + address.to_bytes(4, "big")
    records.append("S7" + body.hex().upper() + f"{(~sum(body)) & 255:02X}")
    return ("\r\n".join(records) + "\r\n").encode()


def _upload_dtb_serial(board, dtb: Path) -> None:
    """Use U-Boot's S-record loader and verify the complete RAM payload CRC."""
    data = dtb.read_bytes()
    payload = _srecords(data, int(_DTB_ADDRESS, 16))
    _uboot_command(board, "setenv loads_echo 0")
    console = board.shell.console
    console.sendline("loads 0")
    console.expect("Ready for S-Record download", timeout=15)
    original = (console.txdelay, console.txchunk)
    # 16-byte chunks at 4 kB/s stay below the 115200-baud receive rate.
    console.txdelay, console.txchunk = 0.004, 16
    try:
        console.write(payload)
    finally:
        console.txdelay, console.txchunk = original
    _, _, match, _ = console.expect(_SREC_SIZE_PATTERN, timeout=120)
    transferred = int(match.group(1), 16)
    assert transferred == len(data), (
        f"Serial DTB size: {transferred}, expected {len(data)}"
    )
    console.expect(board.production_uboot_prompt, timeout=30)
    result = _uboot_command(board, f"crc32 {_DTB_ADDRESS} {len(data):x}")
    checksum = re.search(r"==>\s*([0-9a-fA-F]{8})", result)
    assert checksum and int(checksum.group(1), 16) == zlib.crc32(data), result


def boot_generated_zynqmp_dtb(board, dtb: Path):
    """Load the generated DTB through serial; retain the stock SD kernel/rootfs.

    The fixed RAM address is reserved for this ZU11EG test handoff. U-Boot
    validates the unique marker before boot and Linux must expose it afterward.
    A second JTAG connection can strand CPU1, so only the initial production
    bootstrap uses JTAG. No SD file or persistent U-Boot environment is written.
    The caller's board
    fixture owns power-off on every exit, including failed Linux boots.
    """
    if type(board).__name__ != "BootZynqMPJTAG":
        raise ValueError("Generated ZynqMP boot requires BootZynqMPJTAG")
    marker = mark_dtb_for_boot(dtb)
    board.transition("powered_off")
    board.transition("production_uboot_prompt")
    # Retain the production SoM boot policy;
    # cpuidle.off=1 is also present in the stock SD boot arguments.
    _uboot_command(
        board,
        "setenv bootargs console=ttyPS0,115200 earlycon clk_ignore_unused "
        "cpuidle.off=1 && setenv partid 1 && mmc dev $sdbootdev && mmcinfo && "
        "run sdroot$sdbootdev && load mmc $sdbootdev:$partid $kernel_addr Image",
    )
    _upload_dtb_serial(board, dtb)
    output = _uboot_command(
        board, f"fdt addr {_DTB_ADDRESS} && fdt print / adidt,validation-id"
    )
    assert f'adidt,validation-id = "{marker}"' in output, output
    board.shell.console.sendline(f"booti $kernel_addr - {_DTB_ADDRESS}")
    board.shell.console.expect("Starting kernel", timeout=60)
    try:
        _, boot_log, _, _ = board.shell.console.expect(
            board.kuiper_shell_marker, timeout=board.kuiper_boot_timeout
        )
    except Exception as exc:
        # Keep the boot failure actionable even when Linux never reaches a shell.
        partial = getattr(getattr(board.shell.console, "_expect", None), "before", b"")
        dtb.with_suffix(".boot-failed.log").write_bytes(partial or str(exc).encode())
        raise
    dtb.with_suffix(".boot.log").write_bytes(boot_log)
    shell = board.shell
    shell.prompt = board.kuiper_shell_marker
    shell._check_prompt()
    shell._inject_run()
    actual = shell_out(
        shell, "cat /proc/device-tree/adidt,validation-id | tr -d '\\000'"
    ).strip()
    assert actual == marker, f"Wrong booted DTB: expected {marker}, got {actual!r}"
    board.status = type(board.status).kuiper_shell
    return shell
