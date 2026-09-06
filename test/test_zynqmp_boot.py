"""Generated-tree deployment must fail before Linux on U-Boot/upload errors."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test.hw import _zynqmp_boot as boot


def test_uboot_error_status_is_not_reported_as_success():
    match = Mock()
    match.group.return_value = b"1"
    console = Mock()
    console.expect.return_value = (0, b"Failed to load Image", match, b"")
    board = SimpleNamespace(shell=SimpleNamespace(console=console))
    with pytest.raises(AssertionError, match="Failed to load Image"):
        boot._uboot_command(board, "load mmc 0:1 0x80000 Image")
    assert console.expect.call_count == 1


@pytest.mark.parametrize("value", ["a} ; exit", "a\nb", "a\\b", "{abc"])
def test_tcl_arguments_cannot_escape_a_word(value):
    with pytest.raises(ValueError):
        boot._tcl_word(value)


def test_generated_handoff_rejects_unrelated_strategy(tmp_path):
    with pytest.raises(ValueError, match="BootZynqMPJTAG"):
        boot.boot_generated_zynqmp_dtb(object(), tmp_path / "tree.dtb")


def test_failed_jtag_upload_cannot_boot_linux(tmp_path, monkeypatch):
    board = type("BootZynqMPJTAG", (), {})()
    board.transition = Mock()
    board.shell = SimpleNamespace(console=Mock())
    board.jtag_url = "TCP:127.0.0.1:3121"
    board.jtag = SimpleNamespace(
        _stage_file=Mock(return_value="/tmp/generated.dtb"),
        _run_xsdb=Mock(return_value=("", "DAP transfer failed", 1)),
    )
    monkeypatch.setattr(boot, "mark_dtb_for_boot", Mock(return_value="unique-marker"))
    uboot = Mock()
    monkeypatch.setattr(boot, "_uboot_command", uboot)
    with pytest.raises(AssertionError, match="DAP transfer failed"):
        boot.boot_generated_zynqmp_dtb(board, tmp_path / "tree.dtb")
    # Only the SD kernel load ran. No fdt/booti command may follow an upload error.
    assert uboot.call_count == 1
    board.shell.console.sendline.assert_not_called()
