import os
import pytest
import iio
from pathlib import Path

from adibuild import LinuxBuilder, BuildConfig
from adibuild.platforms import ZynqMPPlatform

from adidt.boards.ad9081_fmc import ad9081_fmc
import adijif

SAMPLE_RATES = [100, 125, 150, 175, 200, 225, 245, 260, 280, 300]
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


def generate_ad9081_config(
    sample_rate_msps: int, platform: str = "zcu102", jesd=None
) -> dict:
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

    sys = adijif.system("ad9081", "hmc7044", "xilinx", vcxo, solver="CPLEX")
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

    # Datapath Configuration - Dynamic decimation/interpolation based on sample rate and JESD mode
    # Mode 10.0 (M=8, L=4) constraints: 1.45 GHz < ADC_CLK < 4 GHz, bit_clock > 1.5 GHz
    # Mode 18.0 (M=4, L=8) constraints: 1.45 GHz < ADC_CLK < 4 GHz, bit_clock > 1.5 GHz
    # Mode 9 (M=8, L=4) DAC constraints: 2.9 GHz < DAC_CLK < 12 GHz
    # Mode 17 (M=4, L=8) DAC constraints: 2.9 GHz < DAC_CLK < 12 GHz

    # For M=4, L=8 we need higher decimation to meet bit clock minimum (1.5 GHz)
    # bit_clock = (sample_rate * decimation * M) / (L * 1.25)
    # For 100 MSPS, M=4, L=8: need bit_clock >= 1.5 GHz
    # (100M * decimation * 4) / (8 * 1.25) = 1.5G -> decimation >= 30x

    if jesd["M"] == 4:
        # M=4, L=8 configuration - needs higher decimation for bit clock constraint
        if sample_rate_msps <= 125:
            # 100-125 MSPS: Use 32x decimation to meet 1.5 GHz bit clock minimum
            adc_cddc = 4
            adc_fddc = 8
            adc_total_dec = 32
        elif sample_rate_msps <= 250:
            # 150-250 MSPS: Use 16x decimation
            adc_cddc = 4
            adc_fddc = 4
            adc_total_dec = 16
        else:
            # 260-300 MSPS: Use 12x decimation
            adc_cddc = 3
            adc_fddc = 4
            adc_total_dec = 12
    else:
        # M=8, L=4 configuration - lower decimation OK
        if sample_rate_msps <= 250:
            # 100-250 MSPS: Use 16x decimation (1.6-4.0 GHz)
            adc_cddc = 4
            adc_fddc = 4
            adc_total_dec = 16
        else:
            # 260-300 MSPS: Use 12x decimation (3.12-3.6 GHz)
            adc_cddc = 3
            adc_fddc = 4
            adc_total_dec = 12

    # DAC interpolation - CDUC must be 1, 2, 4, 6, 8, or 12
    # Must maintain integer ratio with ADC decimation (DAC_interp / ADC_dec must be integer)
    if adc_total_dec == 12:
        # For 12x ADC decimation, use 36x DAC interpolation (3:1 ratio)
        dac_cduc = 6
        dac_fduc = 6
        dac_total_interp = 36
    else:
        # For 16x ADC decimation, use 32x DAC interpolation (2:1 ratio)
        dac_cduc = 4
        dac_fduc = 8
        dac_total_interp = 32

    # Apply ADC decimation
    sys.converter.adc.datapath.fddc_enabled = [True] * 4 + [False] * 4
    sys.converter.adc.datapath.fddc_decimations = [adc_fddc] * 8
    sys.converter.adc.datapath.cddc_decimations = [adc_cddc] * 4

    # Apply DAC interpolation
    sys.converter.dac.datapath.cduc_interpolation = dac_cduc
    sys.converter.dac.datapath.fduc_interpolation = dac_fduc
    sys.converter.dac.datapath.fduc_enabled = [True] * 4 + [False] * 4

    # Validate and print clock rates
    adc_clock_ghz = sample_rate_msps * adc_total_dec / 1000
    dac_clock_ghz = sample_rate_msps * dac_total_interp / 1000

    # ADC Mode 10.0 requires: 1.45 GHz < ADC_CLK < 4 GHz
    assert 1.45 <= adc_clock_ghz <= 4.0, (
        f"ADC clock {adc_clock_ghz:.2f} GHz out of range [1.45, 4.0] GHz "
        f"for {sample_rate_msps} MSPS with {adc_total_dec}x decimation"
    )

    # DAC Mode 9 requires: 2.9 GHz < DAC_CLK < 12 GHz
    assert 2.9 <= dac_clock_ghz <= 12.0, (
        f"DAC clock {dac_clock_ghz:.2f} GHz out of range [2.9, 12.0] GHz "
        f"for {sample_rate_msps} MSPS with {dac_total_interp}x interpolation"
    )

    # Verify integer ratio between DAC and ADC clocks
    clock_ratio = dac_total_interp / adc_total_dec
    assert clock_ratio == int(clock_ratio), (
        f"Clock ratio must be integer: DAC {dac_total_interp}x / ADC {adc_total_dec}x = {clock_ratio}"
    )

    print(f"ADC: {sample_rate_msps} MSPS × {adc_total_dec} = {adc_clock_ghz:.2f} GHz ✓")
    print(
        f"DAC: {sample_rate_msps} MSPS × {dac_total_interp} = {dac_clock_ghz:.2f} GHz ✓"
    )
    print(f"Clock ratio: {dac_total_interp}/{adc_total_dec} = {int(clock_ratio)}:1 ✓")

    # JESD Configuration - Use quick_configuration_mode to lock parameters
    # M=8, L=4 -> ADC Mode 10.0, DAC Mode 9
    # M=4, L=8 -> ADC Mode 18.0, DAC Mode 17
    if jesd["M"] == 8 and jesd["L"] == 4:
        adc_mode = "10.0"
        dac_mode = "9"
    elif jesd["M"] == 4 and jesd["L"] == 8:
        adc_mode = "18.0"
        dac_mode = "17"
    else:
        raise ValueError(
            f"Unsupported JESD configuration: M={jesd['M']}, L={jesd['L']}"
        )

    sys.converter.adc.set_quick_configuration_mode(adc_mode, "jesd204b")
    sys.converter.dac.set_quick_configuration_mode(dac_mode, "jesd204b")

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


@pytest.mark.lg_feature(["ad9081", "zcu102"])
@pytest.mark.parametrize("JESD", [{"M": 8, "L": 4}, {"M": 4, "L": 8}])
@pytest.mark.parametrize("sample_rate_msps", SAMPLE_RATES)
def test_ad9081_new(board, sample_rate_msps, JESD):
    # Skip M=4, L=8 for low sample rates - bit clock cannot meet 1.5 GHz minimum
    if JESD["M"] == 4 and sample_rate_msps < 150:
        pytest.skip(
            f"M=4, L=8 not supported at {sample_rate_msps} MSPS (bit clock too low)"
        )

    kuiper = board.target.get_driver("KuiperDLDriver")
    print(JESD)
    if JESD["M"] == 4:
        BB = "release:zynqmp-zcu102-rev10-ad9081/m4_l8/BOOT.BIN"
    else:
        BB = "release:zynqmp-zcu102-rev10-ad9081/m4_l8/BOOT.BIN"
    # zynqmp-zcu102-rev10-ad9081/m8_l4/BOOT.BIN
    # if M=
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
    config = generate_ad9081_config(sample_rate_msps, platform="zcu102", jesd=JESD)

    # Step 2: Generate DTS
    print("Generating DTS file...")
    kernel_path = builder.repo.local_path
    dt_board = ad9081_fmc(platform="zcu102", kernel_path=kernel_path)
    config = dt_board.validate_and_default_fpga_config(config)

    dts_filename = (
        kernel_path
        / "arch/arm64/boot/dts/xilinx"
        / f"ad9081_{sample_rate_msps}msps.dts"
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
    kuiper.add_files_to_target(dtb)

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

    expected_devices = ["axi-ad9081-rx-hpc", "axi-ad9081-tx-hpc"]
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
