"""AD9081+ZCU102 Multi-Rate Hardware Test Suite

This module tests AD9081 FMC board on ZCU102 at 10 different sample rates
from 100-300 MSPS, maintaining JESD204 configuration of L=4, M=8, Np=16
with max lane rate of 10 Gbps.

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
- AD9081-FMCA-EBZ hardware on ZCU102
"""

import pytest
import os
import shutil
import subprocess
import urllib.request
import tarfile
from pathlib import Path
from adidt.boards.ad9081_fmc import ad9081_fmc
import iio
import adijif
import adi


# Sample rates to test (in MSPS)
# Range: 100-300 MSPS, staying under 10 Gbps lane rate limit
SAMPLE_RATES = [100, 125, 150, 175, 200, 225, 245, 260, 280, 300]
# SAMPLE_RATES = [100, 300]


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


def generate_ad9081_config(sample_rate_msps: int, platform: str = "zcu102") -> dict:
    """Generate AD9081 configuration for given sample rate.

    Uses pyadi-jif to generate a complete configuration dict with JESD204
    parameters L=4, M=8, Np=16 for both ADC and DAC paths.

    Args:
        sample_rate_msps: Sample rate in MSPS (100-300)
        platform: Platform name ('zcu102', 'zc706', etc.). Default: 'zcu102'

    Returns:
        Complete configuration dict for ad9081_fmc board
    """
    vcxo = 122_880_000  # 122.88 MHz reference

    # Create system with gekko solver (fallback when CPLEX not available)
    sys = adijif.system("ad9081", "hmc7044", "xilinx", vcxo, solver="gekko")
    sys.fpga.setup_by_dev_kit_name(platform)  # Pass platform parameter

    # Clocking constraints
    sys.fpga.ref_clock_constraint = "Unconstrained"
    sys.fpga.sys_clk_select = "XCVR_QPLL"
    sys.fpga.out_clk_select = "XCVR_REFCLK_DIV2"
    sys.converter.clocking_option = "integrated_pll"

    # Sample Rates
    sample_clock = sample_rate_msps * 1_000_000
    sys.converter.adc.sample_clock = sample_clock
    sys.converter.dac.sample_clock = sample_clock

    # Datapath Configuration
    # Mode 10.0 requires minimal decimation and clock rates > 1.45 GHz
    # 100 MSPS * 16 = 1.6 GHz > 1.45 GHz.
    # Using 16x Decimation (4x4)
    # Mode 10.0 M=8 supports 4 Complex Channels (4*2=8 converters)
    # Enable only 4 FDDC channels
    sys.converter.adc.datapath.fddc_enabled = [True] * 4 + [False] * 4
    sys.converter.adc.datapath.fddc_decimations = [4] * 8
    sys.converter.adc.datapath.cddc_decimations = [4] * 4

    # Mode 9 for DAC requires clock > 2.9 GHz
    # 100 MSPS * 32 = 3.2 GHz > 2.9 GHz.
    # Using 32x Interpolation (4x8)
    sys.converter.dac.datapath.cduc_interpolation = 4
    sys.converter.dac.datapath.fduc_interpolation = 8
    sys.converter.dac.datapath.fduc_enabled = [True] * 4 + [False] * 4
    # Original DAC sources were: [[0, 1], [2, 3], [4, 5], [6, 7]]
    # pyadi-jif should handle default routing for M=8, but let's verify if needed.

    # JESD Constraints for L=4, M=8, Np=16
    # Confirmed from adijif resources:
    # ADC Mode 10.0: L=4, M=8, F=4, Np=16
    # DAC Mode 9: L=4, M=8, F=4, Np=16
    sys.converter.adc.set_quick_configuration_mode("10.0", "jesd204b")
    sys.converter.dac.set_quick_configuration_mode("9", "jesd204b")

    # Fix for any potential solver ambiguity
    sys.converter.adc.K = 32
    sys.converter.dac.K = 32

    # Platform-specific JESD configuration
    if platform == "zc706":
        # ZC706 uses GTX transceivers with max 10 Gbps lane rate
        # Force S=1 for ZC706 per user requirements
        sys.converter.adc.jesd_S = 1
        sys.converter.dac.jesd_S = 1
        # Max lane rate constraint for GTX
        sys.fpga.max_serdes_rate = 10e9

    # Solve for configuration
    cfg = sys.solve()

    # Map generated keys to expected keys for adidt
    # adidt expects generic names (adc_fpga_ref_clk) but pyadi-jif generates
    # board specific names (zcu102_adc_ref_clk, zc706_adc_ref_clk, etc.)
    clks = cfg["clock"]["output_clocks"]

    platform_prefix = platform.lower()
    mapping = {
        f"{platform_prefix}_adc_ref_clk": "adc_fpga_ref_clk",
        f"{platform_prefix}_adc_device_clk": "adc_fpga_link_out_clk",
        f"{platform_prefix}_dac_ref_clk": "dac_fpga_ref_clk",
        f"{platform_prefix}_dac_device_clk": "dac_fpga_link_out_clk",
    }

    for old_key, new_key in mapping.items():
        if old_key in clks:
            clks[new_key] = clks.pop(old_key)

    # Helper to clean up modes (10.0 -> 10)
    for part in ["jesd_adc", "jesd_dac"]:
        if part in cfg and "jesd_mode" in cfg[part]:
            try:
                cfg[part]["jesd_mode"] = int(float(cfg[part]["jesd_mode"]))
            except (ValueError, TypeError):
                pass

    return cfg


def compile_dts_to_dtb(
    dts_path: Path,
    dtb_path: Path,
    kernel_path: str,
    arch: str = "arm64",
    cross_compile: str = None,
) -> None:
    """Compile DTS to DTB using kernel build system with cross-compiler.

    Places the DTS file in the kernel tree and uses the kernel's make system
    to compile it properly. This ensures correct include resolution and creates
    a bootable DTB for hardware deployment.

    This follows ADI documentation:
    - ARM64 (ZynqMP): https://analogdevicesinc.github.io/documentation/linux/kernel/zynqmp.html
    - ARM (Zynq): https://analogdevicesinc.github.io/documentation/linux/kernel/zynq.html

    Args:
        dts_path: Path to generated DTS source file
        dtb_path: Desired path for output DTB file
        kernel_path: Path to Linux kernel source tree
        arch: Target architecture ('arm' or 'arm64'). Default: 'arm64'
        cross_compile: Cross-compiler prefix (e.g., 'aarch64-none-elf-' or 'arm-none-eabi-').
                      If None, automatically downloads appropriate ARM GNU toolchain.

    Raises:
        RuntimeError: If compilation fails at any stage
        ValueError: If arch is not 'arm' or 'arm64'
    """
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
    env["ARCH"] = arch  # Use parameter instead of hardcoded 'arm64'
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

    # Step 2: Ensure kernel is configured (one-time setup)
    # This creates .config file needed for device tree compilation
    config_file = Path(kernel_path) / ".config"
    if not config_file.exists():
        print("      Configuring kernel (first-time setup)...")

        # Select defconfig based on architecture
        if arch == "arm64":
            defconfig = "adi_zynqmp_defconfig"
        else:  # arch == "arm"
            defconfig = "zynq_xcomm_adv7511_defconfig"

        config_cmd = ["make", defconfig]
        config_result = subprocess.run(
            config_cmd,
            cwd=kernel_path,
            capture_output=True,
            text=True,
            env=env,  # Use cross-compiler environment
        )
        if config_result.returncode != 0:
            raise RuntimeError(f"Kernel configuration failed: {config_result.stderr}")

    # Step 3: Compile DTB using kernel make system
    # Target format: xilinx/filename.dtb (relative to arch/arm64/boot/dts/)
    if arch == "arm64":
        make_target = f"xilinx/{dts_filename.replace('.dts', '.dtb')}"
    else:
        make_target = f"{dts_filename.replace('.dts', '.dtb')}"
    make_cmd = ["make", make_target]

    make_result = subprocess.run(
        make_cmd,
        cwd=kernel_path,
        capture_output=True,
        text=True,
        env=env,  # Use cross-compiler environment
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

    # Optional: Clean up DTS/DTB from kernel tree to avoid clutter
    # Commented out to preserve for debugging
    # kernel_dts_path.unlink()
    # kernel_dtb_path.unlink()


# Pytest fixtures


@pytest.fixture(scope="module")
def kernel_path():
    """Get kernel path from environment or use default.

    Priority:
    1. LINUX_KERNEL_PATH environment variable
    2. ./linux directory (default)

    Skips test if kernel source not found.
    """
    path = os.environ.get("LINUX_KERNEL_PATH", "./linux")
    if not os.path.exists(path):
        pytest.skip(f"Linux kernel source not found at {path}")
    return path


@pytest.fixture(scope="module")
def dtb_output_dir(tmp_path_factory):
    """Create temporary directory for DTB files.

    Creates a module-scoped temporary directory that persists
    across all parametrized tests. Automatically cleaned up
    after test module completes.
    """
    return tmp_path_factory.mktemp("ad9081_dtbs")


@pytest.fixture(scope="module")
def post_power_off(strategy):
    """Ensure board powers off after all tests.

    Yields the strategy fixture for tests to use, then
    transitions to soft_off state after all tests complete.
    This ensures clean board state for subsequent test runs.
    """
    yield strategy
    strategy.transition("soft_off")


# Test class


class TestAD9081MultiRateHardware:
    """Hardware test suite for AD9081 at multiple sample rates.

    Tests AD9081 FMC board on ZCU102 across 10 sample rates from 100-300 MSPS.
    Each test performs full hardware deployment and verification:
    - DTS generation
    - DTB compilation
    - Board power cycling
    - DTB deployment
    - System boot
    - IIO device enumeration

    All configurations use JESD204 parameters: L=4, M=8, Np=16
    Lane rates verified to stay under 10 Gbps limit.
    """

    # @pytest.mark.timeout(60*2)
    @pytest.mark.parametrize("sample_rate_msps", SAMPLE_RATES)
    @pytest.mark.lg_feature(["ad9081", "zcu102"])
    def test_sample_rate_deployment(
        self, sample_rate_msps, kernel_path, dtb_output_dir, post_power_off
    ):
        """Test AD9081 at specific sample rate with full hardware deployment.

        Generates device tree for specified sample rate, deploys to hardware,
        boots system, and verifies both ADC and DAC IIO devices enumerate.

        Args:
            sample_rate_msps: Sample rate in MSPS (from SAMPLE_RATES list)
            kernel_path: Path to Linux kernel source (fixture)
            dtb_output_dir: Temporary directory for DTB files (fixture)
            post_power_off: Strategy fixture with cleanup (fixture)

        Raises:
            AssertionError: If any verification step fails
            RuntimeError: If DTS/DTB generation fails
        """
        strategy = post_power_off

        # Calculate and display lane rate for verification
        lane_rate_gbps = sample_rate_msps * 32 / 1000
        print(f"\n{'=' * 70}")
        print(f"Testing {sample_rate_msps} MSPS (Lane Rate: {lane_rate_gbps:.2f} Gbps)")
        print(f"{'=' * 70}")

        # Step 1: Generate configuration
        print("[1/9] Generating configuration...")
        config = generate_ad9081_config(sample_rate_msps, platform="zcu102")

        # Step 2: Generate DTS
        print("[2/9] Generating DTS file...")
        board = ad9081_fmc(platform="zcu102", kernel_path=kernel_path)
        config = board.validate_and_default_fpga_config(config)

        dts_filename = dtb_output_dir / f"ad9081_{sample_rate_msps}msps.dts"
        board.output_filename = str(dts_filename)

        clock, adc, dac, fpga = board.map_clocks_to_board_layout(config)
        generated_dts = board.gen_dt(
            clock=clock,
            adc=adc,
            dac=dac,
            fpga=fpga,
            config_source=f"generated_{sample_rate_msps}msps",
        )

        assert os.path.exists(generated_dts), f"DTS file not generated: {generated_dts}"
        print(f"      ✓ Generated DTS: {generated_dts}")
        shutil.copy2(generated_dts, "/tmp/")  # Copy for debugging if needed

        # Step 3: Compile DTS to DTB using kernel build system
        print("[3/9] Compiling DTS to DTB...")
        dtb_filename = dtb_output_dir / f"ad9081_{sample_rate_msps}msps.dtb"

        # Extract architecture from board config
        arch = board.platform_config["arch"]  # "arm64" for ZCU102

        compile_dts_to_dtb(
            dts_path=Path(generated_dts),
            dtb_path=dtb_filename,
            kernel_path=kernel_path,
            arch=arch,  # Pass architecture parameter
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
        # Rename to system.dtb for KuiperDLDriver
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
        # Handle shell.run return (stdout_lines, returncode)
        if isinstance(dmesg_res, tuple):
            dmesg_output = dmesg_res[0]
        else:
            dmesg_output = dmesg_res

        if isinstance(dmesg_output, list):
            dmesg_output = "\n".join(dmesg_output)

        dmesg_log_path = dtb_output_dir / f"dmesg_{sample_rate_msps}msps.log"
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

        dmesg_error_log_path = (
            dtb_output_dir / f"dmesg_errors_{sample_rate_msps}msps.log"
        )
        with open(dmesg_error_log_path, "w") as f:
            f.write(dmesg_error_output)
        print(f"      ✓ Kernel error/warn log saved: {dmesg_error_log_path}")

        # Step 9: Verify devices
        print("[9/9] Verifying IIO devices...")
        expected_devices = ["axi-ad9081-rx-hpc", "axi-ad9081-tx-hpc"]
        found_devices = [d.name for d in ctx.devices]

        for device_name in expected_devices:
            assert device_name in found_devices, (
                f"Expected IIO device '{device_name}' not found at {sample_rate_msps} MSPS. "
                f"Available devices: {found_devices}"
            )
            # Get channel count for verification
            device = [d for d in ctx.devices if d.name == device_name][0]
            num_channels = len(device.channels)
            print(f"      ✓ Found IIO device: {device_name} ({num_channels} channels)")

        dev = adi.ad9081(uri=f"ip:{ip_address}")
        sample_rate = dev.rx_sample_rate
        print(f"      ✓ Sample rate: {sample_rate}")
        assert sample_rate == sample_rate_msps * 1_000_000, (
            f"Expected sample rate {sample_rate_msps * 1_000_000} Hz, "
            f"got {sample_rate} Hz"
        )

        print(f"\n{'=' * 70}")
        print(f"✓✓✓ Test PASSED for {sample_rate_msps} MSPS ✓✓✓")
        print(f"{'=' * 70}\n")


# Test class for ZC706 platform


class TestAD9081ZC706Hardware:
    """Hardware test suite for AD9081 on ZC706 platform.

    Tests AD9081 FMC board on ZC706 (Zynq-7000) at a single sample rate
    to verify ZC706 support. Uses ARM 32-bit compilation and platform-specific
    JESD configuration (M=8, L=4, S=1, NP=16).

    Key differences from ZCU102:
    - Architecture: ARM (32-bit) vs ARM64
    - DTB filename: devicetree.dtb vs system.dtb
    - Transceiver: GTX vs GTH
    - Defconfig: zynq_xcomm_adv7511_defconfig vs adi_zynqmp_defconfig
    """

    # @pytest.mark.timeout(60*5)  # 5 minute timeout for full boot cycle
    @pytest.mark.skip(reason="Not fully verified. SDMux not supported of ZC706.")
    @pytest.mark.lg_feature(["ad9081", "zc706"])
    def test_zc706_deployment(self, kernel_path, tmp_path, strategy):
        """Test AD9081 on ZC706 at 100 MSPS with full hardware deployment.

        This test verifies ZC706 platform support by:
        - Using pre-computed configuration for 100 MSPS
        - Compiling DTB with ARM 32-bit toolchain
        - Deploying devicetree.dtb (not system.dtb)
        - Verifying IIO device enumeration

        Args:
            kernel_path: Path to Linux kernel source (fixture)
            tmp_path: Temporary directory for DTB files (fixture)
            strategy: Labgrid strategy fixture for hardware control

        Raises:
            AssertionError: If any verification step fails
            RuntimeError: If DTS/DTB generation fails
        """
        sample_rate_msps = 100  # Test at 100 MSPS
        platform = "zc706"

        print(f"\n{'=' * 70}")
        print(f"Testing AD9081 on ZC706 @ {sample_rate_msps} MSPS")
        print(f"{'=' * 70}")

        # Step 1: Use static configuration for ZC706 @ 100 MSPS
        # This avoids needing CPLEX/gekko solver
        print("[1/9] Loading static configuration for ZC706...")
        config = {
            "converter": {"type": "ad9081"},
            "clock": {
                "vcxo": 122880000,
                "vco": 2949120000,
                "output_clocks": {
                    "AD9081_ref_clk": {"divider": 12},
                    "adc_sysref": {"divider": 1536},
                    "dac_sysref": {"divider": 1536},
                    "adc_fpga_ref_clk": {"divider": 12},
                    "adc_fpga_link_out_clk": {"divider": 12},
                    "dac_fpga_ref_clk": {"divider": 12},
                    "dac_fpga_link_out_clk": {"divider": 12},
                },
            },
            "fpga_adc": {
                "sys_clk_select": "XCVR_QPLL",
                "out_clk_select": "XCVR_REFCLK_DIV2",
            },
            "fpga_dac": {
                "sys_clk_select": "XCVR_QPLL",
                "out_clk_select": "XCVR_REFCLK_DIV2",
            },
            "jesd_adc": {
                "M": 8,
                "L": 4,
                "S": 1,
                "F": 4,
                "K": 32,
                "Np": 16,
                "CS": 0,
                "HD": 0,
                "jesd_mode": 10,
                "jesd_class": "jesd204b",
                "converter_clock": 1600000000,
                "sample_clock": 100000000,
            },
            "jesd_dac": {
                "M": 8,
                "L": 4,
                "S": 1,
                "F": 4,
                "K": 32,
                "Np": 16,
                "CS": 0,
                "HD": 0,
                "jesd_mode": 9,
                "jesd_class": "jesd204b",
                "converter_clock": 3200000000,
                "sample_clock": 100000000,
            },
            "datapath_adc": {
                "cddc": {
                    "enabled": [True, True, True, True],
                    "decimations": [4, 4, 4, 4],
                    "nco_frequencies": [0, 0, 0, 0],
                },
                "fddc": {
                    "enabled": [True, True, True, True, True, True, True, True],
                    "decimations": [4, 4, 4, 4, 4, 4, 4, 4],
                    "nco_frequencies": [0, 0, 0, 0, 0, 0, 0, 0],
                },
            },
            "datapath_dac": {
                "cduc": {
                    "enabled": [True, True, True, True],
                    "interpolation": 4,
                    "sources": [[0, 1], [2, 3], [4, 5], [6, 7]],
                    "nco_frequencies": [0, 0, 0, 0],
                },
                "fduc": {
                    "enabled": [True, True, True, True, True, True, True, True],
                    "interpolation": 8,
                    "nco_frequencies": [0, 0, 0, 0, 0, 0, 0, 0],
                },
            },
        }
        print("      ✓ Configuration loaded")

        # Step 2: Generate DTS
        print("[2/9] Generating DTS file...")
        board = ad9081_fmc(platform=platform, kernel_path=kernel_path)
        config = board.validate_and_default_fpga_config(config)

        dts_filename = tmp_path / f"ad9081_zc706_{sample_rate_msps}msps.dts"
        board.output_filename = str(dts_filename)

        clock, adc, dac, fpga = board.map_clocks_to_board_layout(config)
        generated_dts = board.gen_dt(
            clock=clock,
            adc=adc,
            dac=dac,
            fpga=fpga,
            config_source=f"zc706_{sample_rate_msps}msps",
        )

        assert os.path.exists(generated_dts), f"DTS file not generated: {generated_dts}"
        print(f"      ✓ Generated DTS: {generated_dts}")

        # Step 3: Compile DTS to DTB using ARM 32-bit toolchain
        print("[3/9] Compiling DTS to DTB (ARM 32-bit)...")
        dtb_filename = tmp_path / f"ad9081_zc706_{sample_rate_msps}msps.dtb"

        # Extract architecture from board config
        arch = board.platform_config["arch"]  # Should be "arm" for ZC706

        compile_dts_to_dtb(
            dts_path=Path(generated_dts),
            dtb_path=dtb_filename,
            kernel_path=kernel_path,
            arch=arch,  # Pass architecture parameter
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

        # Step 5: Deploy DTB as devicetree.dtb (ZC706 requirement)
        print("[5/9] Deploying DTB to board...")
        kuiper = strategy.target.get_driver("KuiperDLDriver")

        # ZC706 requires devicetree.dtb, not system.dtb
        devicetree_filename = tmp_path / "devicetree.dtb"
        shutil.copy2(dtb_filename, devicetree_filename)
        kuiper.add_files_to_target(str(devicetree_filename))
        print("      ✓ DTB deployed as devicetree.dtb")

        # Step 6: Boot to shell
        print("[6/9] Booting board to shell...")
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
        print(f"      ✓ IIO context created: {ip_address}")

        # Step 8: Extract kernel log for debugging
        print("[8/9] Extracting kernel logs...")
        dmesg_res = shell.run("dmesg")
        if isinstance(dmesg_res, tuple):
            dmesg_output = dmesg_res[0]
        else:
            dmesg_output = dmesg_res

        if isinstance(dmesg_output, list):
            dmesg_output = "\n".join(dmesg_output)

        dmesg_log_path = tmp_path / f"dmesg_zc706_{sample_rate_msps}msps.log"
        with open(dmesg_log_path, "w") as f:
            f.write(dmesg_output)
        print(f"      ✓ Kernel logs saved: {dmesg_log_path}")

        # Step 9: Verify devices
        print("[9/9] Verifying IIO devices...")
        expected_devices = ["axi-ad9081-rx-hpc", "axi-ad9081-tx-hpc"]
        found_devices = [d.name for d in ctx.devices]

        for device_name in expected_devices:
            assert device_name in found_devices, (
                f"Expected IIO device '{device_name}' not found on ZC706. "
                f"Available devices: {found_devices}"
            )
            device = [d for d in ctx.devices if d.name == device_name][0]
            num_channels = len(device.channels)
            print(f"      ✓ Found IIO device: {device_name} ({num_channels} channels)")

        print(f"\n{'=' * 70}")
        print(f"✓✓✓ Test PASSED for AD9081 on ZC706 @ {sample_rate_msps} MSPS ✓✓✓")
        print(f"{'=' * 70}\n")

        # Power off after test
        strategy.transition("soft_off")
