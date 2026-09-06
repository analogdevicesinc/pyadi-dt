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


def test_srecord_payload_round_trips_with_binutils(tmp_path):
    import shutil
    import subprocess

    if not shutil.which("objcopy"):
        pytest.skip("objcopy required for independent S-record decoding")
    data = bytes(range(256)) * 3 + b"last partial record"
    source = tmp_path / "dtb.srec"
    source.write_bytes(boot._srecords(data, 0x20000000))
    binary = tmp_path / "dtb.bin"
    subprocess.run(
        ["objcopy", "-I", "srec", "-O", "binary", str(source), str(binary)],
        check=True,
        capture_output=True,
    )
    assert binary.read_bytes() == data


@pytest.mark.parametrize("size,address", [(0, 0), (2097153, 0), (32, 0xFFFFFFF0)])
def test_serial_payload_rejects_invalid_ram_extent(size, address):
    with pytest.raises(ValueError):
        boot._srecords(b"x" * size, address)


def test_generated_handoff_rejects_unrelated_strategy(tmp_path):
    with pytest.raises(ValueError, match="BootZynqMPJTAG"):
        boot.boot_generated_zynqmp_dtb(object(), tmp_path / "tree.dtb")


def test_failed_serial_upload_cannot_boot_linux(tmp_path, monkeypatch):
    board = type("BootZynqMPJTAG", (), {})()
    board.transition = Mock()
    board.shell = SimpleNamespace(console=Mock())
    monkeypatch.setattr(
        boot, "_upload_dtb_serial", Mock(side_effect=AssertionError("CRC mismatch"))
    )
    monkeypatch.setattr(boot, "mark_dtb_for_boot", Mock(return_value="unique-marker"))
    uboot = Mock()
    monkeypatch.setattr(boot, "_uboot_command", uboot)
    with pytest.raises(AssertionError, match="CRC mismatch"):
        boot.boot_generated_zynqmp_dtb(board, tmp_path / "tree.dtb")
    # Only the SD kernel load ran. No fdt/booti command may follow an upload error.
    assert uboot.call_count == 1
    assert "cpuidle.off=1" in uboot.call_args.args[1]
    board.shell.console.sendline.assert_not_called()


def test_serial_upload_rejects_corrupted_ram_and_restores_pacing(tmp_path, monkeypatch):
    data = b"small dtb payload"
    dtb = tmp_path / "tree.dtb"
    dtb.write_bytes(data)
    size_match = Mock()
    size_match.group.return_value = f"{len(data):x}".encode()
    console = Mock(txdelay=0.0, txchunk=1)
    console.expect.side_effect = [
        (0, b"", None, b""),
        (0, b"", size_match, b""),
        (0, b"", None, b""),
    ]
    board = SimpleNamespace(
        shell=SimpleNamespace(console=console), production_uboot_prompt="ZynqMP>"
    )
    monkeypatch.setattr(
        boot, "_uboot_command", Mock(side_effect=["", "CRC32 ==> 00000000"])
    )
    with pytest.raises(AssertionError, match="CRC32"):
        boot._upload_dtb_serial(board, dtb)
    assert (console.txdelay, console.txchunk) == (0.0, 1)



def test_transfer_size_waits_for_complete_serial_field():
    import re

    prefix = "## Total Size = 0x0001F600"
    for end in range(1, len(prefix) + 1):
        assert re.search(boot._SREC_SIZE_PATTERN, prefix[:end]) is None
    match = re.search(boot._SREC_SIZE_PATTERN, prefix + " = 128512 Bytes")
    assert int(match.group(1), 16) == 128512
