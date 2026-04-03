from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from adidt.xsa.pipeline import XsaPipeline
from test.hw.hw_helpers import DEFAULT_OUT_DIR, compile_dts_to_dtb, shell_out
from test.xsa.kuiper_release import download_project_xsa

iio = pytest.importorskip("iio")

if not os.environ.get("LG_ENV"):
    pytest.skip(
        "set LG_ENV for AD9172 ZCU102 hardware test",
        allow_module_level=True,
    )

DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynqmp-zcu102-rev10-ad9172-fmc-ebz-mode4"
DEFAULT_KUIPER_BOOTBIN = "release:zynqmp-zcu102-rev10-ad9172-fmc-ebz-mode4/BOOT.BIN"
DEFAULT_VCXO_HZ = 125e6
DEFAULT_SAMPLE_RATE_HZ = 12288e6


def _resolve_config_from_adijif(
    vcxo_hz: float = DEFAULT_VCXO_HZ,
    sample_rate_hz: float = DEFAULT_SAMPLE_RATE_HZ,
    solve: bool = True,
) -> dict[str, Any]:
    """Use adijif to derive JESD TX parameters for the AD9172 (DAC-only).

    The AD9172 is not directly available in adijif, so we use the AD9144 as a
    stand-in — it shares the same JESD204B mode table for L=8, M=4, Np=16.
    """
    import adijif

    sys = adijif.system("ad9144", "hmc7044", "xilinx", vcxo_hz)
    sys.fpga.setup_by_dev_kit_name("zcu102")
    sys.fpga.ref_clock_constraint = "Unconstrained"

    tx_mode = adijif.utils.get_jesd_mode_from_params(sys.converter, L=8, M=4, Np=16)
    if not tx_mode:
        raise RuntimeError("No matching AD9172 JESD TX mode found via adijif")

    sys.converter.set_quick_configuration_mode(tx_mode[0]["mode"], "jesd204b")
    sys.converter.sample_clock = sample_rate_hz

    def _jesd_mode_val(mode: dict[str, Any], key: str, default: int) -> int:
        settings = mode.get("settings", {}) if isinstance(mode, dict) else {}
        if key in settings:
            return int(settings[key])
        if key in mode:
            return int(mode[key])
        return default

    txm = tx_mode[0]
    cfg: dict[str, Any] = {
        "jesd": {
            "tx": {
                "F": _jesd_mode_val(txm, "F", 1),
                "K": _jesd_mode_val(txm, "K", 32),
                "M": _jesd_mode_val(txm, "M", 4),
                "L": _jesd_mode_val(txm, "L", 8),
                "Np": _jesd_mode_val(txm, "Np", 16),
                "S": _jesd_mode_val(txm, "S", 1),
            },
        },
    }

    if solve:
        conf = sys.solve()
        tx_conf = conf.get("jesd_AD9144", {})
        for key in ("F", "K", "M", "L", "Np", "S"):
            if key in tx_conf:
                cfg["jesd"]["tx"][key] = int(tx_conf[key])

    return cfg


@pytest.fixture(scope="module")
def built_kernel_image(built_kernel_image_zynqmp: Path | None) -> Path | None:
    """Linux kernel image for ZCU102 (ZynqMP)."""
    return built_kernel_image_zynqmp


@pytest.mark.lg_feature(["ad9172", "zcu102"])
def test_ad9172_zcu102_xsa_hw(board, built_kernel_image, tmp_path):
    release = os.environ.get("ADI_KUIPER_BOOT_RELEASE", DEFAULT_KUIPER_RELEASE)
    project = os.environ.get("ADI_KUIPER_XSA_PROJECT", DEFAULT_KUIPER_PROJECT)
    bootbin = os.environ.get("ADI_KUIPER_BOOTBIN", DEFAULT_KUIPER_BOOTBIN)

    xsa_path = download_project_xsa(
        release=release,
        project_dir=project,
        cache_dir=tmp_path / "kuiper_cache",
        output_dir=tmp_path / "xsa",
    )
    assert xsa_path.exists(), f"XSA extraction failed: {xsa_path}"

    cfg = _resolve_config_from_adijif(solve=True)
    out_dir = DEFAULT_OUT_DIR
    result = XsaPipeline().run(
        xsa_path=xsa_path,
        cfg=cfg,
        output_dir=out_dir,
        profile="ad9172_zcu102",
        sdtgen_timeout=300,
    )

    dtb = out_dir / "system.dtb"
    compile_dts_to_dtb(result["merged"], dtb)

    kuiper = board.target.get_driver("KuiperDLDriver")
    kuiper.kuiper_resource.BOOTBIN_path = bootbin
    kuiper.get_boot_files_from_release()
    if built_kernel_image is not None:
        kuiper.add_files_to_target(built_kernel_image)
    kuiper.add_files_to_target(dtb)

    board.transition("shell")
    shell = board.target.get_driver("ADIShellDriver")
    dmesg_txt = shell_out(shell, "dmesg")
    (out_dir / "dmesg_ad9172_zcu102_xsa.log").write_text(dmesg_txt)

    addresses = shell.get_ip_addresses()
    ip_address = str(addresses[0].ip)
    if "/" in ip_address:
        ip_address = ip_address.split("/")[0]
    ctx = iio.Context(f"ip:{ip_address}")
    assert ctx is not None, "Failed to create IIO context"

    expected_aliases = {
        "dac_core": ["axi-ad9172-hpc", "ad_ip_jesd204_tpl_dac", "cf_axi_dds"],
        "clock_chip": ["hmc7044", "ad9528"],
    }
    found = [d.name for d in ctx.devices]
    for role, aliases in expected_aliases.items():
        assert any(name in found for name in aliases), (
            f"Expected IIO device for {role} not found. "
            f"Expected one of {aliases}; available devices: {found}"
        )

    # The AD9172 SPI driver may not always surface as a standalone IIO context
    # device over network transport, so verify probe success in dmesg as ground truth.
    assert "ad9172" in dmesg_txt.lower() and "probed." in dmesg_txt.lower(), (
        "AD9172 driver did not report successful probe in dmesg"
    )
