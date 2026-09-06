"""Explicit hardware artifacts must be used and restored after the run."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test.hw import conftest
from test.hw.xsa._overlay_spec import local_xsa_or_skip


def test_external_xsa_directory_is_authoritative(tmp_path, monkeypatch):
    monkeypatch.setenv("ADIDT_XSA_DIR", str(tmp_path))
    resolver = local_xsa_or_skip("system_top.xsa")
    with pytest.raises(pytest.fail.Exception, match="Configured XSA fixture missing"):
        resolver(tmp_path)
    expected = tmp_path / "system_top.xsa"
    expected.write_bytes(b"fixture")
    assert resolver(tmp_path) == expected


@pytest.mark.parametrize("original", [None, "/stock/simpleImage"])
def test_fabric_kernel_override_restored_after_failure(monkeypatch, original):
    monkeypatch.setenv("ADIDT_FABRIC_KERNEL_IMAGE", "/private/simpleImage")
    monkeypatch.setattr(conftest, "require_hw_prereqs", Mock())
    resource = SimpleNamespace(kernel_path=original)
    strategy = SimpleNamespace(
        jtag=SimpleNamespace(xilinxdevicejtag=resource),
        transition=Mock(),
        target=SimpleNamespace(activate=Mock()),
    )
    fixture = conftest.board.__wrapped__(strategy, _request("test_board_hw.py"))
    assert next(fixture) is strategy
    assert resource.kernel_path == "/private/simpleImage"
    with pytest.raises(RuntimeError, match="test failure"):
        fixture.throw(RuntimeError("test failure"))
    assert resource.kernel_path == original
    assert strategy.transition.call_count == 2


def test_fabric_kernel_override_rejects_incompatible_strategy(monkeypatch):
    monkeypatch.setenv("ADIDT_FABRIC_KERNEL_IMAGE", "/private/simpleImage")
    monkeypatch.setattr(conftest, "require_hw_prereqs", Mock())
    strategy = SimpleNamespace(transition=Mock())
    with pytest.raises(pytest.fail.Exception, match="requires a fabric JTAG resource"):
        next(conftest.board.__wrapped__(strategy, _request("test_board_hw.py")))


def _request(filename):
    return SimpleNamespace(node=SimpleNamespace(path=Path(filename)))


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("test_board_hw.py", "/ordinary/image"),
        ("test_board_overlay.py", "/runtime/image"),
    ],
)
def test_fabric_overlay_override_is_module_specific(monkeypatch, filename, expected):
    monkeypatch.setenv("ADIDT_FABRIC_KERNEL_IMAGE", "/ordinary/image")
    monkeypatch.setenv("ADIDT_OVERLAY_FABRIC_KERNEL_IMAGE", "/runtime/image")
    monkeypatch.setattr(conftest, "require_hw_prereqs", Mock())
    resource = SimpleNamespace(kernel_path="/stock/image")
    strategy = SimpleNamespace(
        jtag=SimpleNamespace(xilinxdevicejtag=resource),
        transition=Mock(),
        target=SimpleNamespace(activate=Mock()),
    )
    fixture = conftest.board.__wrapped__(strategy, _request(filename))
    next(fixture)
    assert resource.kernel_path == expected
    fixture.close()
    assert resource.kernel_path == "/stock/image"


@pytest.mark.parametrize("family", ["zynq", "zynqmp"])
def test_overlay_kernel_override_avoids_ordinary_build(monkeypatch, tmp_path, family):
    from test.hw.xsa._overlay_base import _runtime_kernel_image

    image = tmp_path / "runtime-image"
    image.write_bytes(b"kernel")
    variable = f"ADIDT_OVERLAY_KERNEL_IMAGE_{family.upper()}"
    monkeypatch.setenv(variable, str(image))
    request = Mock()
    spec = SimpleNamespace(kernel_fixture_name=f"built_kernel_image_{family}")
    assert _runtime_kernel_image(request, spec) == image
    request.getfixturevalue.assert_not_called()
    image.unlink()
    with pytest.raises(pytest.fail.Exception, match="not a runner-local file"):
        _runtime_kernel_image(request, spec)
    monkeypatch.delenv(variable)
    assert _runtime_kernel_image(request, spec) == request.getfixturevalue.return_value
    request.getfixturevalue.assert_called_once_with(spec.kernel_fixture_name)
