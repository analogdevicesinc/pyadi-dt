"""ADRV9009+ZCU102 Hardware Test Suite

This module tests ADRV9009 FMC board on ZCU102
Test Flow:
1. Generate configuration for sample rate
2. Generate DTS file
3. Compile DTS to DTB
4. Power off board
5. Deploy DTB via KuiperDLDriver
6. Boot to shell
7. Create IIO context
8. Verify ADC and DAC devices present

Requirements:
- Linux kernel source (via LINUX_KERNEL_PATH env var)
- LABGRID environment with ZCU102 configuration
- ADRV9009 hardware on ZCU102
"""

import pytest
import os
import shutil
import subprocess
import urllib.request
import tarfile
from pathlib import Path
from adidt.boards.adrv9009_fmc import adrv9009_fmc
import iio
import adijif


# ARM GNU Toolchain configuration for cross-compiling ARM64 device trees
TOOLCHAIN_URL_ARM64 = "https://developer.arm.com/-/media/Files/downloads/gnu/12.2.rel1/binrel/arm-gnu-toolchain-12.2.rel1-x86_64-aarch64-none-elf.tar.xz"
TOOLCHAIN_VERSION = "12.2.rel1"
TOOLCHAIN_ARCH_ARM64 = "aarch64-none-elf"

# ARM32 Toolchain configuration for ZC706 (Zynq-7000)
TOOLCHAIN_URL_ARM32 = "https://developer.arm.com/-/media/Files/downloads/gnu/12.2.rel1/binrel/arm-gnu-toolchain-12.2.rel1-x86_64-arm-none-eabi.tar.xz"
TOOLCHAIN_ARCH_ARM32 = "arm-none-eabi"


def download_and_cache_toolchain(arch: str = "arm64", cache_dir: Path = None) -> Path:
    """Download and cache ARM GNU toolchain for cross-compilation.

    Downloads the ARM GNU toolchain for arm or arm64 from ARM's official site
    and extracts it to a cache directory. If already cached, skips download.

    Args:
        arch: Target architecture ('arm' or 'arm64')
        cache_dir: Directory to cache toolchain. Defaults to ~/.cache/pyadi-dt/

    Returns:
        Path to toolchain bin directory containing cross-compiler

    Raises:
        RuntimeError: If download or extraction fails or arch is invalid
    """
    # Select toolchain based on architecture
    if arch == "arm64":
        toolchain_url = TOOLCHAIN_URL_ARM64
        toolchain_arch = TOOLCHAIN_ARCH_ARM64
    elif arch == "arm":
        toolchain_url = TOOLCHAIN_URL_ARM32
        toolchain_arch = TOOLCHAIN_ARCH_ARM32
    else:
        raise ValueError(f"Unsupported architecture: {arch}. Must be 'arm' or 'arm64'")

    # Determine cache directory
    if cache_dir is None:
        cache_dir = Path.home() / ".cache" / "pyadi-dt" / "toolchains"
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Expected toolchain directory after extraction
    toolchain_name = f"arm-gnu-toolchain-{TOOLCHAIN_VERSION}-x86_64-{toolchain_arch}"
    toolchain_dir = cache_dir / toolchain_name
    toolchain_bin = toolchain_dir / "bin"

    # Check if already cached
    if toolchain_bin.exists():
        print(f"      Using cached toolchain: {toolchain_dir}")
        return toolchain_bin

    # Download toolchain
    print(f"      Downloading ARM GNU toolchain {TOOLCHAIN_VERSION} ({arch})...")
    tarball_path = cache_dir / f"{toolchain_name}.tar.xz"

    try:
        with urllib.request.urlopen(toolchain_url) as response:
            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0
            chunk_size = 1024 * 1024  # 1MB chunks

            with open(tarball_path, "wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(
                            f"      Progress: {percent:.1f}% ({downloaded // (1024 * 1024)}MB / {total_size // (1024 * 1024)}MB)",
                            end="\r",
                        )

        print(f"\n      Download complete: {tarball_path}")

        # Extract toolchain
        print("      Extracting toolchain...")
        with tarfile.open(tarball_path, "r:xz") as tar:
            tar.extractall(cache_dir)

        # Verify extraction
        if not toolchain_bin.exists():
            raise RuntimeError(
                f"Toolchain extraction failed: {toolchain_bin} not found"
            )

        # Clean up tarball to save space
        tarball_path.unlink()
        print(f"      Toolchain ready: {toolchain_bin}")

        return toolchain_bin

    except Exception as e:
        # Clean up on failure
        if tarball_path.exists():
            tarball_path.unlink()
        raise RuntimeError(f"Failed to download/extract toolchain: {e}")


def get_adrv9009_config() -> dict:
    """Get ADRV9009 configuration.

    Returns:
        Complete configuration dict for adrv9009_fmc board
    """
    vcxo = 122880000
    sys = adijif.system("adrv9009", "ad9528", "xilinx", vcxo)
    sys.fpga.setup_by_dev_kit_name("zcu102")

    cfg = sys.solve()

    # Map generated keys to expected keys for adidt
    clks = cfg["clock"]["output_clocks"]

    clks["DEV_CLK"] = clks.pop("ADRV9009_ref_clk")
    clks["DEV_CLK"]["channel"] = 13
    clks["DEV_SYSREF"] = clks.pop("adc_sysref")
    clks["DEV_SYSREF"]["channel"] = 12
    clks["FMC_CLK"] = clks.pop("zcu102_adc_ref_clk")
    clks["FMC_CLK"]["channel"] = 1
    clks["FMC_SYSREF"] = clks.pop("dac_sysref")
    clks["FMC_SYSREF"]["channel"] = 3

    # Not used but need to be removed
    clks.pop("zcu102_adc_device_clk")
    clks.pop("zcu102_dac_ref_clk")
    clks.pop("zcu102_dac_device_clk")

    return cfg


def compile_dts_to_dtb(
    dts_path: Path,
    dtb_path: Path,
    kernel_path: str,
    arch: str = "arm64",
    cross_compile: str = None,
) -> None:
    """Compile DTS to DTB using kernel build system with cross-compiler."""
    # Validate architecture
    if arch not in ["arm", "arm64"]:
        raise ValueError(f"Unsupported architecture: {arch}. Must be 'arm' or 'arm64'")

    # Download and cache cross-compiler if not provided
    if cross_compile is None:
        print(f"      Setting up {arch.upper()} cross-compiler...")
        toolchain_bin = download_and_cache_toolchain(arch=arch)

        if arch == "arm64":
            cross_compile = f"{toolchain_bin}/{TOOLCHAIN_ARCH_ARM64}-"
        else:  # arch == "arm"
            cross_compile = f"{toolchain_bin}/{TOOLCHAIN_ARCH_ARM32}-"

        print(f"      ✓ Cross-compiler ready: {cross_compile}")

    # Set up environment for kernel compilation
    env = os.environ.copy()
    env["ARCH"] = arch
    env["CROSS_COMPILE"] = cross_compile

    # Determine platform-specific paths
    dts_filename = dts_path.name
    if arch == "arm64":
        kernel_dts_dir = Path(kernel_path) / "arch" / arch / "boot" / "dts" / "xilinx"
    else:
        kernel_dts_dir = Path(kernel_path) / "arch" / arch / "boot" / "dts"
    kernel_dts_path = kernel_dts_dir / dts_filename

    # DTB will be compiled to same location with .dtb extension
    kernel_dtb_path = kernel_dts_path.with_suffix(".dtb")

    # Step 1: Copy DTS file into kernel tree
    shutil.copy2(dts_path, kernel_dts_path)

    # Step 2: Ensure kernel is configured
    print("      Configuring kernel...")

    if arch == "arm64":
        defconfig = "adi_zynqmp_defconfig"
    else:
        defconfig = "zynq_xcomm_adv7511_defconfig"

    config_cmd = ["make", defconfig]
    print(f"      Running: {' '.join(config_cmd)}")
    config_result = subprocess.run(
        config_cmd, cwd=kernel_path, capture_output=True, text=True, env=env
    )
    if config_result.returncode != 0:
        raise RuntimeError(f"Kernel configuration failed: {config_result.stderr}")
    print("      Kernel configured.")

    # Step 3: Compile DTB using kernel make system
    print("      Compiling DTB...")
    if arch == "arm64":
        make_target = f"xilinx/{dts_filename.replace('.dts', '.dtb')}"
    else:
        make_target = f"{dts_filename.replace('.dts', '.dtb')}"
    make_cmd = ["make", make_target]
    print(f"      Running: {' '.join(make_cmd)}")

    make_result = subprocess.run(
        make_cmd, cwd=kernel_path, capture_output=True, text=True, env=env
    )

    if make_result.returncode != 0:
        raise RuntimeError(
            f"DTB compilation failed:\n"
            f"Command: {' '.join(make_cmd)}\n"
            f"ARCH={env['ARCH']} CROSS_COMPILE={env['CROSS_COMPILE']}\n"
            f"Error: {make_result.stderr}"
        )

    # Step 4: Verify DTB was created
    if not kernel_dtb_path.exists():
        raise RuntimeError(f"DTB file not created at {kernel_dtb_path}")

    # Step 5: Copy compiled DTB to desired output location
    shutil.copy2(kernel_dtb_path, dtb_path)


class adrv9009_fmc_no_plugin(adrv9009_fmc):
    """ADRV9009 FMC board with plugin mode disabled"""

    use_plugin_mode = False


@pytest.fixture(scope="module")
def kernel_path():
    """Get kernel path from environment or use default."""
    path = os.environ.get("LINUX_KERNEL_PATH", "./linux")
    if not os.path.exists(path):
        pytest.skip(f"Linux kernel source not found at {path}")
    return path


@pytest.fixture(scope="module")
def dtb_output_dir(tmp_path_factory):
    """Create temporary directory for DTB files."""
    return tmp_path_factory.mktemp("adrv9009_dtbs")


@pytest.fixture(scope="module")
def post_power_off(strategy):
    """Ensure board powers off after all tests."""
    yield strategy
    # strategy.transition("soft_off")


# Test class


class TestADRV9009Hardware:
    """Hardware test suite for ADRV9009"""

    @pytest.mark.skip(
        reason="Not fully verified. All profile fields not generated from jif."
    )
    @pytest.mark.lg_feature(["adrv9009", "zcu102"])
    def test_hw_deployment(self, kernel_path, dtb_output_dir, post_power_off):
        strategy = post_power_off

        # Step 1: Generate configuration
        print("[1/9] Generating configuration...")
        config = get_adrv9009_config()

        # Step 2: Generate DTS
        print("[2/9] Generating DTS file...")
        board = adrv9009_fmc_no_plugin(platform="zcu102", kernel_path=kernel_path)
        config = board.validate_and_default_fpga_config(config)

        dts_filename = dtb_output_dir / "adrv9009.dts"
        board.output_filename = str(dts_filename)

        clock, rx, tx, orx, fpga = board.map_clocks_to_board_layout(config)
        generated_dts = board.gen_dt(
            clock=clock,
            rx=rx,
            tx=tx,
            orx=orx,
            fpga=fpga,
            config_source="from_pyadi_jif",
        )

        assert os.path.exists(generated_dts), f"DTS file not generated: {generated_dts}"
        print(f"      ✓ Generated DTS: {generated_dts}")

        # Step 3: Compile DTS to DTB using kernel build system
        print("[3/9] Compiling DTS to DTB...")
        dtb_filename = dtb_output_dir / "adrv9009.dtb"

        arch = board.platform_config["arch"]

        compile_dts_to_dtb(
            dts_path=Path(generated_dts),
            dtb_path=dtb_filename,
            kernel_path=kernel_path,
            arch=arch,
        )

        assert dtb_filename.exists(), f"DTB file not created: {dtb_filename}"
        assert dtb_filename.stat().st_size > 0, "DTB file is empty"
        print(
            f"      ✓ Compiled DTB: {dtb_filename} ({dtb_filename.stat().st_size} bytes)"
        )

        # Step 4: Power off board
        print("[4/9] Powering off board...")
        strategy.transition("powered_off")
        print("      ✓ Board powered off")

        # Step 5: Deploy DTB
        print("[5/9] Deploying DTB to board...")
        kuiper = strategy.target.get_driver("KuiperDLDriver")
        os.rename(dtb_filename, dtb_output_dir / "system.dtb")
        kuiper.add_files_to_target(str(dtb_output_dir / "system.dtb"))
        print("      ✓ DTB deployed")

        # Step 6: Boot to shell
        print("[6/9] Booting board...")
        strategy.transition("shell")
        print("      ✓ Board booted successfully")

        # Step 7: Create IIO context
        print("[7/9] Creating IIO context...")
        shell = strategy.target.get_driver("ADIShellDriver")
        addresses = shell.get_ip_addresses()
        ip_address = str(addresses[0].ip)
        if "/" in ip_address:
            ip_address = ip_address.split("/")[0]

        ctx = iio.Context(f"ip:{ip_address}")
        assert ctx is not None, "Failed to create IIO context"
        print(f"      ✓ IIO context created at {ip_address}")

        # Step 8: Extract kernel log for debugging
        print("[8/9] Extracting kernel log for debugging...")
        dmesg_res = shell.run("dmesg")
        if isinstance(dmesg_res, tuple):
            dmesg_output = dmesg_res[0]
        else:
            dmesg_output = dmesg_res

        if isinstance(dmesg_output, list):
            dmesg_output = "\n".join(dmesg_output)

        dmesg_log_path = dtb_output_dir / "dmesg.log"
        with open(dmesg_log_path, "w") as f:
            f.write(dmesg_output)
        print(f"      ✓ Kernel log saved: {dmesg_log_path}")
        dmesg_err_res = shell.run("dmesg --level=err,warn")
        if isinstance(dmesg_err_res, tuple):
            dmesg_error_output = dmesg_err_res[0]
        else:
            dmesg_error_output = dmesg_err_res

        if isinstance(dmesg_error_output, list):
            dmesg_error_output = "\n".join(dmesg_error_output)

        dmesg_error_log_path = dtb_output_dir / "dmesg_errors.log"
        with open(dmesg_error_log_path, "w") as f:
            f.write(dmesg_error_output)
        print(f"      ✓ Kernel error/warn log saved: {dmesg_error_log_path}")

        # Step 9: Verify devices
        print("[9/9] Verifying IIO devices...")
        expected_devices = ["axi-adrv9009-rx-hpc", "axi-adrv9009-tx-hpc"]
        found_devices = [d.name for d in ctx.devices]

        for device_name in expected_devices:
            assert device_name in found_devices, (
                f"Expected IIO device '{device_name}' not found. "
                f"Available devices: {found_devices}"
            )
            device = [d for d in ctx.devices if d.name == device_name][0]
            num_channels = len(device.channels)
            print(f"      ✓ Found IIO device: {device_name} ({num_channels} channels)")

    @pytest.mark.lg_feature(["adrv9009", "zcu102"])
    def test_zcu102_rev10_adrv9009(self, kernel_path, dtb_output_dir, post_power_off):
        """Test reference configuration matching zynqmp-zcu102-rev10-adrv9009.dts"""
        strategy = post_power_off

        # Manual configuration derived from adi-adrv9009.dtsi
        # and adi-adrv9009.dtsi in linux/arch/arm64/boot/dts/xilinx/

        # Helper to create channel config
        def mk_clk(channel, divider):
            return {"channel": channel, "divider": divider}

        config = {
            "clock": {
                "vcxo": 122880000,
                "pll1": {
                    "refa_enable": True,
                    "r_div": 1,
                    "feedback_div": 4,
                    "charge_pump_nA": 5000,
                    "nDivider": 4,
                    "refA_Divider": 1,
                    "vcxo_Frequency_Hz": 122880000,
                },
                "pll2": {
                    "vco_div_m1": 3,
                    "n2_div": 10,
                    "r1_div": 1,
                    "rfDivider": 3,  # Same as vco_div_m1
                    "n2Divider": 10,
                    "r1Divider": 1,
                },
                "sysref": {
                    "k_div": 512,
                    "sysrefSource": "SYSREF_SRC_INTERNAL",
                    "sysrefPatternMode": "SYSREF_PATTERN_CONTINUOUS",
                    "sysrefDivide": 512,
                    "sysrefNshotMode": "SYSREF_NSHOT_4_PULSES",
                    "sysrefPinEdgeMode": "SYSREF_LEVEL_HIGH",
                },
                "output_clocks": {
                    # Keys must match what adrv9009_fmc.map_clocks_to_board_layout expects
                    # OR we can manually map them.
                    # Based on existing test, we can use arbitrary keys if we map them manually
                    # but adrv9009_fmc.map_clocks_to_board_layout expects us to pass `cfg`.
                    # Let's use the keys the class expects to be present in the logic
                    # actually map_clocks_to_board_layout just iterates keys.
                    # BUT map_clocks_to_board_layout separates them into a 'map'.
                    # We will align with the output names expected by the template loop.
                    "DEV_CLK": mk_clk(13, 5),
                    "FMC_CLK": mk_clk(1, 5),
                    "DEV_SYSREF": mk_clk(12, 5),
                    "FMC_SYSREF": mk_clk(3, 5),
                },
            },
            "jesd204": {
                "framer_a": {  # RX
                    "bankId": 1,
                    "deviceId": 0,
                    "lane0Id": 0,
                    "M": 4,
                    "K": 32,
                    "F": 4,
                    "Np": 16,
                    "scramble": 1,
                    "externalSysref": 1,
                    "lanes_enabled": "0x03",
                    "serializerLanesEnabled": "0x03",
                    "serializerLaneCrossbar": "0xE4",
                    "lmfcOffset": 31,
                    "newSysrefOnRelink": 0,
                    "syncbInSelect": 0,
                    "overSample": 0,
                    "syncbInLvdsMode": 1,
                    "syncbInLvdsPnInvert": 0,
                    "enableManualLaneXbar": 0,
                },
                "deframer_a": {  # TX
                    "bankId": 0,
                    "deviceId": 0,
                    "lane0Id": 0,
                    "M": 4,
                    "K": 32,
                    "Np": 16,
                    "scramble": 1,
                    "externalSysref": 1,
                    "lanes_enabled": "0x0F",
                    "deserializerLanesEnabled": "0x0F",
                    "deserializerLaneCrossbar": "0xE4",
                    "lmfcOffset": 17,
                    "newSysrefOnRelink": 0,
                    "syncbOutSelect": 0,
                    "syncbOutLvdsMode": 1,
                    "syncbOutLvdsPnInvert": 0,
                    "syncbOutCmosSlewRate": 0,
                    "syncbOutCmosDriveLevel": 0,
                    "enableManualLaneXbar": 0,
                },
                "framer_b": {  # ORX
                    "bankId": 0,
                    "deviceId": 0,
                    "lane0Id": 0,
                    "M": 2,
                    "K": 32,
                    "F": 2,
                    "Np": 16,
                    "scramble": 1,
                    "externalSysref": 1,
                    "lanes_enabled": "0x0C",
                    "serializerLanesEnabled": "0x0C",
                    "serializerLaneCrossbar": "0xE4",
                    "lmfcOffset": 31,
                    "newSysrefOnRelink": 0,
                    "syncbInSelect": 1,
                    "overSample": 0,
                    "syncbInLvdsMode": 1,
                    "syncbInLvdsPnInvert": 0,
                    "enableManualLaneXbar": 0,
                },
                # SERDES settings matching .dtsi
                "serAmplitude": 15,
                "serPreEmphasis": 1,
                "serInvertLanePolarity": 0,
                "desInvertLanePolarity": 0,
                "desEqSetting": 1,
                "sysrefLvdsMode": 1,
                "sysrefLvdsPnInvert": 0,
            },
            # Profiles
            "rx_profile": {
                "fir_gain_db": -6,
                "fir_decimation": 2,
                "dec5_decimation": 4,
                "rhb1_decimation": 1,
                "output_rate_khz": 245760,
                "rf_bandwidth_hz": 200000000,
                "ddc_mode": 0,
                # Additional fields for template
                "rxChannels": 3,
                "filter": {
                    "@gain_dB": -6,
                    "@numFirCoefs": 48,
                    "coefs": "(-2) (23) (46) (-17) (-104) (10) (208) (23) (-370) (-97) (607) (240) (-942) (-489) (1407) (910) (-2065) (-1637) (3058) (2995) (-4912) (-6526) (9941) (30489) (30489) (9941) (-6526) (-4912) (2995) (3058) (-1637) (-2065) (910) (1407) (-489) (-942) (240) (607) (-97) (-370) (23) (208) (10) (-104) (-17) (46) (23) (-2)",
                },
                "rxFirDecimation": 2,
                "rxDec5Decimation": 4,
                "rhb1Decimation": 1,
                "rxOutputRate_kHz": 245760,
                "rfBandwidth_Hz": 200000000,
                "rxBbf3dBCorner_kHz": 200000,
                "rxAdcProfile": {
                    "coefs": "182 142 173 90 1280 982 1335 96 1369 48 1012 18 48 48 37 208 0 0 0 0 52 0 7 6 42 0 7 6 42 0 25 27 0 0 25 27 0 0 165 44 31 905"
                },
                "rxDdcMode": 0,
                "rxNcoShifterCfg": {
                    "bandAInputBandWidth_kHz": 0,
                    "bandAInputCenterFreq_kHz": 0,
                    "bandANco1Freq_kHz": 0,
                    "bandANco2Freq_kHz": 0,
                    "bandBInputBandWidth_kHz": 0,
                    "bandBInputCenterFreq_kHz": 0,
                    "bandBNco1Freq_kHz": 0,
                    "bandBNco2Freq_kHz": 0,
                },
            },
            "tx_profile": {
                "fir_gain_db": 6,
                "fir_interpolation": 1,
                "thb1_interpolation": 2,
                "thb2_interpolation": 2,
                "thb3_interpolation": 2,
                "input_rate_khz": 245760,
                "rf_bandwidth_hz": 225000000,
                "txChannels": 3,
                "filter": {
                    "@gain_dB": 6,
                    "@numFirCoefs": 40,
                    "coefs": "(-14) (5) (-9) (6) (-4) (19) (-29) (27) (-30) (46) (-63) (77) (-103) (150) (-218) (337) (-599) (1266) (-2718) (19537) (-2718) (1266) (-599) (337) (-218) (150) (-103) (77) (-63) (46) (-30) (27) (-29) (19) (-4) (6) (-9) (5) (-14) (0)",
                },
                "dacDiv": 1,
                "txFirInterpolation": 1,
                "thb1Interpolation": 2,
                "thb2Interpolation": 2,
                "thb3Interpolation": 2,
                "txInt5Interpolation": 1,
                "txInputRate_kHz": 245760,
                "primarySigBandwidth_Hz": 100000000,
                "rfBandwidth_Hz": 225000000,
                "txDac3dBCorner_kHz": 225000,
                "txBbf3dBCorner_kHz": 113000,
                "lpbkAdcProfile": {
                    "coefs": "206 132 168 90 1280 641 1307 53 1359 28 1039 30 48 48 37 210 0 0 0 0 53 0 7 6 42 0 7 6 42 0 25 27 0 0 25 27 0 0 165 44 31 905"
                },
            },
            "orx_profile": {
                "fir_gain_db": 6,
                "fir_decimation": 1,
                "output_rate_khz": 245760,
                "rf_bandwidth_hz": 200000000,
                "obsRxChannelsEnable": 1,
                "filter": {
                    "@gain_dB": 6,
                    "@numFirCoefs": 24,
                    "coefs": "(-10) (7) (-10) (-12) (6) (-12) (16) (-16) (1) (63) (-431) (17235) (-431) (63) (1) (-16) (16) (-12) (6) (-12) (-10) (7) (-10) (0)",
                },
                "rxFirDecimation": 1,
                "rxDec5Decimation": 4,
                "rhb1Decimation": 2,
                "orxOutputRate_kHz": 245760,
                "rfBandwidth_Hz": 200000000,
                "rxBbf3dBCorner_kHz": 225000,
                "orxLowPassAdcProfile": {
                    "coefs": "185 141 172 90 1280 942 1332 90 1368 46 1016 19 48 48 37 208 0 0 0 0 52 0 7 6 42 0 7 6 42 0 25 27 0 0 25 27 0 0 165 44 31 905"
                },
                "orxBandPassAdcProfile": {
                    "coefs": "0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0"
                },
                "orxDdcMode": 0,
            },
            "clocks": {
                "deviceClock_kHz": 245760,
                "clkPllVcoFreq_kHz": 9830400,
                "clkPllHsDiv": 1,
            },
            "lpbk": {
                "lpbkAdcProfile": {
                    "coefs": "206 132 168 90 1280 641 1307 53 1359 28 1039 30 48 48 37 210 0 0 0 0 53 0 7 6 42 0 7 6 42 0 25 27 0 0 25 27 0 0 165 44 31 905"
                }
            },
            # FPGA Config
            "fpga_rx": {"sys_clk_select": "XCVR_CPLL", "out_clk_select": "XCVR_REFCLK"},
            "fpga_tx": {"sys_clk_select": "XCVR_QPLL", "out_clk_select": "XCVR_REFCLK"},
            "fpga_orx": {
                "sys_clk_select": "XCVR_CPLL",
                "out_clk_select": "XCVR_REFCLK",
            },
        }

        # Step 2: Generate DTS
        print("[1/4] Generating DTS from manual configuration...")
        board = adrv9009_fmc_no_plugin(platform="zcu102", kernel_path=kernel_path)

        dts_filename = dtb_output_dir / "generated_adrv9009.dts"
        board.output_filename = str(dts_filename)

        # We manually constructed the config to match what map_clocks_to_board_layout expects
        # (which is just passing through values mostly) OR we can use the map directly.
        # But board.gen_dt calls board.map_clocks_to_board_layout(config) internally?
        # No, in test_hw_deployment it calls it explicitly.
        # Let's call it explicitly to be safe and match the flow.

        clock, rx, tx, orx, fpga = board.map_clocks_to_board_layout(config)

        # Merge the manually created profile/clocks/lpbk dictionaries into the args for gen_dt
        # because map_clocks_to_board_layout only handles a subset.
        # Wait, the template expects flattened dictionaries or specific structure.
        # The template accesses `rx['filter']`, `jesd204['framerA']`, etc.
        # But gen_dt takes clock, rx, tx, orx, fpga arguments.
        # So we need to ensure those arguments contain ALL the data the template needs.
        # map_clocks_to_board_layout extracts some subsets but keys like 'filter' or 'jesd204' settings
        # need to be in rx/tx/orx dictionaries passed to gen_dt.

        # Re-construct complete dictionaries for gen_dt
        def merge(d1, d2):
            return {**d1, **d2}

        # config['jesd204'] contains framer_a, etc.
        # map_clocks sets rx['framer'] = cfg['jesd204']['framer_a']

        # We need to ensure the template keys are present.
        # The template uses camelCase keys e.g. framerA, deframerA
        # My config above uses what passed existing tests? No, existing tests use pyadi-jif which might produce snake_case?
        # Let's check the template again.
        # Template: {{ jesd204['framerA']['bankId'] }}
        # My config above: framer_a
        # So I need to map snake_case to camelCase for the template or change my config.
        # Changing config above to match template would be cleaner.

        jesd_config_fixed = {
            "framerA": config["jesd204"]["framer_a"],
            "deframerA": config["jesd204"]["deframer_a"],
            "framerB": config["jesd204"]["framer_b"],
            "serAmplitude": 15,
            "serPreEmphasis": 1,
            "serInvertLanePolarity": 0,
            "desInvertLanePolarity": 0,
            "desEqSetting": 1,
            "sysrefLvdsMode": 1,
            "sysrefLvdsPnInvert": 0,
        }

        # Template expects 'jesd204' object in context. gen_dt generally puts **kwargs into context.
        # adrv9009_fmc.gen_dt doesn't seem to take jesd204 argument.
        # Let's check adrv9009_fmc.gen_dt signature or parent layout.gen_dt.
        # It likely accepts **kwargs.

        generated_dts = board.gen_dt(
            clock=clock,
            rx=merge(rx, config["rx_profile"]),  # Merge profile and mapped framer
            tx=merge(tx, config["tx_profile"]),
            orx=merge(orx, config["orx_profile"]),
            fpga=fpga,
            jesd204=jesd_config_fixed,  # Pass jesd204 explicitly
            clocks=config["clocks"],
            lpbk=config["lpbk"],
            pll1=config["clock"]["pll1"],  # Template accesses pll1 directly too
            pll2=config["clock"]["pll2"],
            sysref=config["clock"]["sysref"],
            out=board._map_clocks_to_board_layout_helper(config)
            if hasattr(board, "_map_clocks_to_board_layout_helper")
            else clock["map"],  # Wait map_clocks... returns ccfg which has 'map'.
            # The template iterates `clock['map'].items()`
            # It also uses `out['outBufferCtrl'][13]` etc in adi-adrv9009.dtsi include?
            # Ah, the template includes "adi-adrv9009.dtsi" which uses `out` variable?
            # No, the template has the content of adi-adrv9009.dtsi INLINED?
            # OR logic.
            # Looking at adrv9009_fmc_zcu102.tmpl (Step 25):
            # It includes "adi-adrv9009.dtsi" on line 303 (commented out?) No wait.
            # Step 25 output shows content of adrv9009_fmc_zcu102.tmpl.
            # It does NOT include adi-adrv9009.dtsi. It has the nodes directly?
            # Wait, line 303: `#include "adi-adrv9009.dtsi"` is in the reference DTS, not the template.
            # The template in Step 25 does NOT seem to look like reference DTS structure regarding includes.
            # It generates the full nodes?
            # Scanning Step 25 template again...
            # It has `&fmc_spi {` ... `clk0_ad9528: ad9528-1@0 {` ...
            # `adi,vcxo-freq = <{{ clock['vcxo'] }}>;`
            # So the template needs `clock` dict with `vcxo`, `pll1`, `pll2`, `sysref`, `map`.
            # And `clock['map']` for the outputs loop.
            # It does NOT use `out['outBufferCtrl']`. That was in `adi-adrv9009.dtsi`.
            # The template seems to implement the logic of `adi-adrv9009.dtsi` but with variables.
        )

        # Correction: The generated DTS is fully expanded, while reference uses includes.
        # Comparison strategy:
        # 1. Compile generated DTS to DTB.
        # 2. Compile reference DTS to DTB.
        # 3. Use `fdtdump` or similar to flatten both and compare textually?
        # Or compare using logic in the test.

        generated_dts = Path(generated_dts)
        assert generated_dts.exists()
        print(f"      ✓ Generated DTS: {generated_dts}")

        # Step 3: Verify against reference
        print("[2/4] Verifying against reference...")

        # 3a. Compile Generated
        gen_dtb = dtb_output_dir / "generated.dtb"
        compile_dts_to_dtb(generated_dts, gen_dtb, kernel_path, arch="arm64")

        # 3b. Compile Reference
        ref_dts_name = "zynqmp-zcu102-rev10-adrv9009.dts"
        ref_dts_path = Path(kernel_path) / "arch/arm64/boot/dts/xilinx" / ref_dts_name
        if not ref_dts_path.exists():
            pytest.skip(f"Reference DTS {ref_dts_name} not found in kernel")

        ref_dtb = dtb_output_dir / "reference.dtb"

        # To compile reference, we can use the same helper but we need to verify if it supports
        # compiling a file already in the tree (it does, it copies it).
        # But since ref is already there, we can just point to it.
        # The helper `compile_dts_to_dtb` copies the source to the kernel tree.
        # Since ref is already there, it's fine (overwrite or skip copy).
        # Actually it copies to `kernel_dts_path`. If `dts_path` argument IS `kernel_dts_path`, shutil.copy2 might error or be no-op.

        if (
            ref_dts_path.resolve()
            == (
                Path(kernel_path) / "arch/arm64/boot/dts/xilinx" / ref_dts_name
            ).resolve()
        ):
            # It is the same file.
            pass

        # We'll trust compile_dts_to_dtb handles it or just manually trigger make
        env = os.environ.copy()
        env["ARCH"] = "arm64"
        # Setup cross compile
        toolchain_bin = download_and_cache_toolchain(arch="arm64")
        env["CROSS_COMPILE"] = f"{toolchain_bin}/{TOOLCHAIN_ARCH_ARM64}-"

        make_target = f"xilinx/{ref_dts_name.replace('.dts', '.dtb')}"
        make_cmd = ["make", make_target]
        print(f"      Compiling Reference: {' '.join(make_cmd)}")
        subprocess.run(
            make_cmd, cwd=kernel_path, env=env, check=True, capture_output=True
        )

        # Move result to output dir
        built_ref_dtb = Path(kernel_path) / "arch/arm64/boot/dts" / make_target
        shutil.copy2(built_ref_dtb, ref_dtb)

        assert ref_dtb.exists()

        # 3c. Compare
        # Simple size check first
        print(f"      Generated DTB Size: {gen_dtb.stat().st_size}")
        print(f"      Reference DTB Size: {ref_dtb.stat().st_size}")

        # Convert both to DTS using dtc to normalize specifics (offsets etc)
        # dtc -I dtb -O dts -o out.dts in.dtb
        # Assumes dtc is in path or we use the one in kernel scripts?
        # Kernel usually has dtc. `scripts/dtc/dtc`
        dtc_path = Path(kernel_path) / "scripts/dtc/dtc"
        if not dtc_path.exists():
            # Try system dtc
            dtc_path = "dtc"

        def dtb_to_dts(dtb, output):
            cmd = [
                str(dtc_path),
                "-I",
                "dtb",
                "-O",
                "dts",
                "-o",
                str(output),
                "-s",
                str(dtb),
            ]
            subprocess.run(cmd, check=True, capture_output=True)

        gen_dts_flat = dtb_output_dir / "generated_flat.dts"
        ref_dts_flat = dtb_output_dir / "reference_flat.dts"

        try:
            dtb_to_dts(gen_dtb, gen_dts_flat)
            dtb_to_dts(ref_dtb, ref_dts_flat)

            # Read and Compare text
            with open(gen_dts_flat) as f:
                gen_text = f.readlines()
            with open(ref_dts_flat) as f:
                ref_text = f.readlines()

            # Simple line count check or more complex diff?
            # Due to different include expansions or ordering, exact match is unlikely without sorting.
            # However, for this task, let's verify essential ADI nodes exist in both.

            print("      Comparing flattened DTS content...")
            # We could use `difflib` but the output might be huge.
            # Let's check for critical path/value existence.

            # Ideally we want exact match. If we used exact values, it should be very close.
            # We can assert that the diff is small or empty?
            for line in gen_text:
                if line not in ref_text:
                    raise Exception(f"Line not found in reference: {line}")

        except Exception as e:
            print(f"      Warning: DTC comparison failed: {e}")
            raise e
            # Fallback to size check similarity?
            # assert abs(gen_dtb.stat().st_size - ref_dtb.stat().st_size) < 1000 # 1KB tolerance

        # Step 4: Deploy (Run)
        print("[3/4] Deploying to board...")
        strategy.transition("powered_off")
        kuiper = strategy.target.get_driver("KuiperDLDriver")

        # Rename for deployment
        deploy_dtb = dtb_output_dir / "system.dtb"
        shutil.copy2(gen_dtb, deploy_dtb)

        kuiper.add_files_to_target(str(deploy_dtb))
        strategy.transition("shell")

        # Step 5: Verify IIO devices
        print("[4/4] Verifying IIO context...")
        shell = strategy.target.get_driver("ADIShellDriver")
        ip = str(shell.get_ip_addresses()[0].ip).split("/")[0]
        ctx = iio.Context(f"ip:{ip}")

        assert "adrv9009-phy" in [d.name for d in ctx.devices]
        assert "axi-adrv9009-rx-hpc" in [d.name for d in ctx.devices]
        assert "axi-adrv9009-tx-hpc" in [d.name for d in ctx.devices]

        print("      ✓ Referenced configuration verification passed")
