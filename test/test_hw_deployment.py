"""Generated-DTB tests must boot the staged tree rather than the stock SD tree."""

from types import SimpleNamespace
from unittest.mock import Mock
import shutil
import subprocess

import pytest

from test.hw.hw_helpers import deploy_and_boot, mark_dtb_for_boot
from test.hw import hw_helpers


@pytest.fixture(autouse=True)
def boot_marker(monkeypatch):
    monkeypatch.setattr(hw_helpers, "mark_dtb_for_boot", Mock(return_value="run-id"))
    monkeypatch.setattr(hw_helpers, "shell_out", Mock(return_value="run-id"))


@pytest.mark.parametrize("mode", ["recovery", "sd_autoboot", "different_driver"])
def test_reject_boot_paths_that_ignore_generated_dtb(tmp_path, mode):
    kuiper = Mock()
    board = SimpleNamespace(
        target=SimpleNamespace(get_driver=Mock(return_value=kuiper)),
        transition=Mock(),
    )
    if mode == "sd_autoboot":
        board.kuiper = kuiper
        board.sd_autoboot = True
    elif mode == "different_driver":
        board.kuiper = Mock()
    with pytest.raises(pytest.fail.Exception, match="consumes the staged Kuiper files"):
        deploy_and_boot(board, tmp_path / "generated.dtb")
    kuiper.get_boot_files_from_release.assert_not_called()
    kuiper.add_files_to_target.assert_not_called()
    board.transition.assert_not_called()


def test_stage_kernel_and_generated_dtb_before_boot(tmp_path):
    calls = Mock()
    kuiper, shell = Mock(), object()
    calls.attach_mock(kuiper, "kuiper")
    board = SimpleNamespace(
        target=SimpleNamespace(
            get_driver=lambda name: kuiper if name == "KuiperDLDriver" else shell
        ),
        kuiper=kuiper,
        transition=calls.transition,
    )
    dtb, kernel = tmp_path / "generated.dtb", tmp_path / "uImage"
    assert deploy_and_boot(board, dtb, kernel) is shell
    from unittest.mock import call

    assert calls.mock_calls == [
        call.transition("powered_off"),
        call.kuiper.get_boot_files_from_release(),
        call.kuiper.add_files_to_target(kernel),
        call.kuiper.add_files_to_target(dtb),
        call.transition("shell"),
    ]


def test_serial_connection_is_ready_before_boot(tmp_path):
    calls = Mock()
    kuiper, console = Mock(), object()
    board = SimpleNamespace(
        target=SimpleNamespace(get_driver=lambda name: kuiper, activate=calls.activate),
        kuiper=kuiper,
        shell=SimpleNamespace(console=console),
        transition=calls.transition,
    )
    deploy_and_boot(board, tmp_path / "generated.dtb")
    from unittest.mock import call

    assert calls.mock_calls == [
        call.transition("powered_off"),
        call.activate(console),
        call.transition("shell"),
    ]


def test_kernel_override_uses_the_name_requested_by_uboot(tmp_path):
    copied = {}
    pending = []
    kuiper = Mock()
    kuiper.add_files_to_target.side_effect = pending.append

    def transition(status):
        if status == "shell":
            copied.update({path.name: path.read_bytes() for path in pending})

    board = SimpleNamespace(
        target=SimpleNamespace(get_driver=lambda name: kuiper),
        kuiper=kuiper,
        transition=transition,
        kernel_image_name="uImage",
    )
    kernel, dtb = tmp_path / "uImage-private", tmp_path / "devicetree.dtb"
    kernel.write_bytes(b"private kernel")
    dtb.write_bytes(b"marked tree")
    deploy_and_boot(board, dtb, kernel)
    assert copied == {"uImage": b"private kernel", "devicetree.dtb": b"marked tree"}


def test_stock_dtb_cannot_pass_as_generated(tmp_path, monkeypatch):
    monkeypatch.setattr(hw_helpers, "shell_out", Mock(return_value=""))
    kuiper = Mock()
    board = SimpleNamespace(
        target=SimpleNamespace(get_driver=lambda name: kuiper),
        kuiper=kuiper,
        transition=Mock(),
    )
    with pytest.raises(AssertionError, match="does not match the staged generated DTB"):
        deploy_and_boot(board, tmp_path / "devicetree.dtb")


@pytest.mark.skipif(
    not all(shutil.which(tool) for tool in ("dtc", "fdtput", "fdtget")),
    reason="device-tree compiler tools required",
)
def test_boot_marker_is_unique_and_preserves_tree(tmp_path):
    dtb = tmp_path / "devicetree.dtb"
    subprocess.run(
        ["dtc", "-I", "dts", "-O", "dtb", "-o", str(dtb)],
        input='/dts-v1/; / { model = "test-board"; };',
        text=True,
        check=True,
    )
    first, second = mark_dtb_for_boot(dtb), mark_dtb_for_boot(dtb)
    assert first != second
    assert (
        subprocess.check_output(
            ["fdtget", "-t", "s", str(dtb), "/", "adidt,validation-id"], text=True
        ).strip()
        == second
    )
    assert (
        subprocess.check_output(
            ["fdtget", "-t", "s", str(dtb), "/", "model"], text=True
        ).strip()
        == "test-board"
    )
