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
                cross_compile = f"{toolchain_bin}/{TOOLCHAIN_2023_R2_ARCH_ARM64}-"
            else:  # arch == "arm"
                cross_compile = f"{toolchain_bin}/{TOOLCHAIN_2023_R2_ARCH_ARM32}-"
        elif version == "2025.1":
            if arch == "arm64":
                cross_compile = f"{toolchain_bin}/{TOOLCHAIN_2025_R1_ARCH_ARM64}-"
            else:  # arch == "arm"
                # Assuming 2025.1 arm32 follows same pattern or is not supported yet?
                # The file didn't define TOOLCHAIN_2025_R1_ARCH_ARM32, so we might fail here if used.
                # Lines 81-87 in download_and_cache_toolchain suggest 2025.1 only supports arm64 for now.
                raise ValueError("ARM32 not supported for version 2025.1")
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
        
        # Step 1: Manual configuration matching versal-vpk180-reva-ad9084.dts
        config = {
            "clock": {
                "hmc7044_vcxo": 125000000,
                "hmc7044_vco": 2500000000,
                "adf4030_bsync_frequency": 9765625,
                "adf4382_output_frequency": 20000000000,
                "output_clocks": {
                    "ADF4030_REFIN": {"source_port": 1, "divider": 20},
                    "ADF4030_BSYNC0": {"source_port": 3, "divider": 256},
                    "CORE_CLK_TX": {"source_port": 8, "divider": 8},
                    "CORE_CLK_RX": {"source_port": 9, "divider": 8},
                    "FPGA_REFCLK": {"source_port": 10, "divider": 8},
                    "CORE_CLK_RX_B": {"source_port": 11, "divider": 8},
                    "CORE_CLK_TX_B": {"source_port": 12, "divider": 8}
                }
            },
            "jesd_rx": {
                "lanerate_khz": 20625000,
                "link_clk": 312500000,
                "subclass": 1
            },
            "jesd_tx": {
                "lanerate_khz": 20625000,
                "link_clk": 312500000
            },
            "device_profile": "204C_M4_L4_NP16_20p0_4x4.bin",
            "lane_mapping": {
                "rx_physical": [5, 1, 3, 7, 11, 11, 11, 11, 11, 11, 11, 11],
                "tx_logical": [11, 11, 11, 1, 11, 11, 11, 11, 2, 3, 11, 0],
                "jrx1_physical": [1, 7, 10, 3, 11, 11, 11, 11, 11, 11, 11, 11],
                "jtx1_logical": [11, 11, 1, 0, 11, 2, 11, 3, 11, 11, 11, 11]
            },
            "fpga_adc": {},
            "fpga_dac": {}
        }

        # Step 2: Generate DTS
        print(f"[1/4] Generating DTS from manual configuration...")
        board = ad9084_fmc_no_plugin(platform="vpk180", kernel_path=kernel_path)
        
        # Apply defaults
        config = board.validate_and_default_fpga_config(config)

        dts_filename = dtb_output_dir / "generated_ad9084.dts"
        board.output_filename = str(dts_filename)

        # Map configuration
        ccfg, adc, dac, fpga = board.map_clocks_to_board_layout(config)

        # Generate
        generated_dts = board.gen_dt(
            clock=ccfg,
            adc=adc,
            dac=dac,
            fpga=fpga,
            config_source="manual_config"
        )
        
        assert os.path.exists(generated_dts), f"DTS file not generated: {generated_dts}"
        print(f"      ✓ Generated DTS: {generated_dts}")

        # Step 3: Verify against reference
        print(f"[2/4] Verifying against reference...")
        
        # 3a. Compile Generated
        gen_dtb = dtb_output_dir / "generated.dtb"
        compile_dts_to_dtb(Path(generated_dts), gen_dtb, kernel_path, arch="arm64", version="2025.1")
        
        # 3b. Compile Reference
        ref_dts_name = "versal-vpk180-reva-ad9084.dts"
        ref_dts_path = Path(kernel_path) / "arch/arm64/boot/dts/xilinx" / ref_dts_name
        
        if not ref_dts_path.exists():
            pytest.skip(f"Reference DTS {ref_dts_name} not found in kernel")
            
        ref_dtb = dtb_output_dir / "reference.dtb"

        # Check if reference file is in place (it should be)
        if ref_dts_path.resolve() == (Path(kernel_path) / "arch/arm64/boot/dts/xilinx" / ref_dts_name).resolve():
            pass
        
        # Compile reference manually to ensure it uses the same env/toolchain
        env = os.environ.copy()
        env['ARCH'] = "arm64"
        toolchain_bin = download_and_cache_toolchain(arch="arm64", version="2025.1")
        env['CROSS_COMPILE'] = f"{toolchain_bin}/{TOOLCHAIN_2025_R1_ARCH_ARM64}-"
        
        make_target = f"xilinx/{ref_dts_name.replace('.dts', '.dtb')}"
        make_cmd = ["make", make_target]
        print(f"      Compiling Reference: {' '.join(make_cmd)}")
        
        # Clean and configure might be needed if not already done, but usually incremental is fine.
        # Ideally we should match compile_dts_to_dtb steps but simpler here.
        # compile_dts_to_dtb does: make defconfig, make target.
        # let's rely on compile_dts_to_dtb side-effects if we want, OR just call make.
        # We'll use the same commands.
        
        subprocess.run(["make", "adi_versal_apollo_defconfig"], cwd=kernel_path, env=env, check=True, capture_output=True)
        subprocess.run(make_cmd, cwd=kernel_path, env=env, check=True, capture_output=True)
        
        built_ref_dtb = Path(kernel_path) / "arch/arm64/boot/dts" / make_target
        shutil.copy2(built_ref_dtb, ref_dtb)
        
        assert ref_dtb.exists()
        
        print(f"      Generated DTB Size: {gen_dtb.stat().st_size}")
        print(f"      Reference DTB Size: {ref_dtb.stat().st_size}")

        print(f"[3/4] Verifying content match...")
        
        dtc_path = Path(kernel_path) / "scripts/dtc/dtc"
        if not dtc_path.exists():
             dtc_path = "dtc"
        
        def dtb_to_dts(dtb, output):
            cmd = [str(dtc_path), "-I", "dtb", "-O", "dts", "-o", str(output), "-s", str(dtb)]
            subprocess.run(cmd, check=True, capture_output=True)
            
        gen_dts_flat = dtb_output_dir / "generated_flat.dts"
        ref_dts_flat = dtb_output_dir / "reference_flat.dts"
        
        try:
            dtb_to_dts(gen_dtb, gen_dts_flat)
            dtb_to_dts(ref_dtb, ref_dts_flat)
            
            # Read and Compare text
            with open(gen_dts_flat) as f: gen_text = f.readlines()
            with open(ref_dts_flat) as f: ref_text = f.readlines()
            
            print("      Comparing flattened DTS content...")
            
            mismatches = []
            
            ref_set = set([l.strip() for l in ref_text])
            
            for line in gen_text:
                l = line.strip()
                if not l: continue
                # Skip phandle noise if it varies
                if "phandle =" in l: continue 
                if "linux,phandle" in l: continue
                
                if l not in ref_set:
                     mismatches.append(f"Excess in GEN: {l}")
            
            # Also check if REF has lines missing in GEN (Critical!)
            gen_set = set([l.strip() for l in gen_text])
            for line in ref_text:
                l = line.strip()
                if not l: continue
                if "phandle =" in l: continue 
                if "linux,phandle" in l: continue
                
                if l not in gen_set:
                     mismatches.append(f"Missing in GEN: {l}")

            if mismatches:
                # Dump first few
                print("      Mismatch details:")
                for m in mismatches[:50]:
                    print(f"      {m}")
                raise Exception(f"Found {len(mismatches)} mismatches in generated DTS content")

            print("      ✓ DTS Content Matches Reference")
            
        except Exception as e:
            print(f"      Warning: DTC comparison failed: {e}")
            raise e

        # Step 4: Deploy (Run)
        print(f"[3/4] Deploying to board...")
        strategy.transition("powered_off")
        
        # Copy generated DTB to TFTP
        print(f"      Copying {gen_dtb} to {TFTP_BOOT_FOLDER}")
        shutil.copy2(gen_dtb, Path(TFTP_BOOT_FOLDER) / "system.dtb")
        # Ensure the filename matches what the board expects.
        # If the board expects 'reference.dtb' (as the original test copied it), we might need to match that.
        # Previous test: shutil.copy2(ref_dtb, TFTP_BOOT_FOLDER) -> copies as 'reference.dtb' (basename of ref_dtb)
        # But 'ref_dtb' in previous test was: ref_dtb = dtb_output_dir / "reference.dtb"
        # So it was copying 'reference.dtb'.
        # If I want to verify the GENERATED one, I should copy gen_dtb but maybe rename it to 'reference.dtb' if the 
        # boot script is hardcoded to load that specific filename. 
        # However, typically 'system.dtb' is standard for ADI scripts. 
        # The prompt says: "Keep the TFTP implementation used already".
        # The already used implementation copied 'reference.dtb'.
        # I will assume the board uses whatever is latest or I should rename my generated one to 'reference.dtb' 
        # to trick the board if necessary, OR 'system.dtb' if that's standard. 
        # I'll stick to 'reference.dtb' name for TFTP to be safe if that's what was working, 
        # but the content will be from generated DTB.
        
        shutil.copy2(gen_dtb, Path(TFTP_BOOT_FOLDER) / "reference.dtb")
        
        strategy.transition("shell")
        
        # Step 5: Verify IIO devices
        print(f"[4/4] Verifying IIO context...")
        shell = strategy.target.get_driver("ADIShellDriver")
        ip = str(shell.get_ip_addresses()[0].ip).split('/')[0]
        ctx = iio.Context(f"ip:{ip}")
        
        assert "axi-ad9084-rx-hpc" in [d.name for d in ctx.devices]
        assert "axi-ad9084-tx-hpc" in [d.name for d in ctx.devices]
        
        print("      ✓ Referenced configuration verification passed")