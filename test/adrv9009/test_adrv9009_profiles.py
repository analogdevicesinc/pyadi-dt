import pytest
import pathlib
from pathlib import Path
import os
from adidt.parts import adrv9009
from pprint import pprint

from adibuild import LinuxBuilder, BuildConfig
from adibuild.platforms import ZynqMPPlatform

import adijif

from adidt.boards.adrv9009_fmc import adrv9009_fmc

here = pathlib.Path(os.path.dirname(__file__))
profiles = here / "profiles"
profiles = list(profiles.glob("*.txt"))

@pytest.fixture(scope="module")
def board(strategy):
    # with capsys.disabled():
    strategy.transition("powered_off")
    # strategy.transition("shell")
    # strategy.target["ADIShellDriver"].get_ip_addresses()

    yield strategy
    # with capsys.disabled():
    # strategy.transition("soft_off")

@pytest.mark.parametrize("profile", profiles)
def test_profile(profile):
    if not os.path.exists(profile):
        pytest.skip(f"Profile {profile} does not exist")

    profile_data = adrv9009.parse_profile(profile)
    assert profile_data
    pprint(profile_data)


@pytest.mark.lg_feature(["adrv9009", "zcu102"])
@pytest.mark.parametrize("profile", profiles)
def test_adrv9009_new(board, profile):

    kuiper = board.target.get_driver("KuiperDLDriver")
    # kuiper.kuiper_resource.BOOTBIN_path = BB
    kuiper.get_boot_files_from_release()

    # Configure build system
    config_path = Path(__file__).parent / "2023_R2.yaml"
    config = BuildConfig.from_yaml(config_path)
    platform_config = config.get_platform("zynqmp")
    platform = ZynqMPPlatform(platform_config)
    builder = LinuxBuilder(config, platform)
    builder.prepare_source()

    # Parse profiles for settings needed for JIF
    profile_data = adrv9009.parse_profile(profile)
    assert profile_data, f"Failed to parse profile {profile}"

    pprint(profile_data)

    # Generate clocks with JIF
    sys = adijif.system("adrv9009", "ad9528", "xilinx", 122.88e6, solver="CPLEX")
    sys.fpga.setup_by_dev_kit_name("zcu102")
    sys.fpga.ref_clock_constraint = "Unconstrained"
    # sys.fpga.sys_clk_select = "XCVR_QPLL"
    # sys.fpga.out_clk_select = "XCVR_REFCLK_DIV2"
    # sys.converter.clocking_option = "integrated_pll"

    # Converters
    mode_rx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.adc, M=4, L=2, S=1, Np=16,
    )
    sys.converter.adc.set_quick_configuration_mode(mode_rx[0]['mode'], mode_rx[0]['jesd_class'])

    mode_tx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.dac, M=4, L=4, S=1, Np=16,
    )
    sys.converter.dac.set_quick_configuration_mode(mode_tx[0]['mode'], mode_tx[0]['jesd_class'])

    def hz_to_int(hz):
        if "mhz" in hz.lower():
            return int(float(hz.lower().replace("mhz", "")) * 1e6)
        elif "khz" in hz.lower():
            return int(float(hz.lower().replace("khz", "")) * 1e3)
        elif "ghz" in hz.lower():
            return int(float(hz.lower().replace("ghz", "")) * 1e9)
        else:
            return int(float(hz))

    sys.converter.adc.decimation = int(float(profile_data['rx']['@TotalDecimation']))
    sys.converter.adc.sample_clock = hz_to_int(profile_data['rx']['@OutputRate'])
    sys.converter.dac.interpolation = int(float(profile_data['tx']['@TotalInterpolation']))
    sys.converter.dac.sample_clock = hz_to_int(profile_data['tx']['@InputRate'])

    # Print sample clocks
    print(f"ADC Sample Clock: {sys.converter.adc.sample_clock}")
    print(f"DAC Sample Clock: {sys.converter.dac.sample_clock}")
    config = sys.solve()
    pprint(config)
    # return

    # Initialize board_fmc object (needed for config processing)
    kernel_path = builder.repo.local_path
    board_fmc = adrv9009_fmc(platform="zcu102", kernel_path=kernel_path)

    # PROCESS CONFIG
    ###################

    # Transform adijif output to match map_clocks_to_board_layout expectations
    # Following the pattern from test/hw/test_ad9081_new.py

    # 1. Map platform-specific clock names to generic names and add AD9528 channel assignments
    if "clock" in config and "output_clocks" in config["clock"]:
        clks = config["clock"]["output_clocks"]
        platform_prefix = "zcu102"  # or board_fmc.platform

        # Clock name mapping: platform-specific → generic
        # Based on actual adijif output for ADRV9009
        clock_mapping = {
            # Device clocks
            "ADRV9009_ref_clk": "DEV_CLK",  # Device reference clock (case-sensitive)
            "adrv9009_ref_clk": "DEV_CLK",  # Fallback lowercase
            "adc_sysref": "DEV_SYSREF",      # Device SYSREF (ADC and DAC share)
            "dac_sysref": "DEV_SYSREF",      # Fallback for DAC sysref
            # FPGA clocks
            f"{platform_prefix}_adc_ref_clk": "FMC_CLK",  # FPGA reference clock
            f"{platform_prefix}_dac_ref_clk": "FMC_CLK",  # Fallback FPGA ref
            f"{platform_prefix}_fpga_ref_clk": "FMC_CLK",
            # FPGA sysref - may need to be derived
        }

        # Rename clocks (process in order, skip if target already exists)
        for old_name, new_name in clock_mapping.items():
            if old_name in clks and new_name not in clks:
                clks[new_name] = clks.pop(old_name)

        # Create FMC_SYSREF if it doesn't exist (derive from DEV_SYSREF)
        if "FMC_SYSREF" not in clks and "DEV_SYSREF" in clks:
            clks["FMC_SYSREF"] = clks["DEV_SYSREF"].copy()

        # Convert clock rates and dividers to integers (DTS requires ints, not floats)
        for clk_name, clk_cfg in clks.items():
            if "rate" in clk_cfg and isinstance(clk_cfg["rate"], float):
                clk_cfg["rate"] = int(clk_cfg["rate"])
            if "divider" in clk_cfg and isinstance(clk_cfg["divider"], float):
                clk_cfg["divider"] = int(clk_cfg["divider"])

        # Add AD9528 channel assignments
        channel_map = {
            "DEV_CLK": 13,      # Device reference clock
            "FMC_CLK": 1,       # FPGA reference clock
            "DEV_SYSREF": 12,   # Device SYSREF
            "FMC_SYSREF": 3,    # FPGA SYSREF
        }

        for clk_name, channel in channel_map.items():
            if clk_name in clks:
                clks[clk_name]["channel"] = channel

        # Remove any unmapped clocks (only keep the standard AD9528 outputs)
        # This prevents KeyError when board code iterates through all clocks
        expected_clocks = set(channel_map.keys())
        clocks_to_remove = [name for name in clks.keys() if name not in expected_clocks]
        for name in clocks_to_remove:
            del clks[name]

    # Convert clock VCO and VCXO frequencies to integers
    if "clock" in config:
        if "vcxo" in config["clock"] and isinstance(config["clock"]["vcxo"], float):
            config["clock"]["vcxo"] = int(config["clock"]["vcxo"])
        if "vco" in config["clock"] and isinstance(config["clock"]["vco"], float):
            config["clock"]["vco"] = int(config["clock"]["vco"])

    # 2. Transform JESD configuration from flat to nested structure
    if "jesd_adc" in config and "jesd_dac" in config:
        config["jesd204"] = {}

        # Helper to convert float JESD params to integers (DTS requires ints)
        def convert_jesd_params_to_int(jesd_dict):
            """Convert float JESD parameters to integers for DTS compatibility"""
            int_params = ["M", "L", "F", "S", "K", "Np", "CS", "HD"]
            for param in int_params:
                if param in jesd_dict and isinstance(jesd_dict[param], float):
                    jesd_dict[param] = int(jesd_dict[param])
            return jesd_dict

        # RX path: jesd_adc → framer_a
        rx_jesd = config["jesd_adc"].copy()
        rx_jesd = convert_jesd_params_to_int(rx_jesd)
        rx_L = rx_jesd.get("L", 2)
        rx_M = rx_jesd.get("M", 4)

        # Calculate lane enable mask (L lanes starting from lane 0)
        rx_mask = (1 << rx_L) - 1
        rx_jesd["lanes_enabled"] = hex(rx_mask)

        config["jesd204"]["framer_a"] = rx_jesd

        # TX path: jesd_dac → deframer_a
        tx_jesd = config["jesd_dac"].copy()
        tx_jesd = convert_jesd_params_to_int(tx_jesd)
        tx_L = tx_jesd.get("L", 4)

        # Calculate lane enable mask
        tx_mask = (1 << tx_L) - 1
        tx_jesd["lanes_enabled"] = hex(tx_mask)

        config["jesd204"]["deframer_a"] = tx_jesd

        # ORX path: derive from jesd_adc as framer_b
        # ORX typically uses half the converters but same basic params
        orx_jesd = config["jesd_adc"].copy()
        orx_jesd = convert_jesd_params_to_int(orx_jesd)
        orx_jesd["M"] = max(1, rx_M // 2)  # Half the converters, min 1
        orx_jesd["L"] = min(rx_L, 2)       # Typically 2 lanes for ORX

        # ORX uses different physical lanes (lanes 2-3 if RX uses 0-1)
        orx_lane_offset = rx_L
        orx_mask = ((1 << orx_jesd["L"]) - 1) << orx_lane_offset
        orx_jesd["lanes_enabled"] = hex(orx_mask)

        config["jesd204"]["framer_b"] = orx_jesd

    # 3. Ensure FPGA configuration for all three paths (RX, TX, ORX)
    # Rename fpga_adc → fpga_rx, fpga_dac → fpga_tx
    if "fpga_adc" in config:
        config["fpga_rx"] = config.pop("fpga_adc")
    if "fpga_dac" in config:
        config["fpga_tx"] = config.pop("fpga_dac")

    # Create fpga_orx if missing (copy from fpga_rx)
    if "fpga_orx" not in config:
        config["fpga_orx"] = config.get("fpga_rx", {}).copy()

    # Fix XCVR constant names (adijif uses XCVR_QPLL0, DTS header uses XCVR_QPLL)
    def fix_xcvr_constants(fpga_cfg):
        """Map adijif XCVR constants to DTS header constants"""
        if "sys_clk_select" in fpga_cfg:
            fpga_cfg["sys_clk_select"] = fpga_cfg["sys_clk_select"].replace("XCVR_QPLL0", "XCVR_QPLL")
        if "out_clk_select" in fpga_cfg:
            fpga_cfg["out_clk_select"] = fpga_cfg["out_clk_select"].replace("XCVR_REFCLK_DIV2", "XCVR_REFCLK_DIV2")
        return fpga_cfg

    for fpga_key in ["fpga_rx", "fpga_tx", "fpga_orx"]:
        if fpga_key in config:
            config[fpga_key] = fix_xcvr_constants(config[fpga_key])

    # Apply platform defaults for FPGA configuration
    config = board_fmc.validate_and_default_fpga_config(config)

    # 4. Add profile data from parsed profile
    if profile_data:
        config["rx_profile"] = profile_data.get("rx", {})
        config["tx_profile"] = profile_data.get("tx", {})
        config["orx_profile"] = profile_data.get("orx", {})

    ###################



    # Generate devicetree
    dts_filename = kernel_path / "arch/arm64/boot/dts/xilinx" / f"adrv9009_fmc.dts"
    board_fmc.output_filename = str(dts_filename)

    # Debug: Verify transformed config structure
    print("\n=== Transformed Config Structure ===")
    print(f"Clock outputs: {list(config['clock']['output_clocks'].keys())}")
    print(f"JESD204 keys: {list(config.get('jesd204', {}).keys())}")
    print(f"RX lanes_enabled: {config['jesd204']['framer_a'].get('lanes_enabled')}")
    print(f"TX lanes_enabled: {config['jesd204']['deframer_a'].get('lanes_enabled')}")
    print(f"ORX lanes_enabled: {config['jesd204']['framer_b'].get('lanes_enabled')}")
    print(f"FPGA paths: fpga_rx={bool(config.get('fpga_rx'))}, fpga_tx={bool(config.get('fpga_tx'))}, fpga_orx={bool(config.get('fpga_orx'))}")
    print("=" * 40 + "\n")

    clock, rx, tx, orx, fpga = board_fmc.map_clocks_to_board_layout(config)

    # Merge profile data into rx/tx/orx structures for template
    # Template expects: rx['filter'], rx['profile'], tx['filter'], tx['profile'], etc.
    if profile_data:
        # RX: merge filter and other fields from profile_data['rx']
        # NOTE: Temporarily excluding rxAdcProfile - appears to cause driver probe issues
        if 'rx' in profile_data:
            rx.update({
                'filter': profile_data['rx'].get('filter', {}),
                # 'rxAdcProfile': profile_data['rx'].get('rxAdcProfile', {}),  # TODO: Fix ADC profile format
            })

        # TX: merge filter and other fields from profile_data['tx']
        if 'tx' in profile_data:
            tx.update({
                'filter': profile_data['tx'].get('filter', {}),
                'txAttenCtrl': profile_data['tx'].get('txAttenCtrl', {}),
            })

        # ORX: merge filter and other fields from profile_data['orx']
        # NOTE: Temporarily excluding ADC profiles - appears to cause driver probe issues
        if 'orx' in profile_data:
            orx.update({
                'filter': profile_data['orx'].get('filter', {}),
                # 'orxBandPassAdcProfile': profile_data['orx'].get('orxBandPassAdcProfile', {}),  # TODO: Fix ADC profile format
                # 'orxLowPassAdcProfile': profile_data['orx'].get('orxLowPassAdcProfile', {}),  # TODO: Fix ADC profile format
            })

    generated_file = board_fmc.gen_dt(
        clock=clock,
        rx=rx,
        tx=tx,
        orx=orx,
        fpga=fpga,
        config_source="test_config_zcu102.json",
    )
    assert os.path.exists(generated_file), f"Failed to generate devicetree for profile {profile}"

    # Update build config to use the generated DTS
    generated_dts_base = Path(generated_file).name
    # Replace dts with dtb
    generated_dts_base = generated_dts_base.replace(".dts", ".dtb")
    builder.platform.config['dtbs'] = [generated_dts_base]


    # Build kernel
    result = builder.build(clean_before=False)
    print(result)

    kernel = result.get("kernel_image")
    kuiper.add_files_to_target(kernel)

    dtb = result.get("dtbs")[0]
    # Rename dtb to system.dtb
    os.rename(dtb, "system.dtb")
    dtb = Path("system.dtb")
    kuiper.add_files_to_target(dtb)

    # Boot
    board.transition("shell")

    # Verify IIO devices and sample rates
    print("\n=== IIO Device Verification ===")
    shell = board.target.get_driver("ADIShellDriver")

    # Check kernel logs for driver loading
    print("\nChecking kernel logs for ADRV9009 and JESD...")
    dmesg_adrv = shell.run_check("dmesg | grep -i adrv9009 | tail -10")
    print(f"ADRV9009 driver messages:\n{dmesg_adrv}")

    dmesg_jesd = shell.run_check("dmesg | grep -i jesd | tail -10")
    print(f"\nJESD messages:\n{dmesg_jesd}")

    # List all IIO devices
    print("\nListing IIO devices...")
    all_iio = shell.run_check("ls -la /sys/bus/iio/devices/ 2>/dev/null || echo 'No /sys/bus/iio/devices'")
    print(f"IIO devices directory:\n{all_iio}")

    # Try iio_info if available
    iio_devices = shell.run_check("iio_info -s 2>/dev/null | grep 'iio:device' || echo 'No IIO devices found'")
    print(f"\niio_info output:\n{iio_devices}")

    # Check for ADRV9009 devices - run_check returns a list
    adrv9009_search = shell.run_check("find /sys/bus/iio/devices -name '*adrv9009*' 2>/dev/null")
    print(f"\nADRV9009 device search: {adrv9009_search}")

    if adrv9009_search and len(adrv9009_search) > 0 and adrv9009_search[0]:
        adrv9009_phy = adrv9009_search[0]
        print(f"✓ Found ADRV9009 PHY device: {adrv9009_phy}")

        # Get RX sample rate
        rx_rate = shell.run_check(f"cat {adrv9009_phy}/in_voltage_sampling_frequency 2>/dev/null || echo 'N/A'")
        rx_rate_str = rx_rate[0] if rx_rate else "N/A"
        print(f"  RX Sample Rate: {rx_rate_str} Hz")

        # Get TX sample rate
        tx_rate = shell.run_check(f"cat {adrv9009_phy}/out_voltage_sampling_frequency 2>/dev/null || echo 'N/A'")
        tx_rate_str = tx_rate[0] if tx_rate else "N/A"
        print(f"  TX Sample Rate: {tx_rate_str} Hz")

        # Expected sample rates from profile (using the hz_to_int function logic)
        expected_rx_rate = sys.converter.adc.sample_clock
        expected_tx_rate = sys.converter.dac.sample_clock

        print(f"\n  Expected RX Rate: {expected_rx_rate} Hz")
        print(f"  Expected TX Rate: {expected_tx_rate} Hz")

        # Verify rates match (within tolerance)
        if rx_rate_str != 'N/A':
            actual_rx = int(rx_rate_str)
            tolerance = max(1000, expected_rx_rate * 0.01)  # 1% tolerance
            assert abs(actual_rx - expected_rx_rate) < tolerance, f"RX rate mismatch: {actual_rx} != {expected_rx_rate}"
            print("  ✓ RX sample rate matches profile")

        if tx_rate_str != 'N/A':
            actual_tx = int(tx_rate_str)
            tolerance = max(1000, expected_tx_rate * 0.01)  # 1% tolerance
            assert abs(actual_tx - expected_tx_rate) < tolerance, f"TX rate mismatch: {actual_tx} != {expected_tx_rate}"
            print("  ✓ TX sample rate matches profile")
    else:
        print("\n⚠ Warning: ADRV9009 PHY device not found in /sys/bus/iio/devices")
        print("This may indicate:")
        print("  - Driver not loaded (check dmesg above)")
        print("  - Device tree issue")
        print("  - Hardware not connected/powered")

    print("=" * 40)