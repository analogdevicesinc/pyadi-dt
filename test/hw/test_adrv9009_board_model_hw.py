"""ADRV9009 + ZCU102 hardware test using the unified BoardModel.

Exercises the full BoardModel pipeline:
  XSA → sdtgen → topology → ADRV9009Builder.build_model() → BoardModelRenderer → DtsMerger → DTB → deploy → IIO verify

LG_ENV: /jenkins/lg_hw.yaml
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import iio
import pytest

from adidt.xsa.builders.adrv9009 import ADRV9009Builder
from adidt.xsa.pipeline import XsaPipeline
from adidt.xsa.topology import XsaParser
from test.hw.hw_helpers import DEFAULT_OUT_DIR, compile_dts_to_dtb, shell_out

LG_ENV_PATH = "/jenkins/lg_hw.yaml"
if not os.environ.get("LG_ENV"):
    pytest.skip(
        f"set LG_ENV={LG_ENV_PATH} for ADRV9009 BoardModel hardware test",
        allow_module_level=True,
    )

DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynqmp-zcu102-rev10-adrv9009"
DEFAULT_KUIPER_BOOTBIN = "release:zynqmp-zcu102-rev10-adrv9009/BOOT.BIN"
DEFAULT_VCXO_HZ = 122.88e6
DEFAULT_SAMPLE_RATE_HZ = 245.76e6

PS_CLK_LABEL = "zynqmp_clk"
PS_CLK_INDEX = 71
GPIO_LABEL = "gpio"


def _resolve_config_from_adijif(
    vcxo_hz: float = DEFAULT_VCXO_HZ,
    sample_rate_hz: float = DEFAULT_SAMPLE_RATE_HZ,
) -> dict[str, Any]:
    """Resolve ADRV9009 JESD + clock config via adijif solver."""
    import adijif

    sys = adijif.system("adrv9009", "ad9528", "xilinx", vcxo=vcxo_hz)
    sys.fpga.setup_by_dev_kit_name("zcu102")

    mode_rx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.adc, M=4, L=2, S=1, Np=16
    )
    mode_tx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.dac, M=4, L=4, S=1, Np=16
    )
    if not mode_rx or not mode_tx:
        raise RuntimeError("No matching ADRV9009 JESD modes found via adijif")

    sys.converter.adc.set_quick_configuration_mode(
        mode_rx[0]["mode"], mode_rx[0]["jesd_class"]
    )
    sys.converter.dac.set_quick_configuration_mode(
        mode_tx[0]["mode"], mode_tx[0]["jesd_class"]
    )
    sys.converter.adc.decimation = 8
    sys.converter.adc.sample_clock = sample_rate_hz
    sys.converter.dac.interpolation = 8
    sys.converter.dac.sample_clock = sample_rate_hz

    rx_settings = mode_rx[0]["settings"]
    tx_settings = mode_tx[0]["settings"]

    cfg: dict[str, Any] = {
        "jesd": {
            "rx": {k: int(rx_settings[k]) for k in ("F", "K", "M", "L", "Np", "S")},
            "tx": {k: int(tx_settings[k]) for k in ("F", "K", "M", "L", "Np", "S")},
        },
        "clock": {
            "rx_device_clk_label": "clkgen",
            "tx_device_clk_label": "clkgen",
            "hmc7044_rx_channel": 0,
            "hmc7044_tx_channel": 0,
        },
    }

    conf = sys.solve()
    for key in ("F", "K", "M", "L", "Np", "S"):
        rx_conf = conf.get("jesd_ADRV9009_RX", {})
        tx_conf = conf.get("jesd_ADRV9009_TX", {})
        if key in rx_conf:
            cfg["jesd"]["rx"][key] = int(rx_conf[key])
        if key in tx_conf:
            cfg["jesd"]["tx"][key] = int(tx_conf[key])

    return cfg


@pytest.fixture(scope="module")
def built_kernel_image(built_kernel_image_zynqmp: Path | None) -> Path | None:
    """Linux kernel image for ZCU102 (ZynqMP)."""
    return built_kernel_image_zynqmp


@pytest.mark.lg_feature(["adrv9009", "zcu102"])
def test_adrv9009_board_model(board, built_kernel_image, tmp_path):
    """End-to-end BoardModel test: XSA → ADRV9009Builder.build_model() → render → merge → deploy → IIO."""
    release = os.environ.get("ADI_KUIPER_BOOT_RELEASE", DEFAULT_KUIPER_RELEASE)
    project = os.environ.get("ADI_KUIPER_XSA_PROJECT", DEFAULT_KUIPER_PROJECT)
    bootbin = os.environ.get("ADI_KUIPER_BOOTBIN", DEFAULT_KUIPER_BOOTBIN)

    # --- Stage 1: Get XSA ---
    here = Path(__file__).parent
    xsa_path = here / "ref_data" / "system_top_adrv9009_zcu102.xsa"
    if not xsa_path.exists():
        from test.xsa.kuiper_release import download_project_xsa

        xsa_path = download_project_xsa(
            release=release,
            project_dir=project,
            cache_dir=tmp_path / "kuiper_cache",
            output_dir=tmp_path / "xsa",
        )
    assert xsa_path.exists(), f"XSA not found: {xsa_path}"

    # --- Stage 2: Resolve config + verify BoardModel ---
    topology = XsaParser().parse(xsa_path)
    cfg = _resolve_config_from_adijif()

    adrv9009_builder = ADRV9009Builder()
    assert adrv9009_builder.matches(topology, cfg), (
        "ADRV9009Builder did not match topology — wrong XSA?"
    )
    model = adrv9009_builder.build_model(
        topology, cfg, PS_CLK_LABEL, PS_CLK_INDEX, GPIO_LABEL
    )

    # Verify BoardModel structure
    assert model.name.startswith("adrv9009_")
    assert model.get_component("clock") is not None
    assert len(model.jesd_links) >= 2

    # --- Stage 3: Run full pipeline (sdtgen + NodeBuilder + merge + compile) ---
    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    result = XsaPipeline().run(
        xsa_path=xsa_path,
        cfg=cfg,
        output_dir=out_dir,
        sdtgen_timeout=300,
    )

    # --- Stage 4: Compile to DTB ---
    dtb = out_dir / "system.dtb"
    compile_dts_to_dtb(result["merged"], dtb)
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
    (out_dir / "dmesg_adrv9009_board_model.log").write_text(dmesg_txt)

    # --- Stage 10: Verify IIO devices ---
    addresses = shell.get_ip_addresses()
    ip_address = str(addresses[0].ip)
    if "/" in ip_address:
        ip_address = ip_address.split("/")[0]

    ctx = iio.Context(f"ip:{ip_address}")
    assert ctx is not None, "Failed to create IIO context"

    found = [d.name for d in ctx.devices]
    assert any(
        n in found for n in ("axi-adrv9009-rx-hpc", "adrv9009-phy", "ad9528-1")
    ), f"Expected ADRV9009 IIO device not found. Available: {found}"
