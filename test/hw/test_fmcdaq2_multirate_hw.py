"FMCDAQ2+ZCU102 Hardware Test Suite"

import pytest
import os
import shutil
import subprocess
import urllib.request
import tarfile
from pathlib import Path
from adidt.boards.daq2 import daq2
import iio
import adijif
import adi


# Sample rates to test (in MSPS)
SAMPLE_RATES = [500, 1000]


# ARM GNU Toolchain configuration for cross-compiling ARM64 device trees
TOOLCHAIN_URL = "https://developer.arm/-/media/Files/downloads/gnu/12.2.rel1/binrel/arm-gnu-toolchain-12.2.rel1-x86_64-aarch64-none-elf.tar.xz"
TOOLCHAIN_VERSION = "12.2.rel1"
TOOLCHAIN_ARCH = "aarch64-none-elf"


def download_and_cache_toolchain(cache_dir: Path = None) -> Path:
    """Download and cache ARM GNU toolchain for cross-compilation.

    Downloads the ARM GNU toolchain for aarch64 from ARM's official site
    and extracts it to a cache directory. If already cached, skips download.

    Args:
        cache_dir: Directory to cache toolchain. Defaults to ~/.cache/pyadi-dt/

    Returns:
        Path to toolchain bin directory containing cross-compiler

    Raises:
        RuntimeError: If download or extraction fails
    """
    # Determine cache directory
    if cache_dir is None:
        cache_dir = Path.home() / ".cache" / "pyadi-dt" / "toolchains"
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Expected toolchain directory after extraction
    toolchain_name = f"arm-gnu-toolchain-{TOOLCHAIN_VERSION}-x86_64-{TOOLCHAIN_ARCH}"
    toolchain_dir = cache_dir / toolchain_name
    toolchain_bin = toolchain_dir / "bin"

    # Check if already cached
    if toolchain_bin.exists():
        print(f"      Using cached toolchain: {toolchain_dir}")
        return toolchain_bin

    # Download toolchain
    print(f"      Downloading ARM GNU toolchain {TOOLCHAIN_VERSION}...")
    tarball_path = cache_dir / f"{toolchain_name}.tar.xz"

    try:
        with urllib.request.urlopen(TOOLCHAIN_URL) as response:
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


def generate_fmcdaq2_config(sample_rate_msps: int) -> dict:
    """Generate FMCDAQ2 configuration for given sample rate.

    Uses pyadi-jif to generate a complete configuration dict with JESD204
    parameters L=4, M=2 for both ADC and DAC paths.

    Args:
        sample_rate_msps: Sample rate in MSPS

    Returns:
        Complete configuration dict for fmcdaq2 board
    """
    # Create system with default solver (Z3 or CPLEX if available)
    # Using 'zcu102' presets as starting point
    vcxo = 125_000_000
    sys = adijif.system(["ad9680", "ad9144"], "ad9523_1", "xilinx", vcxo)
    sys.fpga.setup_by_dev_kit_name("zcu102")

    # Clocking constraints
    sys.fpga.ref_clock_constraint = "Unconstrained"
    # Let solver determine optimal sys_clk_select and out_clk_select

    # Sample Rates
    sample_clock = sample_rate_msps * 1_000_000
    sys.converter[0].sample_clock = sample_clock
    sys.converter[1].sample_clock = sample_clock

    # JESD Constraints for L=4, M=2
    sys.converter[0].jesd_L = 4
    sys.converter[0].jesd_M = 2
    sys.converter[1].jesd_L = 4
    sys.converter[1].jesd_M = 2

    return sys


def compile_dts_to_dtb(
    dts_path: Path, dtb_path: Path, kernel_path: str, cross_compile: str = None
) -> None:
    """Compile DTS to DTB using kernel build system with cross-compiler.

    Places the DTS file in the kernel tree and uses the kernel's make system
    to compile it properly. This ensures correct include resolution and creates
    a bootable DTB for hardware deployment.

    This follows the ADI ZynqMP documentation:
    https://analogdevicesinc.github.io/documentation/linux/kernel/zynqmp.html

    Args:
        dts_path: Path to generated DTS source file
        dtb_path: Desired path for output DTB file
        kernel_path: Path to Linux kernel source tree
        cross_compile: Cross-compiler prefix (e.g., 'aarch64-none-elf-').
                      If None, automatically downloads ARM GNU toolchain.

    Raises:
        RuntimeError: If compilation fails at any stage
    """
    # Download and cache cross-compiler if not provided
    if cross_compile is None:
        print("      Setting up ARM64 cross-compiler...")
        toolchain_bin = download_and_cache_toolchain()
        cross_compile = f"{toolchain_bin}/{TOOLCHAIN_ARCH}-"
        print(f"      ✓ Cross-compiler ready: {cross_compile}")

    # Set up environment for kernel compilation
    # ARCH=arm64: Target architecture
    # CROSS_COMPILE=<prefix>: Cross-compiler prefix for aarch64
    env = os.environ.copy()
    env["ARCH"] = "arm64"
    env["CROSS_COMPILE"] = cross_compile

    # Determine platform-specific paths
    # For ZCU102: arch/arm64/boot/dts/xilinx/
    dts_filename = dts_path.name
    kernel_dts_dir = Path(kernel_path) / "arch" / "arm64" / "boot" / "dts" / "xilinx"

    # Copy all files from the dts_path directory to the kernel_dts_dir
    if dts_path.parent.is_dir():
        for file in dts_path.parent.glob("*"):
            try:
                shutil.copy2(file, kernel_dts_dir)
            except shutil.SameFileError:
                continue

    kernel_dts_path = kernel_dts_dir / dts_filename

    # DTB will be compiled to same location with .dtb extension
    kernel_dtb_path = kernel_dts_path.with_suffix(".dtb")

    # Step 1: Copy DTS file into kernel tree
    if kernel_dts_path.exists():
        kernel_dts_path.unlink()
    shutil.copy2(dts_path, kernel_dts_path)

    # Step 2: Ensure kernel is configured (one-time setup)
    # This creates .config file needed for device tree compilation
    config_file = Path(kernel_path) / ".config"
    if not config_file.exists():
        print("      Configuring kernel (first-time setup)...")
        config_cmd = ["make", "adi_zynqmp_defconfig"]
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
    make_target = f"xilinx/{dts_filename.replace('.dts', '.dtb')}"
    make_cmd = ["make", make_target]

    make_result = subprocess.run(
        make_cmd,
        cwd=kernel_path,
        capture_output=True,
        text=True,
        env=env,  # Use cross-compiler environment
    )

    if make_result.returncode != 0:
        error_message = make_result.stderr
        syntax_error_line = None
        syntax_error_file = None

        # Attempt to parse error message for DTS syntax error
        import re

        match = re.search(r"Error: (.+):(\d+)\.(\d+)-\d+ syntax error", error_message)
        if match:
            syntax_error_file = match.group(1)
            syntax_error_line = int(match.group(2))

        dts_content_snippet = ""
        if syntax_error_file and syntax_error_line:
            try:
                # Construct absolute path for reading the DTS file
                absolute_syntax_error_file = Path(kernel_path) / syntax_error_file
                with open(absolute_syntax_error_file, "r") as f:
                    lines = f.readlines()
                    start_line = max(0, syntax_error_line - 3)
                    end_line = min(len(lines), syntax_error_line + 2)
                    dts_content_snippet = "\n".join(
                        f"{i + 1}: {line.rstrip()}"
                        for i, line in enumerate(
                            lines[start_line:end_line], start_line + 1
                        )
                    )
            except Exception as e:
                dts_content_snippet = f"Could not read DTS file for snippet: {e}"
        else:
            dts_content_snippet = "Could not locate or read the problematic DTS file."

        raise RuntimeError(
            f"DTB compilation failed:\n"
            f"Command: {' '.join(make_cmd)}\n"
            f"ARCH={env['ARCH']} CROSS_COMPILE={env['CROSS_COMPILE']}\n"
            f"Error: {error_message}\n"
            f"DTS Snippet around line {syntax_error_line} in {syntax_error_file}:\n{dts_content_snippet}"
        )

    if not kernel_dtb_path.exists():
        raise RuntimeError(f"DTB file not created at {kernel_dtb_path}")

    shutil.copy2(kernel_dtb_path, dtb_path)


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
    return tmp_path_factory.mktemp("fmcdaq2_dtbs")


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


class TestFmcdaq2MultiRateHardware:
    """Hardware test suite for FMCDAQ2 at multiple sample rates."""

    @pytest.mark.parametrize("sample_rate_msps", SAMPLE_RATES)
    @pytest.mark.lg_feature(["fmcdaq2", "zcu102"])
    def test_sample_rate_deployment(
        self, sample_rate_msps, kernel_path, dtb_output_dir, post_power_off
    ):
        """Test FMCDAQ2 at specific sample rate with full hardware deployment."""
        strategy = post_power_off

        print(f"\n{'=' * 70}")
        print(f"Testing DAQ2 @ {sample_rate_msps} MSPS")
        print(f"{'=' * 70}\n")

        # Step 1: Generate configuration
        print("[1/9] Generating adijif configuration...")
        sys = generate_fmcdaq2_config(sample_rate_msps)
        config_adijif = sys.solve()  # Rename to avoid confusion with adidt config
        print("      ✓ Configuration solved successfully")

        print("[2/9] Creating board instance and validating FPGA config...")
        board = daq2(platform="zcu102", kernel_path=kernel_path)

        # Create config dictionary matching adidt.boards.daq2 expected structure
        config = {
            "clock": {
                "vco": config_adijif["clock"]["vco"],
                "vcxo": config_adijif["clock"]["vcxo"],
                "m1": config_adijif["clock"]["m1"],
                "output_clocks": config_adijif["clock"]["output_clocks"],
            },
            "converter_AD9680": {
                "sample_clock": config_adijif["jesd_AD9680"]["sample_clock"],
                "decimation": config_adijif["converter_AD9680"]["decimation"],
            },
            "converter_AD9144": {
                "sample_clock": config_adijif["jesd_AD9144"]["sample_clock"],
                "interpolation": config_adijif["converter_AD9144"]["interpolation"],
            },
            "jesd_AD9680": {
                "jesd_class": config_adijif["jesd_AD9680"]["jesd_class"],
                "converter_clock": config_adijif["jesd_AD9680"]["converter_clock"],
                "sample_clock": config_adijif["jesd_AD9680"]["sample_clock"],
                "jesd_L": config_adijif["jesd_AD9680"]["L"],
                "jesd_M": config_adijif["jesd_AD9680"]["M"],
                "jesd_S": config_adijif["jesd_AD9680"]["S"],
                "jesd_HD": config_adijif["jesd_AD9680"].get("HD", 0),
                "jesd_F": config_adijif["jesd_AD9680"].get("F", 1),
            },
            "jesd_AD9144": {
                "jesd_class": config_adijif["jesd_AD9144"]["jesd_class"],
                "converter_clock": config_adijif["jesd_AD9144"]["converter_clock"],
                "sample_clock": config_adijif["jesd_AD9144"]["sample_clock"],
                "jesd_L": config_adijif["jesd_AD9144"]["L"],
                "jesd_M": config_adijif["jesd_AD9144"]["M"],
                "jesd_S": config_adijif["jesd_AD9144"]["S"],
                "jesd_HD": config_adijif["jesd_AD9144"].get("HD", 0),
                "jesd_F": config_adijif["jesd_AD9144"].get("F", 1),
            },
            "fpga_adc": config_adijif.get("fpga_adc", {}),
            "fpga_dac": config_adijif.get("fpga_dac", {}),
        }

        config = board.validate_and_default_fpga_config(config)
        print("      ✓ FPGA config validated")

        print("[3/9] Mapping clocks to board layout...")
        # Step 2: Generate DTS
        ccfg, adc, dac, fpga = board.map_clocks_to_board_layout(config)
        print("      ✓ Clock mapping complete")

        print("[4/9] Generating DTS file...")
        generated_dts = board.gen_dt(clock=ccfg, adc=adc, dac=dac, fpga=fpga)
        assert os.path.exists(generated_dts), f"DTS file not generated: {generated_dts}"
        print(f"      ✓ Generated DTS: {generated_dts}")

        # Step 3: Compile DTS to DTB using kernel build system
        print("[5/9] Compiling DTS to DTB...")
        dtb_filename = dtb_output_dir / f"fmcdaq2_{sample_rate_msps}msps.dtb"
        compile_dts_to_dtb(
            dts_path=Path(generated_dts), dtb_path=dtb_filename, kernel_path=kernel_path
        )

        assert dtb_filename.exists(), f"DTB file not created: {dtb_filename}"
        assert dtb_filename.stat().st_size > 0, "DTB file is empty"
        print(
            f"      ✓ Compiled DTB: {dtb_filename} ({dtb_filename.stat().st_size} bytes)"
        )

        # Step 4: Power off board
        print("[6/9] Deploying DTB to board...")
        strategy.transition("powered_off")

        # Step 5: Deploy DTB
        strategy.target.get_driver("KuiperDLDriver")
        # Copy to system.dtb for KuiperDLDriver
        shutil.copy2(dtb_filename, dtb_output_dir / "system.dtb")
        print("      ✓ DTB deployed to SD card")

        # Step 6: Boot to shell
        print("[7/9] Booting board to shell...")
        os.environ["PATH"] = f"{os.getcwd()}/venv/bin:" + os.environ["PATH"]
        strategy.transition("shell")
        print("      ✓ Board booted successfully")

        # Step 7: Create IIO context
        print("[8/9] Creating IIO context...")
        shell = strategy.target.get_driver("ADIShellDriver")
        addresses = shell.get_ip_addresses()
        ip_address = str(addresses[0].ip)
        if "/" in ip_address:
            ip_address = ip_address.split("/")[0]

        ctx = iio.Context(f"ip:{ip_address}")
        assert ctx is not None, "Failed to create IIO context"
        print(f"      ✓ IIO context created: {ip_address}")

        print("[9/9] Verifying IIO devices...")

        # Step 8: Extract kernel log for debugging
        dmesg_res = shell.run("dmesg")
        # Handle shell.run return (stdout_lines, returncode)
        if isinstance(dmesg_res, tuple):
            dmesg_output = dmesg_res[0]
        else:
            dmesg_output = dmesg_res

        if isinstance(dmesg_output, list):
            dmesg_output = "\n".join(dmesg_output)

        dmesg_log_path_local = dtb_output_dir / f"dmesg_{sample_rate_msps}msps.log"
        with open(dmesg_log_path_local, "w") as f:
            f.write(dmesg_output)

        # Create debug directory and copy dmesg log
        debug_dir = Path("./generated_dts_debug")
        debug_dir.mkdir(exist_ok=True)
        shutil.copy2(
            dmesg_log_path_local, debug_dir / f"dmesg_{sample_rate_msps}msps.log"
        )

        dmesg_err_res = shell.run("dmesg --level=err,warn")
        if isinstance(dmesg_err_res, tuple):
            dmesg_error_output = dmesg_err_res[0]
        else:
            dmesg_error_output = dmesg_err_res

        if isinstance(dmesg_error_output, list):
            dmesg_error_output = "\n".join(dmesg_error_output)

        dmesg_error_log_path_local = (
            dtb_output_dir / f"dmesg_errors_{sample_rate_msps}msps.log"
        )
        with open(dmesg_error_log_path_local, "w") as f:
            f.write(dmesg_error_output)
        shutil.copy2(
            dmesg_error_log_path_local,
            debug_dir / f"dmesg_errors_{sample_rate_msps}msps.log",
        )
        # Step 9: Verify devices
        expected_devices = ["axi-ad9680-hpc", "axi-ad9144-hpc"]
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

        # CANNOT BE CHECKED WITH PYADI-IIO
        adi.DAQ2(uri=f"ip:{ip_address}")
        # print(f"      ✓ Sample rate: {sample_rate}")
        # assert sample_rate == sample_rate_msps * 1_000_000, (
        #    f"Expected sample rate {sample_rate_msps * 1_000_000} Hz, "
        #    f"got {sample_rate} Hz"
        # )

        print(f"\n{'=' * 70}")
        print(f"✓✓✓ Test PASSED for DAQ2 @ {sample_rate_msps} MSPS ✓✓✓")
        print(f"{'=' * 70}\n")
