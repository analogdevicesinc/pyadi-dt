from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import iio
import pytest

from adidt.xsa.pipeline import XsaPipeline
from test.hw.hw_helpers import DEFAULT_OUT_DIR, compile_dts_to_dtb, shell_out
from test.xsa.kuiper_release import download_project_xsa

if not os.environ.get("LG_ENV"):
    pytest.skip(
        "set LG_ENV for FMCDAQ2 ZCU102 hardware test",
        allow_module_level=True,
    )

DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynqmp-zcu102-rev10-fmcdaq2"
DEFAULT_KUIPER_BOOTBIN = "release:zynqmp-zcu102-rev10-fmcdaq2/BOOT.BIN"
DEFAULT_VCXO_HZ = 125e6
DEFAULT_SAMPLE_RATE_HZ = 500e6


def _resolve_config_from_adijif(
    vcxo_hz: float, sample_rate_hz: float, solve: bool = True
) -> tuple[dict[str, Any], dict[str, Any]]:
    import adijif

    sys = adijif.system(["ad9680", "ad9144"], "ad9523_1", "xilinx", vcxo_hz)
    sys.fpga.setup_by_dev_kit_name("zcu102")
    sys.fpga.ref_clock_constraint = "Unconstrained"

    rx_mode = adijif.utils.get_jesd_mode_from_params(
        sys.converter[0], L=4, M=2, Np=16, F=1
    )
    tx_mode = adijif.utils.get_jesd_mode_from_params(
        sys.converter[1], L=4, M=2, Np=16, F=1
    )
    if not rx_mode or not tx_mode:
        raise RuntimeError("No matching FMCDAQ2 JESD modes found via adijif")

    sys.converter[0].set_quick_configuration_mode(rx_mode[0]["mode"], "jesd204b")
    sys.converter[1].set_quick_configuration_mode(tx_mode[0]["mode"], "jesd204b")
    sys.converter[0].sample_clock = sample_rate_hz
    sys.converter[1].sample_clock = sample_rate_hz

    def _jesd_mode_val(mode: dict[str, Any], key: str, default: int) -> int:
        settings = mode.get("settings", {}) if isinstance(mode, dict) else {}
        if key in settings:
            return int(settings[key])
        if key in mode:
            return int(mode[key])
        return default

    rxm = rx_mode[0]
    txm = tx_mode[0]
    cfg: dict[str, Any] = {
        "jesd": {
            "rx": {
                "F": _jesd_mode_val(rxm, "F", 1),
                "K": _jesd_mode_val(rxm, "K", 32),
                "M": _jesd_mode_val(rxm, "M", 2),
                "L": _jesd_mode_val(rxm, "L", 4),
                "Np": _jesd_mode_val(rxm, "Np", 16),
                "S": _jesd_mode_val(rxm, "S", 1),
            },
            "tx": {
                "F": _jesd_mode_val(txm, "F", 1),
                "K": _jesd_mode_val(txm, "K", 32),
                "M": _jesd_mode_val(txm, "M", 2),
                "L": _jesd_mode_val(txm, "L", 4),
                "Np": _jesd_mode_val(txm, "Np", 16),
                "S": _jesd_mode_val(txm, "S", 1),
            },
        },
        "clock": {
            "rx_device_clk_label": "clk0_ad9523",
            "tx_device_clk_label": "clk0_ad9523",
            "rx_device_clk_index": 13,
            "tx_device_clk_index": 1,
        },
    }
    summary: dict[str, Any] = {
        "solver_succeeded": False,
        "clock_output_clocks": None,
    }

    if solve:
        conf = sys.solve()
        summary["solver_succeeded"] = True
        summary["clock_output_clocks"] = conf.get("clock", {}).get("output_clocks")
        rx_conf = conf.get("jesd_AD9680", {})
        tx_conf = conf.get("jesd_AD9144", {})
        for key in ("F", "K", "M", "L", "Np", "S"):
            if key in rx_conf:
                cfg["jesd"]["rx"][key] = int(rx_conf[key])
            if key in tx_conf:
                cfg["jesd"]["tx"][key] = int(tx_conf[key])
        cfg["fpga_adc"] = conf.get("fpga_adc", {})
        cfg["fpga_dac"] = conf.get("fpga_dac", {})

    return cfg, summary


@pytest.fixture(scope="module")
def built_kernel_image(built_kernel_image_zynqmp: Path | None) -> Path | None:
    """Linux kernel image for ZCU102 (ZynqMP)."""
    return built_kernel_image_zynqmp


@pytest.mark.lg_feature(["fmcdaq2", "zcu102"])
def test_fmcdaq2_zcu102_xsa_hw(board, built_kernel_image, tmp_path):
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

    cfg, _summary = _resolve_config_from_adijif(
        DEFAULT_VCXO_HZ, DEFAULT_SAMPLE_RATE_HZ, solve=True
    )
    out_dir = DEFAULT_OUT_DIR
    result = XsaPipeline().run(
        xsa_path=xsa_path,
        cfg=cfg,
        output_dir=out_dir,
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
    (out_dir / "dmesg_fmcdaq2_zcu102_xsa.log").write_text(dmesg_txt)

    addresses = shell.get_ip_addresses()
    ip_address = str(addresses[0].ip)
    if "/" in ip_address:
        ip_address = ip_address.split("/")[0]
    ctx = iio.Context(f"ip:{ip_address}")
    assert ctx is not None, "Failed to create IIO context"

    expected_aliases = {
        "adc_core": ["axi-ad9680-hpc", "ad_ip_jesd204_tpl_adc"],
        "dac_core": ["axi-ad9144-hpc", "ad_ip_jesd204_tpl_dac"],
    }
    found = [d.name for d in ctx.devices]
    for role, aliases in expected_aliases.items():
        assert any(name in found for name in aliases), (
            f"Expected IIO device for {role} not found. "
            f"Expected one of {aliases}; available devices: {found}"
        )
