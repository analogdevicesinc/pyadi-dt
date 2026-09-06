"""Boot a generated ZynqMP DTB from RAM using production U-Boot and SD Linux."""

from __future__ import annotations

import uuid
from pathlib import Path

from test.hw.hw_helpers import mark_dtb_for_boot, shell_out

_DTB_ADDRESS = "0x20000000"


def _tcl_word(value: str) -> str:
    if any(c in value for c in "{}\\\r\n"):
        raise ValueError("Unsupported character in JTAG argument")
    return "{" + value + "}"


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


def boot_generated_zynqmp_dtb(board, dtb: Path):
    """Load the generated DTB through JTAG; retain the stock SD kernel/rootfs.

    The fixed RAM address is reserved for this ZU11EG test handoff. U-Boot
    validates the unique marker before boot and Linux must expose it afterward.
    No SD file or persistent U-Boot environment is written. The caller's board
    fixture owns power-off on every exit, including failed Linux boots.
    """
    if type(board).__name__ != "BootZynqMPJTAG":
        raise ValueError("Generated ZynqMP boot requires BootZynqMPJTAG")
    marker = mark_dtb_for_boot(dtb)
    board.transition("powered_off")
    board.transition("production_uboot_prompt")
    _uboot_command(
        board,
        "setenv partid 1 && mmc dev $sdbootdev && mmcinfo && "
        "run sdroot$sdbootdev && load mmc $sdbootdev:$partid $kernel_addr Image",
    )
    remote = board.jtag._stage_file(str(dtb.resolve()))
    target = _tcl_word('name =~ "' + board.a53_target_name + '"')
    script = "\n".join(
        [
            "connect -url " + _tcl_word(board.jtag_url),
            "targets -set -nocase -filter " + target,
            "stop",
            'targets -set -nocase -filter {name =~ "PSU"}',
            f"dow -force -data {_tcl_word(remote)} {_DTB_ADDRESS}",
            "targets -set -nocase -filter " + target,
            "con",
            "disconnect",
        ]
    )
    out, err, rc = board.jtag._run_xsdb(script, timeout=120)
    assert rc == 0, f"Generated DTB JTAG upload failed: {err or out}"
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
        dtb.with_suffix(".boot-failed.log").write_text(str(exc))
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
