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

def hz_to_int(hz_str):
    if isinstance(hz_str, (int, float)):
        return int(hz_str)
    hz_str = hz_str.lower().replace('hz', '')
    if 'm' in hz_str:
        return int(float(hz_str.replace('m', '')) * 1e6)
    if 'k' in hz_str:
        return int(float(hz_str.replace('k', '')) * 1e3)
    return int(float(hz_str))

def convert_jesd_params_to_int(jesd_dict):
    """Convert JESD parameters to integers if they are strings."""
    params_to_convert = ['L', 'M', 'F', 'S', 'K', 'Np', 'HD', 'CS']
    result = jesd_dict.copy()
    for param in params_to_convert:
        if param in result and isinstance(result[param], str):
            try:
                result[param] = int(result[param])
            except ValueError:
                pass
    return result

# Get list of profiles from test/adrv9009/profiles directory
profiles_dir = Path(__file__).parent / "profiles"
profile_files = sorted(list(profiles_dir.glob("*.txt")))
profile_names = [f.name for f in profile_files]

@pytest.mark.parametrize("profile", profile_names)
def test_profile(profile):
    profile_path = profiles_dir / profile
    profile_data = adrv9009.parse_profile(str(profile_path))
    assert profile_data is not None
    assert "rx" in profile_data
    assert "tx" in profile_data
    assert "orx" in profile_data
    assert "clocks" in profile_data

@pytest.mark.lg_feature(["adrv9009", "zcu102"])
@pytest.mark.parametrize("profile", profile_names)
def test_adrv9009_new(strategy, target, profile):
    # Skip profiles that are too large for now if needed
    # if "400" in profile:
    #     pytest.skip("Skipping 400MHz profile for speed")
    
    # 1. Initialize Builder
    config_path = Path(__file__).parent / "2023_R2.yaml"
    config = BuildConfig.from_yaml(config_path)
    platform_config = config.get_platform("zynqmp")
    platform = ZynqMPPlatform(platform_config)
    builder = LinuxBuilder(config, platform)
    
    # 2. Prepare Source
    builder.prepare_source()
    kernel_path = builder.repo.local_path
    
    # 3. Parse profile for settings needed for JIF
    profile_path = profiles_dir / profile
    profile_data = adrv9009.parse_profile(str(profile_path))
    assert profile_data, f"Failed to parse profile {profile}"
    
    # 4. Load base config from JSON
    config_dir = Path(__file__).parent / "configs"
    with open(config_dir / "zcu102_config.json", "r") as f:
        import json
        config = json.load(f)
    
    # Update base config with profile-specific clocks if needed
    # but for these profiles the base config is generally correct.
    
    # Add profile data
    config["rx_profile"] = profile_data.get("rx", {})
    config["tx_profile"] = profile_data.get("tx", {})
    config["orx_profile"] = profile_data.get("orx", {})
    config["clocks"] = profile_data.get("clocks", {})

    # Initialize board_fmc object
    board_fmc = adrv9009_fmc(platform="zcu102", kernel_path=kernel_path)
    dts_filename = kernel_path / "arch/arm64/boot/dts/xilinx" / f"adrv9009_fmc.dts"
    board_fmc.output_filename = str(dts_filename)

    # Map clocks and profiles
    clock, rx, tx, orx, fpga = board_fmc.map_clocks_to_board_layout(config)

    # Ensure profile data is nested correctly for original template
    # Original template expects: rx['profile'].get('fir_gain_db', -6)
    if profile_data:
        if 'rx' in profile_data:
            rx['profile'] = profile_data['rx']
            rx['filter'] = profile_data['rx'].get('filter', {})
            rx['rxAdcProfile'] = profile_data['rx'].get('rxAdcProfile', {})
        if 'tx' in profile_data:
            tx['profile'] = profile_data['tx']
            tx['filter'] = profile_data['tx'].get('filter', {})
            tx['lpbkAdcProfile'] = profile_data.get('lpbk', {}).get('lpbkAdcProfile', {})
        if 'orx' in profile_data:
            orx['profile'] = profile_data['orx']
            orx['filter'] = profile_data['orx'].get('filter', {})
            orx['orxBandPassAdcProfile'] = profile_data['orx'].get('orxBandPassAdcProfile', {})
            orx['orxLowPassAdcProfile'] = profile_data['orx'].get('orxLowPassAdcProfile', {})

    # Generate devicetree
    generated_file = board_fmc.gen_dt(
        clock=clock,
        rx=rx,
        tx=tx,
        orx=orx,
        fpga=fpga,
        config_source="test_config_zcu102.json",
    )
    
    # Update build config to use the generated DTS
    platform_config["dtbs"] = ["adrv9009_fmc.dtb"]
    
    # Build kernel and DTB
    builder.build()
    
    # stage files
    artifact_dir = Path("build/linux-2023_R2-arm64")
    dtbs = list((artifact_dir / "dts").glob("*.dtb"))
    assert dtbs, "No DTBs found in build artifacts"
    dtb = dtbs[0]
    os.rename(dtb, "system.dtb")
    dtb = Path("system.dtb")

    # Power off board before deploying new DTB so it boots with the new one
    strategy.transition("powered_off")

    kuiper = target.get_driver("KuiperDLDriver")
    kuiper.add_files_to_target(dtb)

    # Boot board
    strategy.transition("shell")
    
    # Verify IIO devices
    shell = target.get_driver("ADIShellDriver")

    # Print dmesg for diagnostics (adrv9009/jesd/spi related messages)
    dmesg = shell.run_check("dmesg | grep -i 'adrv9009\\|jesd\\|spi0' | tail -40; true")
    print("\n=== DMESG (adrv9009/jesd/spi0) ===")
    for line in dmesg:
        print(line)
    print("======================================")

    # List all IIO device names for context
    iio_names = shell.run_check("cat /sys/bus/iio/devices/*/name 2>/dev/null; true")
    print(f"IIO device names present: {iio_names}")

    # IIO devices appear as iio:deviceX in sysfs, not by chip name.
    # Append '; true' so the loop always exits 0 even when no device matches.
    adrv9009_search = shell.run_check(
        'for d in /sys/bus/iio/devices/iio:device*; do '
        'name=$(cat "$d/name" 2>/dev/null); '
        '[ "$name" = "adrv9009-phy" ] && echo "$d"; '
        'done; true'
    )

    if adrv9009_search and len(adrv9009_search) > 0 and adrv9009_search[0]:
        adrv9009_phy = adrv9009_search[0].strip()
        print(f"✓ Found ADRV9009 PHY device: {adrv9009_phy}")

        actual_rx = int(shell.run_check(f"cat {adrv9009_phy}/in_voltage0_sampling_frequency")[0])
        actual_tx = int(shell.run_check(f"cat {adrv9009_phy}/out_voltage_sampling_frequency")[0])

        expected_rx_rate = int(float(profile_data['rx'].get('rxOutputRate_kHz', 245760))) * 1000
        expected_tx_rate = int(float(profile_data['tx'].get('txInputRate_kHz', 245760))) * 1000

        tolerance = max(1000, expected_rx_rate * 0.01)
        assert abs(actual_rx - expected_rx_rate) < tolerance, \
            f"RX rate mismatch: actual={actual_rx}, expected={expected_rx_rate}"
        assert abs(actual_tx - expected_tx_rate) < tolerance, \
            f"TX rate mismatch: actual={actual_tx}, expected={expected_tx_rate}"
    else:
        assert False, f"ADRV9009 PHY device not found. IIO devices present: {iio_names}"
