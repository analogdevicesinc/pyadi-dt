"""AD9084 + VCU118 hardware test using XSA-based device tree generation.

LG_ENV: /jenkins/lg_ad9084_vcu118.yaml
XSA: /jenkins/ref/ad9084_vcu118_slow/system_top_vcu118.xsa

Flow:
1. Verify prerequisites (LG_ENV, sdtgen, dtc).
2. Run XsaPipeline to parse XSA and generate merged DTS.
3. Copy merged DTS into the MicroBlaze kernel source tree.
4. Build simpleImage (kernel + embedded DTB) via pyadi-build.
5. Deploy via JTAG.
6. Boot and verify AD9084 RX IIO device is present.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from pprint import pprint

import pytest

from adidt.xsa.pipeline import XsaPipeline


LG_ENV_PATH = "/jenkins/lg_ad9084_vcu118.yaml"
XSA_PATH = Path("/jenkins/ref/ad9084_vcu118_slow/system_top_vcu118.xsa")
DTS_NAME = "vcu118_ad9084_xsa"

HERE = Path(__file__).parent
OUT_DIR = HERE / "output_xsa_vcu118"


def _require_lg_env() -> None:
    if os.environ.get("LG_ENV") != LG_ENV_PATH:
        pytest.skip(f"set LG_ENV={LG_ENV_PATH} to run this hardware test")
    if not Path(LG_ENV_PATH).exists():
        pytest.skip(f"required labgrid env file missing: {LG_ENV_PATH}")


def _require_tools() -> None:
    if shutil.which("sdtgen") is None:
        pytest.skip("sdtgen not found on PATH (Vivado tools required)")
    if shutil.which("dtc") is None:
        pytest.skip("dtc not found on PATH")


def _build_xsa_pipeline_cfg() -> dict:
    """Return XsaPipeline config for the AD9084 slow profile on VCU118.

    The XSA topology (addresses, lane counts, JESD core instances) is derived
    from the XSA itself by the pipeline.  This dict supplies JESD framing
    parameters, clock mapping, and board-level SPI/clock configuration
    consumed by the AD9084 NodeBuilder path.
    """
    return {
        "jesd": {
            "rx": {"F": 6, "K": 32, "M": 4, "L": 8, "Np": 12, "S": 1},
            "tx": {"F": 6, "K": 32, "M": 4, "L": 8, "Np": 12, "S": 1},
        },
        "clock": {
            # JESD device_clk comes from HMC7044 channels, not clkgen.
            # Per-link device_clk channels: RX=8, RX_B=11, TX=9, TX_B=12
            "rx_device_clk_label": "hmc7044",
            "rx_device_clk_index": 8,
            "tx_device_clk_label": "hmc7044",
            "tx_device_clk_index": 9,
            "rx_b_device_clk_index": 11,
            "tx_b_device_clk_index": 12,
        },
        "ad9084_board": {
            # SPI bus assignments (from VCU118 HDL design)
            "converter_spi": "axi_spi_2",
            "converter_cs": 0,
            "clock_spi": "axi_spi",
            "hmc7044_cs": 1,
            "pll1_clkin_frequencies": [
                125_000_000,
                125_000_000,
                125_000_000,
                125_000_000,
            ],
            # HMC7044 clock configuration
            "vcxo_hz": 125_000_000,
            "pll2_output_hz": 2_500_000_000,
            # HMC7044 channel that provides FPGA GTY reference clock
            "fpga_refclk_channel": 10,
            # AD9084 dev_clk from ADF4382 (not HMC7044)
            "dev_clk_source": "adf4382",
            "dev_clk_ref": "adf4382 0",
            "dev_clk_scales": "1 10",
            # ADF4382 PLL on SPI0 CS0
            "adf4382_cs": 0,
            # XCVR PLL selection (QPLL for VCU118 GTY)
            "rx_sys_clk_select": 3,
            "tx_sys_clk_select": 3,
            "rx_out_clk_select": 4,
            "tx_out_clk_select": 4,
            # JESD204 link IDs (from dt-bindings/iio/adc/adi,ad9088.h)
            "rx_a_link_id": 4,  # FRAMER_LINK_A0_RX
            "rx_b_link_id": 6,  # FRAMER_LINK_B0_RX
            "tx_a_link_id": 0,  # DEFRAMER_LINK_A0_TX
            "tx_b_link_id": 2,  # DEFRAMER_LINK_B0_TX
            # Device profile firmware loaded by the ad9088 driver
            "firmware_name": "204C_M4_L8_NP16_1p25_4x4.bin",
            # Hardware reset GPIO (active high) on VCU118 axi_gpio
            "reset_gpio": 62,
            # JESD204C subclass (0 = standard, 1 = with AION)
            "subclass": 0,
            # Side-B uses separate TPL core (ASYNM_A_B_MODE)
            "side_b_separate_tpl": True,
            # Lane mappings (from reference DTS for VCU118 AD9084)
            "jrx0_physical_lane_mapping": "10 8 9 11 5 1 3 7 4 6 2 0",
            "jtx0_logical_lane_mapping": "11 2 3 5 10 1 9 0 6 7 8 4",
            "jrx1_physical_lane_mapping": "4 6 2 0 1 7 10 3 5 8 9 11",
            "jtx1_logical_lane_mapping": "3 9 5 4 2 6 1 7 8 11 0 10",
            # HMC7044 tuning (from reference DTS)
            "pulse_generator_mode": 7,  # HMC7044_PULSE_GEN_CONT_PULSE
            "oscin_buffer_mode": "0x05",
            # HSCI connection
            "hsci_label": "axi_hsci_0",
            "hsci_auto_linkup": True,
            # Override HMC7044 channel config
            "hmc7044_channels": [
                {"id": 1, "name": "ADF4030_REFIN", "divider": 20, "driver_mode": 2},
                {
                    "id": 3,
                    "name": "ADF4030_BSYNC0",
                    "divider": 512,
                    "driver_mode": 1,
                    "is_sysref": True,
                },
                {"id": 8, "name": "CORE_CLK_TX", "divider": 8, "driver_mode": 2},
                {"id": 9, "name": "CORE_CLK_RX", "divider": 8, "driver_mode": 2},
                {"id": 10, "name": "FPGA_REFCLK", "divider": 8, "driver_mode": 2},
                {"id": 11, "name": "CORE_CLK_RX_B", "divider": 8, "driver_mode": 2},
                {"id": 12, "name": "CORE_CLK_TX_B", "divider": 8, "driver_mode": 2},
            ],
        },
    }


@pytest.mark.lg_feature(["ad9084", "vcu118"])
def test_ad9084_vcu118_xsa(target):
    _require_lg_env()
    _require_tools()

    assert XSA_PATH.exists(), f"XSA not found: {XSA_PATH}"

    try:
        from adibuild import LinuxBuilder, BuildConfig
        from adibuild.platforms import MicroBlazePlatform
    except ModuleNotFoundError as ex:
        pytest.skip(f"pyadi-build dependency missing: {ex}")

    cfg = _build_xsa_pipeline_cfg()

    # 1. Run XSA pipeline: sdtgen → parse topology → render nodes → merge DTS
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result = XsaPipeline().run(
        xsa_path=XSA_PATH,
        cfg=cfg,
        output_dir=OUT_DIR,
        sdtgen_timeout=300,
    )
    merged_dts = result["merged"]
    assert merged_dts.exists(), f"Merged DTS not generated: {merged_dts}"
    print(f"Generated merged DTS: {merged_dts}")

    # 2. Prepare MicroBlaze kernel build
    config_path = HERE / "2023_R2.yaml"
    build_config = BuildConfig.from_yaml(config_path)
    platform_config = build_config.get_platform("microblaze")
    platform = MicroBlazePlatform(platform_config)
    builder = LinuxBuilder(build_config, platform)
    builder.prepare_source()
    kernel_path = builder.repo.local_path

    # 3. Copy XSA-generated merged DTS + base includes into the kernel source tree
    dts_dir = kernel_path / "arch" / "microblaze" / "boot" / "dts"
    dts_dest = dts_dir / f"{DTS_NAME}.dts"
    shutil.copy(merged_dts, dts_dest)
    print(f"Copied merged DTS to: {dts_dest}")

    # Copy base SDT files (pl.dtsi etc.) that the merged DTS #includes
    base_dir = result["base_dir"]
    for f in base_dir.iterdir():
        if f.is_file():
            shutil.copy(f, dts_dir / f.name)
    print(f"Copied base SDT files from: {base_dir}")

    # 4. Configure and build simpleImage (kernel with embedded DTB)
    platform_config["simpleimage_targets"] = [f"simpleImage.{DTS_NAME}"]
    builder.configure()

    # Ensure the AD9084 profile firmware is included in CONFIG_EXTRA_FIRMWARE
    # so it gets embedded into the simpleImage initramfs.
    fw_name = cfg.get("ad9084_board", {}).get("firmware_name")
    if fw_name:
        # Copy profile firmware from test profiles to kernel firmware dir
        profile_src = HERE / "profiles" / "vcu118" / fw_name
        fw_dir = kernel_path / "firmware"
        if profile_src.exists():
            shutil.copy(profile_src, fw_dir / fw_name)
            print(f"Copied firmware {fw_name} ({profile_src.stat().st_size} bytes)")

        dot_config = kernel_path / ".config"
        config_text = dot_config.read_text()
        if fw_name not in config_text:
            config_text = config_text.replace(
                'CONFIG_EXTRA_FIRMWARE="',
                f'CONFIG_EXTRA_FIRMWARE="{fw_name} ',
            )
            dot_config.write_text(config_text)
            print(f"Added {fw_name} to CONFIG_EXTRA_FIRMWARE")

    images = builder.build_kernel()

    # 5. Deploy via JTAG
    xilinx_device_jtag = target.get_resource("XilinxDeviceJTAG")
    xilinx_device_jtag.kernel_path = str(images[0])
    if not xilinx_device_jtag.kernel_path.endswith(".strip"):
        xilinx_device_jtag.kernel_path += ".strip"

    print(f"Deploying: {xilinx_device_jtag.kernel_path}")

    strategy = target.get_driver("Strategy")
    # Disable DHCP reset — XSA-generated DTS may not include full ethernet
    # bindings (phy-mode, phy-handle etc.) so networking is not guaranteed.
    # This test only needs serial console access for IIO verification.
    strategy.trigger_dhcp_reset = False
    strategy.transition("powered_off")
    strategy.transition("shell")

    # 6. Verify IIO devices
    shell = target.get_driver("ADIShellDriver")

    dmesg = shell.run_check("dmesg | grep -i 'ad9084\\|jesd\\|spi' | tail -40; true")
    print("\n=== DMESG (ad9084/jesd/spi) ===")
    for line in dmesg:
        print(line)
    print("================================")

    iio_names = shell.run_check("cat /sys/bus/iio/devices/*/name 2>/dev/null; true")
    print(f"IIO device names present: {iio_names}")

    # The AD9084 converter driver (ad9088) creates bmem and fft-sniffer
    # IIO devices.  The TPL RX core creates a separate IIO device whose
    # name depends on the DT node name (from sdtgen).  Check for the
    # converter driver first, then the TPL core.
    ad9084_search = shell.run_check(
        "for d in /sys/bus/iio/devices/iio:device*; do "
        'name=$(cat "$d/name" 2>/dev/null); '
        'case "$name" in ad9088*|axi-ad9084*|ad_ip_jesd204_tpl_adc*) echo "$d $name";; esac; '
        "done; true"
    )

    assert ad9084_search, (
        f"No AD9084-related IIO devices found. IIO devices present: {iio_names}"
    )
    print(f"Found AD9084 RX device: {ad9084_search[0].strip()}")
