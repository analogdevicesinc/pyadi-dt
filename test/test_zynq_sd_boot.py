"""Release boot from a rig's own SD card: staging and U-Boot hand-off order."""

import enum
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test.hw import _zynq_sd_boot as boot


class _Status(enum.Enum):
    shell = 1
    booted = 2


def test_rejects_strategies_that_do_not_boot_their_own_card(tmp_path):
    with pytest.raises(ValueError, match="sd-autoboot"):
        boot.boot_release_design_from_sd(object(), tmp_path / "a", tmp_path, tmp_path)


def test_boots_staged_files_with_the_stock_command_line(tmp_path, monkeypatch):
    files = {}
    for name in ("tree.dtb", "top.bit", "uImage"):
        files[name] = tmp_path / name
        files[name].write_bytes(name.encode())
    kernel_crc = boot.zlib.crc32(b"uImage")
    console = Mock()
    shell = SimpleNamespace(console=console)
    events = []
    board = type("BootFPGASoCTFTP", (), {})()
    board.sd_autoboot = True
    board.uboot_prompt = "Zynq>.*"
    board.kernel_addr, board.dtb_addr = "0x3000000", "0x2A00000"
    board.status = _Status.shell
    board.transition = Mock(side_effect=lambda state: events.append(state))
    board.power = Mock()
    board._boot_via_sd_autoboot = Mock()
    board.target = SimpleNamespace(get_driver=Mock(return_value=shell))
    monkeypatch.setattr(boot, "mark_dtb_for_boot", Mock(return_value="marker"))
    monkeypatch.setattr(boot.time, "sleep", Mock())
    stage = Mock()
    monkeypatch.setattr(boot, "_stage_on_sd", stage)
    monkeypatch.setattr(
        boot,
        "shell_out",
        lambda _shell, cmd: "root=/dev/mmcblk0p2 rw" if "cmdline" in cmd else "marker",
    )
    commands = []

    def uboot(_board, command):
        commands.append(command)
        if "crc32" in command:
            return f"crc32 for ... ==> {kernel_crc:08x}"
        return 'adidt,validation-id = "marker"'

    monkeypatch.setattr(boot, "_uboot_command", uboot)

    boot.boot_release_design_from_sd(
        board, files["tree.dtb"], files["top.bit"], files["uImage"]
    )

    staged = stage.call_args.args[2]
    assert sorted(path.name for path in staged.values()) == sorted(files)
    assert all(name.startswith(path.name + "-") for name, path in staged.items())
    assert "fpga loadb" in commands[0] and commands[0].index("fatload") == 0
    assert commands[-1] == "setenv bootargs 'root=/dev/mmcblk0p2 rw'"
    console.sendline.assert_called_with("bootm 0x3000000 - 0x2A00000")
    board.power.off.assert_called_once()
    assert events == ["shell", "shell"] and board.status is _Status.booted
