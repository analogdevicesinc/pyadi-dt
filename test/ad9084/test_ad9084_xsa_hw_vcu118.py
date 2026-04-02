"""AD9084 + VCU118 hardware test using XSA-based device tree generation.

LG_ENV: /jenkins/lg_ad9084_vcu118.yaml
XSA: /jenkins/ref/ad9084_vcu118_slow/system_top_vcu118.xsa

Flow:
1. Verify prerequisites (LG_ENV, sdtgen, dtc).
2. Run XsaPipeline with the ad9084_vcu118 profile to generate merged DTS.
3. Copy merged DTS into the MicroBlaze kernel source tree.
4. Build simpleImage (kernel + embedded DTB) via pyadi-build.
5. Deploy via JTAG.
6. Boot and verify AD9084 RX IIO device is present.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

pytest.importorskip("labgrid", reason="labgrid not installed")

from adidt.xsa.pipeline import XsaPipeline
from adidt.xsa.profiles import ProfileManager


PROFILE_NAME = "ad9084_vcu118"
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

    # 1. Run XSA pipeline: sdtgen → parse topology → render nodes → merge DTS
    #    All board config (SPI, clocks, lane mappings, JESD params) comes from
    #    the ad9084_vcu118 profile — no manual cfg dict needed.
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result = XsaPipeline().run(
        xsa_path=XSA_PATH,
        cfg={},
        output_dir=OUT_DIR,
        profile=PROFILE_NAME,
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
    profile_data = ProfileManager().load(PROFILE_NAME)
    fw_name = profile_data["defaults"].get("ad9084_board", {}).get("firmware_name")
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
