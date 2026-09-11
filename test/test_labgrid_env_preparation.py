"""Per-test DTBs must use the place's deployment strategy, not SD recovery."""

import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest


spec = importlib.util.spec_from_file_location(
    "prepare_labgrid_env",
    Path(__file__).parents[1] / ".github/scripts/prepare_labgrid_env.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def environment(resources=None):
    return {
        "targets": {
            "main": {"resources": resources or {"RemotePlace": {"name": "bench"}}}
        }
    }


def test_tftp_uses_live_tags_and_disables_sd_autoboot():
    original = environment()
    rendered = environment()
    rendered["targets"]["main"]["drivers"] = {
        "BootFPGASoCTFTP": {"sd_autoboot": "true"}
    }
    renderer = Mock(return_value=rendered)
    place = {
        "name": "bench",
        "tags": {"boot-strategy": "BootFPGASoCTFTP", "sd-autoboot": "true"},
    }
    prepared = module.deployment_config(
        original, place, tftp_root="/tmp/private-tftp", render=renderer
    )
    renderer.assert_called_once_with(
        place, {"sd_autoboot": "false", "tftp_root": "/tmp/private-tftp"}
    )
    assert prepared["targets"]["main"]["drivers"]["BootFPGASoCTFTP"] == {
        "sd_autoboot": False,
        "tftp_root_folder": "/tmp/private-tftp",
    }
    assert "drivers" not in original["targets"]["main"]


def test_sd_autoboot_board_keeps_the_place_configuration(monkeypatch):
    """ADRV9361-Z7035 cannot TFTP a kernel, so its SD autoboot must survive.

    ADI's Zynq-7000 U-Boot has no CONFIG_TFTP_PORT and only TFTPs from
    privileged port 69, which TFTPServerDriver's 3069 can never satisfy.
    """
    monkeypatch.delenv("BOARD", raising=False)
    monkeypatch.delenv("CARRIER", raising=False)
    original = environment()
    rendered = environment()
    rendered["targets"]["main"]["drivers"] = {
        "BootFPGASoCTFTP": {"sd_autoboot": "true"},
        "KuiperDLDriver": {},
    }
    renderer = Mock(return_value=rendered)
    place = {
        "name": "bench",
        "tags": {
            "boot-strategy": "BootFPGASoCTFTP",
            "sd-autoboot": "true",
            "daughter-board": "adrv9361z7035",
            "carrier": "adrv1crr-fmc",
        },
    }
    prepared = module.deployment_config(
        original, place, tftp_root="/tmp/private-tftp", render=renderer
    )
    renderer.assert_called_once_with(place, {})
    drivers = prepared["targets"]["main"]["drivers"]
    assert drivers["BootFPGASoCTFTP"]["sd_autoboot"] == "true"
    assert "tftp_root_folder" not in drivers["BootFPGASoCTFTP"]
    # Activating KuiperDLDriver downloads a multi-GB image this path never uses.
    assert "KuiperDLDriver" not in drivers


def test_sd_autoboot_opt_out_prefers_ci_board_environment(monkeypatch):
    """prepare-hardware-env.sh exports BOARD/CARRIER; they win over the tags."""
    monkeypatch.setenv("BOARD", "adrv9009")
    monkeypatch.setenv("CARRIER", "zc706")
    place = {
        "name": "bench",
        "tags": {
            "boot-strategy": "BootFPGASoCTFTP",
            "daughter-board": "adrv9361z7035",
            "carrier": "adrv1crr-fmc",
        },
    }
    assert module.keeps_sd_autoboot(place) is False


@pytest.mark.parametrize(
    "boot_mode", ["BootFabric", "BootFPGASoC", "BootZynq7000JTAGRecovery", "unknown"]
)
def test_other_boot_modes_preserve_supplied_environment(boot_mode):
    original = environment()
    renderer = Mock()
    assert (
        module.deployment_config(
            original,
            {"name": "bench", "tags": {"boot-strategy": boot_mode}},
            tftp_root="",
            render=renderer,
        )
        is original
    )
    renderer.assert_not_called()


def test_wrong_place_is_rejected():
    with pytest.raises(ValueError, match="different place"):
        module.deployment_config(
            environment(), {"name": "other"}, tftp_root="", render=Mock()
        )


def test_list_resources_and_direct_environments():
    assert (
        module.remote_place_name(environment([{"RemotePlace": {"name": "bench"}}]))
        == "bench"
    )
    assert (
        module.remote_place_name(
            environment({"RawSerialPort": {"port": "/dev/ttyUSB0"}})
        )
        is None
    )


def test_zynqmp_renders_production_strategy_and_accepts_either_ethernet_port():
    original = environment()
    rendered = environment()
    rendered["imports"] = ["adi_lg_plugins"]
    rendered["targets"]["main"]["drivers"] = {"BootZynqMPJTAG": {}}
    renderer = Mock(return_value=rendered)
    prepared = module.deployment_config(
        original,
        {"name": "bench", "tags": {"boot-strategy": "BootZynqMPJTAG"}},
        tftp_root="",
        render=renderer,
    )
    renderer.assert_called_once()
    assert "adi_lg_plugins.strategies.bootzynqmpjtag" in prepared["imports"]
    checks = prepared["targets"]["main"]["drivers"]["BootZynqMPJTAG"][
        "kuiper_verify_commands"
    ]
    assert "scope global" in checks[0]
    assert "dev eth0" not in checks[0]
    assert "grep -c '^adrv9009-phy'" in checks[1]
    assert "jesd204-fsm" in checks[2]
    assert "drivers" not in original["targets"]["main"]
