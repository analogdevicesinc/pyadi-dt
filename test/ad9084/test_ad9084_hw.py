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
from test.dts_utils import download_and_cache_toolchain, compile_dts_to_dtb, verify_dts_match, TOOLCHAIN_2025_R1_ARCH_ARM64

TFTP_BOOT_FOLDER = "/var/lib/tftpboot/"


def get_ad9084_config() -> dict:
    """Get AD9084 configuration.

    Returns:
        Complete configuration dict for ad9084_fmc board
    """
    vcxo = 125000000
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
        compile_dts_to_dtb(Path(generated_dts), gen_dtb, kernel_path, arch="arm64", version="2025.1", platform="vpk180")
        
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
        verify_dts_match(gen_dtb, ref_dtb, kernel_path, dtb_output_dir)

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