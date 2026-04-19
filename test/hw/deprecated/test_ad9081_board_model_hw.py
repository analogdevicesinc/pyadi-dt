"""AD9081 + ZCU102 hardware test using the unified BoardModel.

Exercises the full BoardModel pipeline:
  XSA → sdtgen → topology → AD9081Builder.build_model() → BoardModelRenderer → DtsMerger → DTB → deploy → IIO verify

LG_ENV: /jenkins/lg_ad9081_zcu102.yaml
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import iio
import pytest

from adidt.model.renderer import BoardModelRenderer
from adidt.xsa.board_fixups import apply_board_fixups
from adidt.xsa.builders.ad9081 import AD9081Builder
from adidt.xsa.merger import DtsMerger
from adidt.xsa.profiles import ProfileManager, merge_profile_defaults
from adidt.xsa.sdtgen import SdtgenRunner
from adidt.xsa.topology import XsaParser
from test.hw.hw_helpers import DEFAULT_OUT_DIR, compile_dts_to_dtb, shell_out

LG_ENV_PATH = "/jenkins/lg_ad9081_zcu102.yaml"
if not os.environ.get("LG_ENV"):
    pytest.skip(
        f"set LG_ENV={LG_ENV_PATH} for AD9081 BoardModel hardware test",
        allow_module_level=True,
    )

DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynqmp-zcu102-rev10-ad9081"
DEFAULT_KUIPER_BOOTBIN = "release:zynqmp-zcu102-rev10-ad9081/m8_l4/BOOT.BIN"
DEFAULT_VCXO_HZ = 122.88e6

PS_CLK_LABEL = "zynqmp_clk"
PS_CLK_INDEX = 71
GPIO_LABEL = "gpio"

_SYS_CLK_SELECT_MAP = {
    "XCVR_CPLL": 0,
    "XCVR_QPLL1": 2,
    "XCVR_QPLL0": 3,
}
_OUT_CLK_SELECT_MAP = {
    "XCVR_REFCLK": 4,
    "XCVR_REFCLK_DIV2": 4,
}


def _resolve_config_from_adijif(vcxo_hz: float = DEFAULT_VCXO_HZ) -> dict[str, Any]:
    """Resolve AD9081 JESD + clock config via adijif solver."""
    import adijif

    sys = adijif.system("ad9081", "hmc7044", "xilinx", vcxo=vcxo_hz)
    sys.fpga.setup_by_dev_kit_name("zcu102")

    cddc, fddc = 4, 4
    cduc, fduc = 8, 6

    sys.converter.clocking_option = "integrated_pll"
    sys.converter.adc.sample_clock = 4_000_000_000 / cddc / fddc
    sys.converter.dac.sample_clock = 12_000_000_000 / cduc / fduc

    sys.converter.adc.datapath.cddc_decimations = [cddc] * 4
    sys.converter.dac.datapath.cduc_interpolation = cduc
    sys.converter.adc.datapath.fddc_decimations = [fddc] * 8
    sys.converter.dac.datapath.fduc_interpolation = fduc
    sys.converter.adc.datapath.fddc_enabled = [True] * 8
    sys.converter.dac.datapath.fduc_enabled = [True] * 8

    mode_rx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.adc, M=8, L=4, Np=16, jesd_class="jesd204b"
    )
    mode_tx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.dac, M=8, L=4, Np=16, jesd_class="jesd204b"
    )
    if not mode_rx or not mode_tx:
        raise RuntimeError("No matching AD9081 JESD modes found via adijif")

    sys.converter.adc.set_quick_configuration_mode(
        mode_rx[0]["mode"], mode_rx[0]["jesd_class"]
    )
    sys.converter.dac.set_quick_configuration_mode(
        mode_tx[0]["mode"], mode_tx[0]["jesd_class"]
    )

    rx_settings = mode_rx[0]["settings"]
    tx_settings = mode_tx[0]["settings"]

    cfg: dict[str, Any] = {
        "jesd": {
            "rx": {k: int(rx_settings[k]) for k in ("F", "K", "M", "L", "Np", "S")},
            "tx": {k: int(tx_settings[k]) for k in ("F", "K", "M", "L", "Np", "S")},
        },
        "clock": {
            "rx_device_clk_label": "hmc7044",
            "tx_device_clk_label": "hmc7044",
            "hmc7044_rx_channel": 10,
            "hmc7044_tx_channel": 6,
        },
        "ad9081": {
            "rx_link_mode": int(float(mode_rx[0]["mode"])),
            "tx_link_mode": int(float(mode_tx[0]["mode"])),
            "adc_frequency_hz": int(sys.converter.adc.sample_clock * cddc * fddc),
            "dac_frequency_hz": int(sys.converter.dac.sample_clock * cduc * fduc),
            "rx_cddc_decimation": cddc,
            "rx_fddc_decimation": fddc,
            "tx_cduc_interpolation": cduc,
            "tx_fduc_interpolation": fduc,
        },
    }

    conf = sys.solve()
    rx_fpga = conf.get("fpga_adc", {})
    tx_fpga = conf.get("fpga_dac", {})
    cfg["ad9081"]["rx_sys_clk_select"] = int(
        _SYS_CLK_SELECT_MAP.get(str(rx_fpga.get("sys_clk_select", "")).upper(), 0)
    )
    cfg["ad9081"]["tx_sys_clk_select"] = int(
        _SYS_CLK_SELECT_MAP.get(str(tx_fpga.get("sys_clk_select", "")).upper(), 0)
    )
    cfg["ad9081"]["rx_out_clk_select"] = int(
        _OUT_CLK_SELECT_MAP.get(str(rx_fpga.get("out_clk_select", "")).upper(), 4)
    )
    cfg["ad9081"]["tx_out_clk_select"] = int(
        _OUT_CLK_SELECT_MAP.get(str(tx_fpga.get("out_clk_select", "")).upper(), 4)
    )
    for key in ("F", "K", "M", "L", "Np", "S"):
        rx_conf = conf.get("jesd_AD9081_RX", {})
        tx_conf = conf.get("jesd_AD9081_TX", {})
        if key in rx_conf:
            cfg["jesd"]["rx"][key] = int(rx_conf[key])
        if key in tx_conf:
            cfg["jesd"]["tx"][key] = int(tx_conf[key])

    return cfg


@pytest.fixture(scope="module")
def built_kernel_image(built_kernel_image_zynqmp: Path | None) -> Path | None:
    """Linux kernel image for ZCU102 (ZynqMP)."""
    return built_kernel_image_zynqmp


@pytest.mark.lg_feature(["ad9081", "zcu102"])
def test_ad9081_board_model(board, built_kernel_image, tmp_path):
    """End-to-end BoardModel test: XSA → AD9081Builder.build_model() → render → merge → deploy → IIO."""
    release = os.environ.get("ADI_KUIPER_BOOT_RELEASE", DEFAULT_KUIPER_RELEASE)
    project = os.environ.get("ADI_KUIPER_XSA_PROJECT", DEFAULT_KUIPER_PROJECT)
    bootbin = os.environ.get("ADI_KUIPER_BOOTBIN", DEFAULT_KUIPER_BOOTBIN)

    # --- Stage 1: Get XSA ---
    here = Path(__file__).parent
    xsa_path = here / "system_top.xsa"
    if not xsa_path.exists():
        from test.xsa.kuiper_release import download_project_xsa

        xsa_path = download_project_xsa(
            release=release,
            project_dir=project,
            cache_dir=tmp_path / "kuiper_cache",
            output_dir=tmp_path / "xsa",
        )
    assert xsa_path.exists(), f"XSA not found: {xsa_path}"

    # --- Stage 2: Run sdtgen for base DTS ---
    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    base_dir = out_dir / "base"
    base_dir.mkdir(exist_ok=True)
    base_dts_path = SdtgenRunner().run(xsa_path, base_dir, timeout=300)
    apply_board_fixups("ad9081_zcu102", base_dir)
    base_dts = base_dts_path.read_text()

    # --- Stage 3: Parse topology + resolve config ---
    topology = XsaParser().parse(xsa_path)
    cfg = _resolve_config_from_adijif()

    profile_data = ProfileManager().load("ad9081_zcu102")
    if profile_data:
        cfg = merge_profile_defaults(cfg, profile_data)

    # --- Stage 4: Build BoardModel ---
    ad9081_builder = AD9081Builder()
    assert ad9081_builder.matches(topology, cfg), (
        "AD9081Builder did not match topology — wrong XSA?"
    )
    model = ad9081_builder.build_model(
        topology, cfg, PS_CLK_LABEL, PS_CLK_INDEX, GPIO_LABEL
    )

    # Verify model structure
    assert model.name.startswith("ad9081_")
    assert model.get_component("clock") is not None
    assert model.get_component("clock").part == "hmc7044"
    assert (
        model.get_component("transceiver") is not None
        or model.get_component("adc") is not None
    )
    assert len(model.jesd_links) >= 2
    assert model.get_jesd_link("rx") is not None
    assert model.get_jesd_link("tx") is not None

    # --- Stage 5: Render via BoardModelRenderer ---
    nodes = BoardModelRenderer().render(model)
    assert nodes["converters"], "No converter nodes rendered"

    # --- Stage 6: Merge with base DTS ---
    name = "ad9081_board_model"
    _, merged_content = DtsMerger().merge(base_dts, nodes, out_dir, name)
    merged_dts = out_dir / f"{name}.dts"
    assert merged_dts.exists(), "Merged DTS not written"

    assert "hmc7044" in merged_content.lower(), "HMC7044 clock not in merged DTS"
    assert "ad9081" in merged_content.lower(), "AD9081 not in merged DTS"

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
    (out_dir / "dmesg_ad9081_board_model.log").write_text(dmesg_txt)

    # --- Stage 10: Verify IIO devices ---
    addresses = shell.get_ip_addresses()
    ip_address = str(addresses[0].ip)
    if "/" in ip_address:
        ip_address = ip_address.split("/")[0]

    ctx = iio.Context(f"ip:{ip_address}")
    assert ctx is not None, "Failed to create IIO context"

    found = [d.name for d in ctx.devices]
    assert "hmc7044" in found, (
        f"Expected IIO clock device 'hmc7044' not found. Available: {found}"
    )
    assert any(n in found for n in ("axi-ad9081-rx-hpc", "ad_ip_jesd204_tpl_adc")), (
        f"Expected AD9081 RX IIO device not found. Available: {found}"
    )
    assert any(n in found for n in ("axi-ad9081-tx-hpc", "ad_ip_jesd204_tpl_dac")), (
        f"Expected AD9081 TX IIO device not found. Available: {found}"
    )
