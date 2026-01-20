"""AD9084+ZCU102 Hardware Test Suite

This module tests AD9084 FMC board on ZCU102
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
- AD9084 hardware on ZCU102
"""

import pytest
import os
import shutil
import subprocess
import urllib.request
import tarfile
from pathlib import Path
from adidt.boards.ad9084_fmc import ad9084_fmc
import iio
import adijif
import adi

TFTP_BOOT_FOLDER = "/var/lib/tftpboot/"

# ARM GNU Toolchain configuration for cross-compiling ARM64 device trees
# Vivado/Vitis 2023.2
TOOLCHAIN_2023_R2_URL_ARM64 = "https://developer.arm.com/-/media/Files/downloads/gnu/12.2.rel1/binrel/arm-gnu-toolchain-12.2.rel1-x86_64-aarch64-none-elf.tar.xz"
TOOLCHAIN_2023_R2_VERSION = "12.2.rel1"
TOOLCHAIN_2023_R2_ARCH_ARM64 = "aarch64-none-elf"

# ARM GNU Toolchain configuration for cross-compiling ARM32 device trees
# Vivado/Vitis 2023.2
TOOLCHAIN_2023_R2_URL_ARM32 = "https://developer.arm.com/-/media/Files/downloads/gnu/12.2.rel1/binrel/arm-gnu-toolchain-12.2.rel1-x86_64-arm-none-eabi.tar.xz"
TOOLCHAIN_2023_R2_ARCH_ARM32 = "arm-none-eabi"

# ARM GNU Toolchain configuration for cross-compiling ARM64 device trees
# Vivado/Vitis 2025.1
TOOLCHAIN_2025_R1_URL_ARM64 = "https://developer.arm.com/-/media/Files/downloads/gnu/13.3.rel1/binrel/arm-gnu-toolchain-13.3.rel1-x86_64-aarch64-none-elf.tar.xz"
TOOLCHAIN_2025_R1_VERSION = "13.3.rel1"
TOOLCHAIN_2025_R1_ARCH_ARM64 = "aarch64-none-elf"


def download_and_cache_toolchain(arch: str = "arm64", version: str = "2023.2", cache_dir: Path = None) -> Path:
    """Download and cache ARM GNU toolchain for cross-compilation.

    Downloads the ARM GNU toolchain for arm or arm64 from ARM's official site
    and extracts it to a cache directory. If already cached, skips download.

    Args:
        arch: Target architecture ('arm' or 'arm64')
        version: Target version ('2023.2' or '2025.1')
        cache_dir: Directory to cache toolchain. Defaults to ~/.cache/pyadi-dt/

    Returns:
        Path to toolchain bin directory containing cross-compiler

    Raises:
        RuntimeError: If download or extraction fails or arch is invalid
    """
    # Select toolchain based on architecture
    if version == "2023.2": 
        if arch == "arm64":
            toolchain_url = TOOLCHAIN_2023_R2_URL_ARM64
            toolchain_version = TOOLCHAIN_2023_R2_VERSION
            toolchain_arch = TOOLCHAIN_2023_R2_ARCH_ARM64
        elif arch == "arm":
            toolchain_url = TOOLCHAIN_2023_R2_URL_ARM32
            toolchain_version = TOOLCHAIN_2023_R2_VERSION
            toolchain_arch = TOOLCHAIN_2023_R2_ARCH_ARM32
        else:
            raise ValueError(f"Unsupported architecture: {arch}. Must be 'arm' or 'arm64'")
    elif version == "2025.1":
        if arch == "arm64":
            toolchain_url = TOOLCHAIN_2025_R1_URL_ARM64
            toolchain_version = TOOLCHAIN_2025_R1_VERSION
            toolchain_arch = TOOLCHAIN_2025_R1_ARCH_ARM64
        else:
            raise ValueError(f"Unsupported architecture: {arch}. Must be 'arm64'")
    else:
        raise ValueError(f"Unsupported version: {version}. Must be '2023.2' or '2025.1'")

    if toolchain_url == "":
        raise ValueError(f"Toolchain URL not found for version: {version}")

    # Determine cache directory
    if cache_dir is None:
        cache_dir = Path.home() / ".cache" / "pyadi-dt" / "toolchains"
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Expected toolchain directory after extraction
    toolchain_name = f"arm-gnu-toolchain-{toolchain_version}-x86_64-{toolchain_arch}"
    toolchain_dir = cache_dir / toolchain_name
    toolchain_bin = toolchain_dir / "bin"

    # Check if already cached
    if toolchain_bin.exists():
        print(f"      Using cached toolchain: {toolchain_dir}")
        return toolchain_bin

    # Download toolchain
    print(f"      Downloading ARM GNU toolchain {toolchain_version} ({arch})...")
    tarball_path = cache_dir / f"{toolchain_name}.tar.xz"

    try:
        with urllib.request.urlopen(toolchain_url) as response:
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            chunk_size = 1024 * 1024  # 1MB chunks

            with open(tarball_path, 'wb') as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"      Progress: {percent:.1f}% ({downloaded // (1024*1024)}MB / {total_size // (1024*1024)}MB)", end='\r')

        print(f"\n      Download complete: {tarball_path}")

        # Extract toolchain
        print(f"      Extracting toolchain...")
        with tarfile.open(tarball_path, 'r:xz') as tar:
            tar.extractall(cache_dir)

        # Verify extraction
        if not toolchain_bin.exists():
            raise RuntimeError(f"Toolchain extraction failed: {toolchain_bin} not found")

        # Clean up tarball to save space
        tarball_path.unlink()
        print(f"      Toolchain ready: {toolchain_bin}")

        return toolchain_bin

    except Exception as e:
        # Clean up on failure
        if tarball_path.exists():
            tarball_path.unlink()
        raise RuntimeError(f"Failed to download/extract toolchain: {e}")


def get_ad9084_config() -> dict:
    """Get AD9084 configuration.

    Returns:
        Complete configuration dict for ad9084_fmc board
    """
    vcxo = 122880000
    sys = adijif.system("ad9084", "hmc7044", "xilinx", vcxo)
    sys.fpga.setup_by_dev_kit_name("vpk180")

    cfg = sys.solve()

    # Map generated keys to expected keys for adidt
    clks = cfg["clock"]["output_clocks"]

    clks["DEV_CLK"] = clks.pop("AD9084_ref_clk")
    clks["DEV_CLK"]["channel"] = 13
    clks["DEV_SYSREF"] = clks.pop("adc_sysref")
    clks["DEV_SYSREF"]["channel"] = 12
    clks["FMC_CLK"] = clks.pop("vpk180_adc_ref_clk")
    clks["FMC_CLK"]["channel"] = 1
    clks["FMC_SYSREF"] = clks.pop("dac_sysref")
    clks["FMC_SYSREF"]["channel"] = 3
    
    # Not used but need to be removed
    clks.pop("vpk180_adc_device_clk")
    clks.pop("vpk180_dac_ref_clk")
    clks.pop("vpk180_dac_device_clk")

    return cfg


def compile_dts_to_dtb(dts_path: Path, dtb_path: Path, kernel_path: str, arch: str = "arm64", version: str = "2023.2", cross_compile: str = None) -> None:
    """Compile DTS to DTB using kernel build system with cross-compiler.
    """
    # Validate architecture
    if arch not in ["arm", "arm64"]:
        raise ValueError(f"Unsupported architecture: {arch}. Must be 'arm' or 'arm64'")

    # Download and cache cross-compiler if not provided
    if cross_compile is None:
        print(f"      Setting up {arch.upper()} cross-compiler...")
        toolchain_bin = download_and_cache_toolchain(arch=arch, version=version)

        if version == "2023.2":
            if arch == "arm64":
                cross_compile = f"{toolchain_bin}/{TOOLCHAIN_ARCH_ARM64}-"
            else:  # arch == "arm"
                cross_compile = f"{toolchain_bin}/{TOOLCHAIN_ARCH_ARM32}-"
        elif version == "2025.1":
            if arch == "arm64":
                cross_compile = f"{toolchain_bin}/{TOOLCHAIN_ARCH_ARM64}-"
            else:  # arch == "arm"
                cross_compile = f"{toolchain_bin}/{TOOLCHAIN_ARCH_ARM32}-"
        else:
            raise ValueError(f"Unsupported version: {version}. Must be '2023.2' or '2025.1'")

        print(f"      ✓ Cross-compiler ready: {cross_compile}")

    # Set up environment for kernel compilation
    env = os.environ.copy()
    env['ARCH'] = arch
    env['CROSS_COMPILE'] = cross_compile

    # Determine platform-specific paths
    dts_filename = dts_path.name
    if arch == "arm64":
        kernel_dts_dir = Path(kernel_path) / "arch" / arch / "boot" / "dts" / "xilinx"
    else:
        kernel_dts_dir = Path(kernel_path) / "arch" / arch / "boot" / "dts"
    kernel_dts_path = kernel_dts_dir / dts_filename

    # DTB will be compiled to same location with .dtb extension
    kernel_dtb_path = kernel_dts_path.with_suffix('.dtb')

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
        config_cmd,
        cwd=kernel_path,
        capture_output=True,
        text=True,
        env=env
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
        make_cmd,
        cwd=kernel_path,
        capture_output=True,
        text=True,
        env=env
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


class ad9084_fmc_no_plugin(ad9084_fmc):
    """AD9084 FMC board with plugin mode disabled"""
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
    return tmp_path_factory.mktemp("ad9084_dtbs")


@pytest.fixture(scope="module")
def post_power_off(strategy):
    """Ensure board powers off after all tests."""
    yield strategy
    #strategy.transition("soft_off")


# Test class

class TestAD9084Hardware:
    """Hardware test suite for AD9084"""

    def test_vpk180_rev10_ad9084(
        self,
        kernel_path,
        dtb_output_dir,
        post_power_off
    ):
        """Test reference configuration matching versal-vpk180-reva-ad9084.dts"""
        strategy = post_power_off

        version = "2025.1"
        
        # Helper to create channel config
        def mk_clk(channel, divider):
            return {"channel": channel, "divider": divider}

        config = {}

        # Step 2: Generate DTS
        print(f"[1/4] Generating DTS from manual configuration...")
        # board = ad9084_fmc_no_plugin(platform="vpk180", kernel_path=kernel_path)
        
        # dts_filename = dtb_output_dir / "generated_ad9084.dts"
        # board.output_filename = str(dts_filename)

        
        # 3b. Compile Reference
        ref_dts_name = "versal-vpk180-reva-ad9084.dts"
        # versal-vpk180-reva-ad9084-204C-M4-L1-NP16-20p0-16x4.dts
        ref_dts_path = Path(kernel_path) / "arch/arm64/boot/dts/xilinx" / ref_dts_name
        if not ref_dts_path.exists():
            pytest.skip(f"Reference DTS {ref_dts_name} not found in kernel")
            
        ref_dtb = dtb_output_dir / "reference.dtb"

        if ref_dts_path.resolve() == (Path(kernel_path) / "arch/arm64/boot/dts/xilinx" / ref_dts_name).resolve():
            # It is the same file.
            pass
        
        # We'll trust compile_dts_to_dtb handles it or just manually trigger make
        env = os.environ.copy()
        env['ARCH'] = "arm64"
        # Setup cross compile
        toolchain_bin = download_and_cache_toolchain(arch="arm64", version=version)
        if version == "2023.2":
            env['CROSS_COMPILE'] = f"{toolchain_bin}/{TOOLCHAIN_2023_R2_ARCH_ARM64}-"
        else:
            env['CROSS_COMPILE'] = f"{toolchain_bin}/{TOOLCHAIN_2025_R1_ARCH_ARM64}-"
        
        make_target = f"xilinx/{ref_dts_name.replace('.dts', '.dtb')}"
        make_cmd = ["make", make_target]
        print(f"      Compiling Reference: {' '.join(make_cmd)}")
        subprocess.run(["make", "clean", "distclean"], cwd=kernel_path, env=env, check=True, capture_output=True)
        subprocess.run(["make", "adi_versal_apollo_defconfig"], cwd=kernel_path, env=env, check=True, capture_output=True)
        subprocess.run(make_cmd, cwd=kernel_path, env=env, check=True, capture_output=True)
        
        # Move result to output dir
        built_ref_dtb = Path(kernel_path) / "arch/arm64/boot/dts" / make_target
        shutil.copy2(built_ref_dtb, ref_dtb)
        
        assert ref_dtb.exists()

        # Step 4: Deploy (Run)
        print(f"[3/4] Deploying to board...")
        strategy.transition("powered_off")
        kuiper = strategy.target.get_driver("KuiperDLDriver")
        
        # # Rename for deployment
        deploy_dtb = dtb_output_dir / "system.dtb"
        # shutil.copy2(gen_dtb, deploy_dtb)
        # shutil.copy2(ref_dtb, deploy_dtb)
        shutil.copy2(ref_dtb, TFTP_BOOT_FOLDER)
        
        # kuiper.add_files_to_target(str(deploy_dtb))
        strategy.transition("shell")
        
        # Step 5: Verify IIO devices
        print(f"[4/4] Verifying IIO context...")
        shell = strategy.target.get_driver("ADIShellDriver")
        ip = str(shell.get_ip_addresses()[0].ip).split('/')[0]
        ctx = iio.Context(f"ip:{ip}")
        
        assert "axi-ad9084-rx-hpc" in [d.name for d in ctx.devices]
        assert "axi-ad9084-tx-hpc" in [d.name for d in ctx.devices]
        
        print("      ✓ Referenced configuration verification passed")