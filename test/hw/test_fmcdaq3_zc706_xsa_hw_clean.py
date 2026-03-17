from __future__ import annotations

import os
from pathlib import Path

import pytest

from adidt.xsa.adijif_fmcdaq3 import resolve_fmcdaq3_config
from adidt.xsa.pipeline import XsaPipeline
from test.hw.hw_helpers import DEFAULT_OUT_DIR, compile_dts_to_dtb, shell_out
from test.xsa.kuiper_release import download_project_xsa

iio = pytest.importorskip("iio")

if not os.environ.get("LG_ENV"):
    pytest.skip(
        "set LG_ENV for FMCDAQ3 ZC706 hardware test",
        allow_module_level=True,
    )

DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynq-zc706-adv7511-fmcdaq3-revC"
DEFAULT_KUIPER_BOOTBIN = "release:zynq-zc706-adv7511-fmcdaq3-revC/BOOT.BIN"
DEFAULT_VCXO_HZ = 125e6
DEFAULT_SAMPLE_RATE_HZ = 500e6


@pytest.fixture(scope="module")
def built_kernel_image(built_kernel_image_zynq: Path | None) -> Path | None:
    """Linux kernel image for ZC706 (Zynq-7000)."""
    return built_kernel_image_zynq


@pytest.mark.lg_feature(["fmcdaq3", "zc706"])
def test_fmcdaq3_zc706_xsa_hw(board, built_kernel_image, tmp_path):
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

    cfg, _summary = resolve_fmcdaq3_config(
        DEFAULT_VCXO_HZ,
        DEFAULT_SAMPLE_RATE_HZ,
        dev_kit_name="zc706",
        solve=True,
    )
    out_dir = DEFAULT_OUT_DIR
    result = XsaPipeline().run(
        xsa_path=xsa_path,
        cfg=cfg,
        output_dir=out_dir,
        sdtgen_timeout=300,
    )

    dtb = out_dir / "devicetree.dtb"
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
    (out_dir / "dmesg_fmcdaq3_zc706_xsa.log").write_text(dmesg_txt)

    addresses = shell.get_ip_addresses()
    ip_address = str(addresses[0].ip)
    if "/" in ip_address:
        ip_address = ip_address.split("/")[0]
    ctx = iio.Context(f"ip:{ip_address}")
    assert ctx is not None, "Failed to create IIO context"

    expected_aliases = {
        "adc_core": ["axi-ad9680-hpc", "ad_ip_jesd204_tpl_adc"],
        "dac_core": ["axi-ad9152-hpc", "ad_ip_jesd204_tpl_dac"],
    }
    found = [d.name for d in ctx.devices]
    for role, aliases in expected_aliases.items():
        assert any(name in found for name in aliases), (
            f"Expected IIO device for {role} not found. "
            f"Expected one of {aliases}; available devices: {found}"
        )
