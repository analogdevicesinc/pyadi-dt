import os
import pytest
import iio
from pathlib import Path

from adibuild import LinuxBuilder, BuildConfig
from adibuild.platforms import ZynqMPPlatform

from adidt.boards.daq2 import daq2
import adijif

SAMPLE_RATES = [500, 1000]
# SAMPLE_RATES = [100]


@pytest.fixture(scope="module")
def board(strategy):
    # with capsys.disabled():
    strategy.transition("powered_off")
    # strategy.transition("shell")
    # strategy.target["ADIShellDriver"].get_ip_addresses()

    yield strategy
    # with capsys.disabled():
    # strategy.transition("soft_off")


def generate_fmcdaq2_config(sample_rate_msps: int, platform: str = "zcu102", jesd=None):
    """Generate fmcdaq2 configuration for given sample rate.

    Uses pyadi-jif to generate a complete configuration with JESD204 parameters.

    Args:
        sample_rate_msps: Sample rate in MSPS (100-300)
        platform: Platform name ('zcu102', 'zc706', etc.). Default: 'zcu102'
        jesd: JESD configuration dict with 'L' and 'M' keys

    Returns:
        adijif system object (not yet solved)
    """
    vcxo = 125_000_000  # 125 MHz reference

    sys = adijif.system(
        ["ad9680", "ad9144"], "ad9523_1", "xilinx", vcxo, solver="CPLEX"
    )
    sys.fpga.setup_by_dev_kit_name(platform)

    # Clocking constraints
    sys.fpga.ref_clock_constraint = "Unconstrained"
    # Let solver determine optimal sys_clk_select and out_clk_select

    # Sample Rates
    sample_clock = sample_rate_msps * 1_000_000
    sys.converter[0].sample_clock = sample_clock
    sys.converter[1].sample_clock = sample_clock

    # JESD Configuration - Use quick_configuration_mode to lock parameters
    rx_mode = adijif.utils.get_jesd_mode_from_params(
        sys.converter[0], L=jesd["L"], M=jesd["M"], Np=16, F=1
    )
    tx_mode = adijif.utils.get_jesd_mode_from_params(
        sys.converter[1], L=jesd["L"], M=jesd["M"], Np=16, F=1
    )
    rx_mode = [mode for mode in rx_mode if "DL" not in mode["mode"]]
    tx_mode = [mode for mode in tx_mode if "DL" not in mode["mode"]]
    assert rx_mode and len(rx_mode) == 1
    assert tx_mode and len(tx_mode) == 1

    sys.converter[0].set_quick_configuration_mode(rx_mode[0]["mode"], "jesd204b")
    sys.converter[1].set_quick_configuration_mode(tx_mode[0]["mode"], "jesd204b")

    return sys


@pytest.mark.lg_feature(["fmcdaq2", "zcu102"])
@pytest.mark.parametrize("JESD", [{"M": 2, "L": 4}])
@pytest.mark.parametrize("sample_rate_msps", SAMPLE_RATES)
def test_fmcdaq2_new(board, sample_rate_msps, JESD):
    # Skip M=4, L=8 for low sample rates - bit clock cannot meet 1.5 GHz minimum
    if JESD["M"] == 4 and sample_rate_msps < 150:
        pytest.skip(
            f"M=4, L=8 not supported at {sample_rate_msps} MSPS (bit clock too low)"
        )

    kuiper = board.target.get_driver("KuiperDLDriver")
    print(JESD)
    BB = "release:zynqmp-zcu102-rev10-fmcdaq2/BOOT.BIN"
    kuiper.kuiper_resource.BOOTBIN_path = BB
    kuiper.get_boot_files_from_release()

    # Configure build system
    config_path = Path(__file__).parent / "2023_R2.yaml"
    config = BuildConfig.from_yaml(config_path)
    platform_config = config.get_platform("zynqmp")
    platform = ZynqMPPlatform(platform_config)
    builder = LinuxBuilder(config, platform)
    builder.prepare_source()

    # Build device tree
    # lane_rate_gbps = sample_rate_msps * 32 / 1000
    print(f"\n{'=' * 70}")
    print(f"Testing {sample_rate_msps} MSPS")
    print(f"{'=' * 70}")

    # Step 1: Generate configuration
    print("Generating configuration...")
    sys = generate_fmcdaq2_config(sample_rate_msps, platform="zcu102", jesd=JESD)
    config_adijif = sys.solve()

    # Step 2: Create config dictionary matching adidt.boards.daq2 expected structure
    # Note: daq2.py uses generic ADC/DAC names (not chip-specific AD9680/AD9144)
    print("Creating config structure...")

    # Map chip-specific clock names to generic ADC/DAC names expected by daq2.py
    output_clocks = {}
    clk_src = config_adijif["clock"]["output_clocks"]

    # Map AD9680 clocks to generic ADC names
    output_clocks["ADC_CLK"] = clk_src.get("AD9680_ref_clk", {})
    output_clocks["ADC_CLK_FMC"] = clk_src.get("zcu102_AD9680_ref_clk", {})
    output_clocks["ADC_SYSREF"] = clk_src.get("AD9680_sysref", {})
    output_clocks["CLKD_ADC_SYSREF"] = clk_src.get("AD9680_sysref", {})

    # Map AD9144 clocks to generic DAC names
    output_clocks["DAC_CLK"] = clk_src.get("AD9144_ref_clk", {})
    output_clocks["FMC_DAC_REF_CLK"] = clk_src.get("zcu102_AD9144_ref_clk", {})
    output_clocks["DAC_SYSREF"] = clk_src.get("AD9144_sysref", {})
    output_clocks["CLKD_DAC_SYSREF"] = clk_src.get("AD9144_sysref", {})

    config = {
        "clock": {
            "vco": config_adijif["clock"]["vco"],
            "vcxo": config_adijif["clock"]["vcxo"],
            "m1": config_adijif["clock"]["m1"],
            "output_clocks": output_clocks,
        },
        "converter_ADC": {
            "sample_clock": config_adijif["jesd_AD9680"]["sample_clock"],
            "decimation": config_adijif["converter_AD9680"]["decimation"],
        },
        "converter_DAC": {
            "sample_clock": config_adijif["jesd_AD9144"]["sample_clock"],
            "interpolation": config_adijif["converter_AD9144"]["interpolation"],
        },
        "jesd_ADC": {
            "jesd_class": config_adijif["jesd_AD9680"]["jesd_class"],
            "converter_clock": config_adijif["jesd_AD9680"]["converter_clock"],
            "sample_clock": config_adijif["jesd_AD9680"]["sample_clock"],
            "jesd_L": config_adijif["jesd_AD9680"]["L"],
            "jesd_M": config_adijif["jesd_AD9680"]["M"],
            "jesd_S": config_adijif["jesd_AD9680"]["S"],
            "jesd_HD": config_adijif["jesd_AD9680"].get("HD", 0),
            "jesd_F": config_adijif["jesd_AD9680"].get("F", 1),
        },
        "jesd_DAC": {
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

    # Step 3: Generate DTS
    print("Generating DTS file...")
    kernel_path = builder.repo.local_path
    dt_board = daq2(platform="zcu102", kernel_path=kernel_path)
    config = dt_board.validate_and_default_fpga_config(config)

    dts_filename = (
        kernel_path
        / "arch/arm64/boot/dts/xilinx"
        / f"fmcdaq2_{sample_rate_msps}msps.dts"
    )
    dt_board.output_filename = str(dts_filename)

    clock, adc, dac, fpga = dt_board.map_clocks_to_board_layout(config)
    generated_dts = dt_board.gen_dt(
        clock=clock,
        adc=adc,
        dac=dac,
        fpga=fpga,
        config_source=f"generated_{sample_rate_msps}msps",
    )
    assert os.path.exists(generated_dts), f"DTS file not generated: {generated_dts}"

    # Update build config to use the generated DTS
    generated_dts_base = Path(generated_dts).name
    # Replace dts with dtb
    generated_dts_base = generated_dts_base.replace(".dts", ".dtb")
    builder.platform.config["dtbs"] = [generated_dts_base]

    result = builder.build(clean_before=False)
    print(result)

    kernel = result.get("kernel_image")
    kuiper.add_files_to_target(kernel)

    dtb = result.get("dtbs")[0]
    # Rename dtb to system.dtb
    os.rename(dtb, "system.dtb")
    dtb = Path("system.dtb")
    # kuiper.add_files_to_target(dtb)

    board.transition("shell")

    shell = board.target.get_driver("ADIShellDriver")
    addresses = shell.get_ip_addresses()
    ip_address = addresses[0]
    ip_address = str(ip_address.ip)
    print(f"Using IP address for IIO context: {ip_address}")
    if "/" in ip_address:
        ip_address = ip_address.split("/")[0]
    ctx = iio.Context(f"ip:{ip_address}")
    assert ctx is not None, "Failed to create IIO context"

    # DAQ2 uses separate AD9680 (ADC) and AD9144 (DAC) chips.
    # Device names follow pattern: axi-<chip>-<connector>
    # Note: Unlike AD9081 (unified transceiver), DAQ2 does NOT use rx/tx suffixes
    expected_devices = ["axi-ad9680-hpc", "axi-ad9144-hpc"]
    found_devices = [d.name for d in ctx.devices]

    expected_sample_rate_hz = sample_rate_msps * 1_000_000

    for device_name in expected_devices:
        assert device_name in found_devices, (
            f"Expected IIO device '{device_name}' not found on ZCU102. "
            f"Available devices: {found_devices}"
        )
        device = [d for d in ctx.devices if d.name == device_name][0]
        num_channels = len(device.channels)
        print(f"Found IIO device: {device_name} ({num_channels} channels)")

        # Verify sample rate
        if device.attrs.get("sampling_frequency"):
            actual_sample_rate = int(device.attrs["sampling_frequency"].value)
            print(
                f"  Sample rate: {actual_sample_rate / 1e6:.1f} MSPS (expected: {sample_rate_msps} MSPS)"
            )

            # Allow 1% tolerance for sample rate verification
            tolerance = expected_sample_rate_hz * 0.01
            assert abs(actual_sample_rate - expected_sample_rate_hz) <= tolerance, (
                f"Sample rate mismatch for {device_name}: "
                f"expected {expected_sample_rate_hz} Hz ({sample_rate_msps} MSPS), "
                f"got {actual_sample_rate} Hz ({actual_sample_rate / 1e6:.1f} MSPS)"
            )
        else:
            print(f"  Warning: No sampling_frequency attribute found for {device_name}")
