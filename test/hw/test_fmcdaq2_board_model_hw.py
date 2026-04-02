"""FMCDAQ2 + ZCU102 hardware test using the unified BoardModel.

Exercises the full BoardModel pipeline:
  XSA → sdtgen → topology → FMCDAQ2Builder.build_model() → BoardModelRenderer → DtsMerger → DTB → deploy → IIO verify

LG_ENV: /jenkins/lg_fmcdaq2_zcu102.yaml
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import iio
import pytest

from adidt.model.renderer import BoardModelRenderer
from adidt.xsa.board_fixups import apply_board_fixups
from adidt.xsa.builders.fmcdaq2 import FMCDAQ2Builder
from adidt.xsa.merger import DtsMerger
from adidt.xsa.profiles import ProfileManager, merge_profile_defaults
from adidt.xsa.sdtgen import SdtgenRunner
from adidt.xsa.topology import XsaParser
from test.hw.hw_helpers import DEFAULT_OUT_DIR, compile_dts_to_dtb, shell_out
from test.xsa.kuiper_release import download_project_xsa

LG_ENV_PATH = "/jenkins/lg_fmcdaq2_zcu102.yaml"
if not os.environ.get("LG_ENV"):
    pytest.skip(
        f"set LG_ENV={LG_ENV_PATH} for FMCDAQ2 BoardModel hardware test",
        allow_module_level=True,
    )

DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynqmp-zcu102-rev10-fmcdaq2"
DEFAULT_KUIPER_BOOTBIN = "release:zynqmp-zcu102-rev10-fmcdaq2/BOOT.BIN"

# ZCU102 (ZynqMP) platform labels
PS_CLK_LABEL = "zynqmp_clk"
PS_CLK_INDEX = 71
GPIO_LABEL = "gpio"


def _resolve_config_from_adijif(
    vcxo_hz: float = 125e6,
    sample_rate_hz: float = 500e6,
) -> dict[str, Any]:
    """Resolve FMCDAQ2 JESD + clock config via adijif solver."""
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

    conf = sys.solve()

    def _val(mode: dict, key: str, default: int) -> int:
        settings = mode.get("settings", {}) if isinstance(mode, dict) else {}
        return int(settings.get(key, mode.get(key, default)))

    rxm, txm = rx_mode[0], tx_mode[0]
    cfg: dict[str, Any] = {
        "jesd": {
            "rx": {
                k: _val(rxm, k, d)
                for k, d in [
                    ("F", 1),
                    ("K", 32),
                    ("M", 2),
                    ("L", 4),
                    ("Np", 16),
                    ("S", 1),
                ]
            },
            "tx": {
                k: _val(txm, k, d)
                for k, d in [
                    ("F", 1),
                    ("K", 32),
                    ("M", 2),
                    ("L", 4),
                    ("Np", 16),
                    ("S", 1),
                ]
            },
        },
    }
    # Merge solver-resolved JESD params
    for key in ("F", "K", "M", "L", "Np", "S"):
        rx_conf = conf.get("jesd_AD9680", {})
        tx_conf = conf.get("jesd_AD9144", {})
        if key in rx_conf:
            cfg["jesd"]["rx"][key] = int(rx_conf[key])
        if key in tx_conf:
            cfg["jesd"]["tx"][key] = int(tx_conf[key])

    cfg["fpga_adc"] = conf.get("fpga_adc", {})
    cfg["fpga_dac"] = conf.get("fpga_dac", {})
    return cfg


@pytest.fixture(scope="module")
def built_kernel_image(built_kernel_image_zynqmp: Path | None) -> Path | None:
    """Linux kernel image for ZCU102 (ZynqMP)."""
    return built_kernel_image_zynqmp


@pytest.mark.lg_feature(["fmcdaq2", "zcu102"])
def test_fmcdaq2_board_model(board, built_kernel_image, tmp_path):
    """End-to-end BoardModel test: XSA → BoardModel → render → merge → deploy → IIO."""
    release = os.environ.get("ADI_KUIPER_BOOT_RELEASE", DEFAULT_KUIPER_RELEASE)
    project = os.environ.get("ADI_KUIPER_XSA_PROJECT", DEFAULT_KUIPER_PROJECT)
    bootbin = os.environ.get("ADI_KUIPER_BOOTBIN", DEFAULT_KUIPER_BOOTBIN)

    # --- Stage 1: Download XSA ---
    xsa_path = download_project_xsa(
        release=release,
        project_dir=project,
        cache_dir=tmp_path / "kuiper_cache",
        output_dir=tmp_path / "xsa",
    )
    assert xsa_path.exists(), f"XSA extraction failed: {xsa_path}"

    # --- Stage 2: Run sdtgen for base DTS ---
    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    base_dir = out_dir / "base"
    base_dir.mkdir(exist_ok=True)
    base_dts_path = SdtgenRunner().run(xsa_path, base_dir, timeout=300)
    apply_board_fixups("fmcdaq2_zcu102", base_dir)
    base_dts = base_dts_path.read_text()

    # --- Stage 3: Parse topology + resolve config ---
    topology = XsaParser().parse(xsa_path)
    cfg = _resolve_config_from_adijif()

    # Merge with built-in profile defaults
    profile_data = ProfileManager().load("fmcdaq2_zcu102")
    if profile_data:
        cfg = merge_profile_defaults(cfg, profile_data)

    # --- Stage 4: Build BoardModel ---
    fmcdaq2_builder = FMCDAQ2Builder()
    assert fmcdaq2_builder.matches(topology, cfg), (
        "FMCDAQ2Builder did not match topology — wrong XSA?"
    )
    model = fmcdaq2_builder.build_model(
        topology, cfg, PS_CLK_LABEL, PS_CLK_INDEX, GPIO_LABEL
    )

    # Verify model structure
    assert model.name.startswith("fmcdaq2_")
    assert len(model.components) == 3
    assert model.get_component("clock").part == "ad9523_1"
    assert model.get_component("adc").part == "ad9680"
    assert model.get_component("dac").part == "ad9144"
    assert len(model.jesd_links) == 2
    assert model.get_jesd_link("rx") is not None
    assert model.get_jesd_link("tx") is not None

    # --- Stage 5: Render via BoardModelRenderer ---
    nodes = BoardModelRenderer().render(model)
    assert nodes["converters"], "No converter nodes rendered"
    assert nodes["jesd204_rx"], "No JESD204 RX nodes rendered"
    assert nodes["jesd204_tx"], "No JESD204 TX nodes rendered"

    # --- Stage 6: Merge with base DTS ---
    name = "fmcdaq2_board_model"
    _, merged_content = DtsMerger().merge(base_dts, nodes, out_dir, name)
    merged_dts = out_dir / f"{name}.dts"
    assert merged_dts.exists(), "Merged DTS not written"

    # Sanity check merged content
    assert "ad9523" in merged_content.lower(), "AD9523 clock not in merged DTS"
    assert (
        "ad9680" in merged_content.lower()
        or "ad_ip_jesd204_tpl_adc" in merged_content.lower()
    )
    assert (
        "ad9144" in merged_content.lower()
        or "ad_ip_jesd204_tpl_dac" in merged_content.lower()
    )

    # --- Stage 7: Compile to DTB ---
    dtb = out_dir / "system.dtb"
    compile_dts_to_dtb(merged_dts, dtb)
    assert dtb.exists(), "DTB compilation failed"

    # --- Stage 8: Deploy and boot ---
    kuiper = board.target.get_driver("KuiperDLDriver")
    kuiper.kuiper_resource.BOOTBIN_path = bootbin
    kuiper.get_boot_files_from_release()
    if built_kernel_image is not None:
        kuiper.add_files_to_target(built_kernel_image)
    kuiper.add_files_to_target(dtb)

    board.transition("shell")

    # --- Stage 9: Collect dmesg ---
    shell = board.target.get_driver("ADIShellDriver")
    dmesg_txt = shell_out(shell, "dmesg")
    (out_dir / "dmesg_fmcdaq2_board_model.log").write_text(dmesg_txt)

    # --- Stage 10: Verify IIO devices ---
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
