"""A successful configfs write alone is not evidence of an applied overlay."""

from unittest.mock import Mock
import shutil
import subprocess

import pytest

from test.hw import hw_helpers
from test.hw.xsa import _overlay_modules
from test.hw.xsa._overlay_tree import prepare_overlay_base


@pytest.mark.parametrize("status", ["unapplied", "", "applied"])
def test_binary_overlay_load_requires_applied_status(monkeypatch, status):
    marker = "a" * 32
    commands = Mock(side_effect=["", "RC=0", status, marker, marker])
    monkeypatch.setattr(hw_helpers, "shell_out", commands)
    if status == "applied":
        assert hw_helpers.load_overlay(object(), "test", "/tmp/test.dtbo") == "RC=0"
    else:
        with pytest.raises(AssertionError, match="did not reach applied status"):
            hw_helpers.load_overlay(object(), "test", "/tmp/test.dtbo")
    write = commands.call_args_list[1].args[1]
    assert "cat /tmp/test.dtbo >" in write
    assert "/test/dtbo" in write


def test_applied_status_cannot_hide_failed_live_update(monkeypatch):
    commands = Mock(side_effect=["", "RC=0", "applied", "a" * 32, "", "", ""])
    monkeypatch.setattr(hw_helpers, "shell_out", commands)
    with pytest.raises(AssertionError, match="did not update the live tree"):
        hw_helpers.load_overlay(object(), "test", "/tmp/test.dtbo")


def test_configfs_is_mounted_before_support_check(monkeypatch):
    commands = Mock(side_effect=["", "OK"])
    monkeypatch.setattr(hw_helpers, "shell_out", commands)
    hw_helpers.assert_configfs_overlay_support(object())
    assert "mount -t configfs" in commands.call_args_list[0].args[1]


@pytest.mark.skipif(
    not all(shutil.which(tool) for tool in ("dtc", "fdtget", "fdtoverlay")),
    reason="device-tree compiler tools required",
)
def test_compiled_overlay_updates_live_marker_and_target_node(tmp_path):
    base = tmp_path / "base.dts"
    base.write_text('/dts-v1/; / { device: test-device { status = "disabled"; }; };')
    dtb = tmp_path / "base.dtb"
    hw_helpers.compile_dts_to_dtb(base, dtb)
    overlay = tmp_path / "test.dtso"
    overlay.write_text('/dts-v1/; /plugin/; &device { status = "okay"; };')
    dtbo = tmp_path / "test.dtbo"
    hw_helpers.compile_dtso_to_dtbo(overlay, dtbo)
    applied = tmp_path / "applied.dtb"
    subprocess.run(
        ["fdtoverlay", "-i", str(dtb), "-o", str(applied), str(dtbo)], check=True
    )
    marker = subprocess.check_output(
        ["fdtget", str(applied), "/", "adidt,overlay-validation-id"], text=True
    ).strip()
    assert marker == dtbo.with_suffix(".validation-id").read_text()
    assert (
        subprocess.check_output(
            ["fdtget", str(applied), "/test-device", "status"], text=True
        ).strip()
        == "okay"
    )


def test_busy_client_prevents_jesd_teardown(monkeypatch):
    monkeypatch.setattr(_overlay_modules, "_unbind_iio_consumers", Mock())
    commands = Mock(return_value="rmmod: module is in use\nMODULE_RC=1")
    monkeypatch.setattr(_overlay_modules, "shell_out", commands)
    with pytest.raises(AssertionError, match="Cannot quiesce overlay driver converter"):
        _overlay_modules.stop_overlay_modules(object(), ("jesd204", "converter"))
    assert commands.call_count == 1


def test_topology_must_be_absent_before_tree_change(monkeypatch):
    monkeypatch.setattr(_overlay_modules, "_unbind_iio_consumers", Mock())
    commands = Mock(side_effect=["MODULE_RC=0", "MODULE_RC=0", ""])
    monkeypatch.setattr(_overlay_modules, "shell_out", commands)
    with pytest.raises(AssertionError, match="still registered"):
        _overlay_modules.stop_overlay_modules(object(), ("jesd204", "converter"))


def test_missing_core_stops_client_loading(monkeypatch):
    commands = Mock(return_value="modprobe: module not found\nMODULE_RC=1")
    monkeypatch.setattr(_overlay_modules, "shell_out", commands)
    with pytest.raises(AssertionError, match="Could not load overlay driver jesd204"):
        _overlay_modules.start_overlay_modules(object(), ("jesd204", "converter"))
    assert commands.call_count == 1


def test_iio_consumers_are_unbound_before_converter_module_removal(monkeypatch):
    commands = Mock(return_value="MODULE_RC=0\nJESD_ABSENT")
    monkeypatch.setattr(_overlay_modules, "shell_out", commands)
    _overlay_modules.stop_overlay_modules(object(), ("jesd204", "converter"))
    sequence = [call.args[1] for call in commands.call_args_list]
    assert sequence[0].find("stop iiod") >= 0
    assert "/cf_axi_adc/unbind" in sequence[1]
    assert "/cf_axi_dds/unbind" in sequence[2]
    assert "rmmod converter" in sequence[3]
    assert "rmmod jesd204" in sequence[4]
    assert "/sys/bus/jesd204" in sequence[5]


def test_module_archive_requires_checksum_before_download(monkeypatch):
    monkeypatch.setenv("ADIDT_OVERLAY_MODULES_URL", "http://lab/modules.tar.gz")
    monkeypatch.delenv("ADIDT_OVERLAY_MODULES_SHA256", raising=False)
    commands = Mock()
    monkeypatch.setattr(_overlay_modules, "shell_out", commands)
    with pytest.raises(AssertionError, match="Set both"):
        _overlay_modules.stage_overlay_modules(object())
    commands.assert_not_called()


@pytest.mark.skipif(
    not all(shutil.which(tool) for tool in ("dtc", "fdtget", "fdtput", "fdtoverlay")),
    reason="device-tree compiler tools required",
)
def test_runtime_base_leaves_spi_children_owned_by_overlay(tmp_path):
    base = tmp_path / "base.dts"
    base.write_text("""/dts-v1/; / {
        spi: spi { #address-cells = <1>; #size-cells = <0>;
            converter: adc@0 { reg = <0>; child: channel { value = <1>; }; };
            unrelated: sensor@1 { reg = <1>; };
        };
        core: core { status = "disabled"; };
    };""")
    overlay = tmp_path / "overlay.dtso"
    overlay.write_text("""/dts-v1/; /plugin/;
        &spi { #address-cells = <1>; #size-cells = <0>;
            converter: adc@0 { reg = <0>; child: channel { value = <2>; }; };
        };
        &core { status = "okay"; converter = <&converter>; };
    """)
    dtb, dtbo = tmp_path / "base.dtb", tmp_path / "overlay.dtbo"
    hw_helpers.compile_dts_to_dtb(base, dtb)
    hw_helpers.compile_dtso_to_dtbo(overlay, dtbo)
    prepare_overlay_base(dtb, dtbo)
    symbols = subprocess.check_output(
        ["fdtget", "-p", str(dtb), "/__symbols__"], text=True
    )
    assert set(symbols.split()) == {"spi", "unrelated", "core"}
    children = subprocess.check_output(["fdtget", "-l", str(dtb), "/spi"], text=True)
    assert children.split() == ["sensor@1"]
    applied = tmp_path / "applied.dtb"
    subprocess.run(
        ["fdtoverlay", "-i", str(dtb), "-o", str(applied), str(dtbo)], check=True
    )
    assert (
        subprocess.check_output(
            ["fdtget", str(applied), "/spi/adc@0/channel", "value"], text=True
        ).strip()
        == "2"
    )


def test_local_module_server_lifetime_and_checksum(tmp_path, monkeypatch):
    import hashlib
    import os
    from urllib.request import urlopen
    from urllib.error import HTTPError
    from test.hw.xsa._overlay_module_server import serve_overlay_modules

    archive = tmp_path / "modules.tar.gz"
    payload = b"private module bundle"
    archive.write_bytes(payload)
    monkeypatch.setenv("ADIDT_OVERLAY_MODULES_ARCHIVE", str(archive))
    monkeypatch.setenv("ADIDT_OVERLAY_MODULES_HOST", "127.0.0.1")
    monkeypatch.delenv("ADIDT_OVERLAY_MODULES_URL", raising=False)
    monkeypatch.delenv("ADIDT_OVERLAY_MODULES_SHA256", raising=False)
    with pytest.raises(RuntimeError, match="failed test"):
        with serve_overlay_modules():
            url = os.environ["ADIDT_OVERLAY_MODULES_URL"]
            with urlopen(url, timeout=3) as response:
                assert response.read() == payload
            assert (
                os.environ["ADIDT_OVERLAY_MODULES_SHA256"]
                == hashlib.sha256(payload).hexdigest()
            )
            with pytest.raises(HTTPError, match="404"):
                urlopen(url.replace("/modules.tar.gz", "/other-file"), timeout=3)
            raise RuntimeError("failed test")
    assert "ADIDT_OVERLAY_MODULES_URL" not in os.environ
    assert "ADIDT_OVERLAY_MODULES_SHA256" not in os.environ
    from urllib.error import URLError

    with pytest.raises(URLError):
        urlopen(url, timeout=1)


@pytest.mark.parametrize(
    "before,after,expected",
    [
        ("boot\nready\n", "boot\nready\nloaded\n", "loaded"),
        ("boot\nready\n", "ready\nBUG: fault\n", "ready\nBUG: fault\n"),
        ("old\nold2\nold3\n", "BUG: shorter ring\n", "BUG: shorter ring\n"),
    ],
)
def test_overlay_dmesg_retains_faults_when_ring_wraps(before, after, expected):
    from test.hw.xsa._overlay_base import _dmesg_since

    assert _dmesg_since(before, after) == expected
