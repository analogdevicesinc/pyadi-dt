import pytest
from pathlib import Path
from pprint import pprint
import shutil

from adibuild import LinuxBuilder, BuildConfig
from adibuild.platforms import MicroBlazePlatform

import adijif
from adidt.boards.ad9084_fmc import ad9084_fmc


# Get list of profiles from test/ad9084/profiles/vcu118 directory
profiles_dir = Path(__file__).parent / "profiles" / "vcu118"
profile_files = sorted(list(profiles_dir.glob("*.json")))
profile_names = [f.name for f in profile_files]

VCXO_HZ = 125_000_000  # HMC7044 VCXO on AD9084-FMCA-EBZ


def _build_jif_config(profile_path: Path) -> dict:
    """Parse an Apollo profile JSON with adijif and return the solver config.

    Sets up:
      - AD9084 RX converter (direct clocking via ADF4382)
      - HMC7044 clock chip (VCXO = 125 MHz)
      - ADF4382 inline PLL (device clock)
      - ADF4030 sysref PLL
      - Xilinx VCU118 FPGA target
    """
    sys = adijif.system("ad9084_rx", "hmc7044", "xilinx", VCXO_HZ, solver="CPLEX")
    sys.fpga.setup_by_dev_kit_name("vcu118")
    sys.converter.clocking_option = "direct"
    sys.add_pll_inline("adf4382", VCXO_HZ, sys.converter)
    sys.add_pll_sysref("adf4030", VCXO_HZ, sys.converter, sys.fpga)
    sys.clock.minimize_feedback_dividers = False

    # Apply Apollo profile (bypass version check for pre-release profiles)
    sys.converter.apply_profile_settings(str(profile_path), bypass_version_check=True)

    cfg = sys.solve()
    return cfg, sys.converter


def _gen_dt(kernel_path: Path, profile_name: str, cfg: dict, converter) -> Path:
    """Generate a VCU118 DTS for the given profile using adijif config.

    Returns the path to the generated DTS file.
    """
    jesd = cfg["jesd_AD9084_RX"]
    fpga = cfg["fpga_AD9084_RX"]
    sysref_clks = cfg["clock_ext_pll_sysref_adf4030"]["output_clocks"]

    bit_clock_hz = jesd["bit_clock"]
    # JESD204C 64B66B: link_clk = bit_clock / 66
    link_clk_hz = bit_clock_hz / 66

    sysref_hz = list(sysref_clks.values())[0]["rate"]

    board_fmc = ad9084_fmc(platform="vcu118", kernel_path=str(kernel_path))

    dts_name = f"vcu118_ad9084_{profile_name}"
    dts_path = kernel_path / "arch" / "microblaze" / "boot" / "dts" / f"{dts_name}.dts"
    board_fmc.output_filename = str(dts_path)

    board_fmc.gen_dt(
        rx_lanerate_khz=int(bit_clock_hz / 1000),
        rx_link_clk=int(link_clk_hz),
        tx_lanerate_khz=int(bit_clock_hz / 1000),
        tx_link_clk=int(link_clk_hz),
        sysref_hz=int(sysref_hz),
        jesd_m=int(jesd["M"]),
        jesd_l=int(jesd["L"]),
        jesd_s=int(jesd["S"]),
        jesd_np=int(jesd["Np"]),
        jesd_f=int(jesd["F"]),
        device_clock_hz=int(converter.converter_clock),
        profile_name=profile_name,
        config_source=f"{profile_name}.json",
    )

    return dts_path, dts_name


@pytest.mark.lg_feature(["ad9084", "vcu118"])
@pytest.mark.parametrize("profile", profile_names)
def test_ad9084_new(strategy, target, profile):
    profile_stem = Path(profile).stem

    # 1. Initialize Builder
    config_path = Path(__file__).parent / "2023_R2.yaml"
    build_config = BuildConfig.from_yaml(config_path)
    platform_config = build_config.get_platform("microblaze")
    platform = MicroBlazePlatform(platform_config)
    builder = LinuxBuilder(build_config, platform)

    # 2. Prepare kernel source (clone/update repo)
    builder.prepare_source()
    kernel_path = builder.repo.local_path

    # 3. Parse profile with adijif → generate clock/JESD config
    profile_path = profiles_dir / profile
    cfg, converter = _build_jif_config(profile_path)

    print(f"\n=== adijif config for {profile_stem} ===")
    pprint(cfg)

    jesd = cfg["jesd_AD9084_RX"]
    print(
        f"JESD204C: M={jesd['M']} L={jesd['L']} S={jesd['S']} "
        f"Np={jesd['Np']} lane_rate={jesd['bit_clock']/1e9:.4f} Gbps"
    )

    # 4. Generate devicetree
    dts_path, dts_name = _gen_dt(kernel_path, profile_stem, cfg, converter)
    print(f"Generated DTS: {dts_path}")
    assert dts_path.exists(), f"DTS file not generated: {dts_path}"

    # 4.1 Copy profile .bin to firmware directory
    firmware_dir = kernel_path / "firmware"
    profile_bin_path = firmware_dir / f"{profile_stem}.bin"
    shutil.copy(profile_path, profile_bin_path)
    print(f"Copied profile to: {profile_bin_path}")

    # 4.2 Update defconfig to include the new profile
    # Get defconfig path from platform config
    defconfig_filename = platform_config["defconfig"]
    defconfig_filename = Path(defconfig_filename)
    defconfig_path = kernel_path / "arch" / "microblaze" / "configs" / defconfig_filename
    print(f"Updating defconfig: {defconfig_path}")
    with open(defconfig_path, "r") as f:
        lines = f.readlines()
    with open(defconfig_path, "w") as f:
        for line in lines:
            if line.startswith("CONFIG_FIRMWARE_FILES="):
                if profile_stem not in line:
                    line = line.strip() + f" {profile_stem}.bin"
            f.write(line)
    print(f"Updated defconfig: {defconfig_path}")

    # 5. Update build to use the profile-specific simpleImage target
    platform_config["simpleimage_targets"] = [f"simpleImage.{dts_name}"]

    # 6. Configure and build kernel + embedded DTB (simpleImage)
    builder.configure()
    images = builder.build_kernel()
    pprint(images)

    # 7. Deploy via JTAG
    xilinx_device_jtag = target.get_resource("XilinxDeviceJTAG")
    xilinx_device_jtag.kernel_path = str(images[0])
    if not xilinx_device_jtag.kernel_path.endswith(".strip"):
        xilinx_device_jtag.kernel_path += ".strip"

    print(f"Deploying: {xilinx_device_jtag.kernel_path}")

    # Power off → boot with new image
    strategy.transition("powered_off")
    strategy.transition("shell")

    # 8. Verify IIO devices
    shell = target.get_driver("ADIShellDriver")
    dmesg_full = shell.run_check("dmesg")

    # Diagnostics: dmesg
    dmesg = shell.run_check("dmesg | grep -i 'ad9084\\|jesd\\|spi' | tail -40; true")
    print("\n=== DMESG (ad9084/jesd/spi) ===")
    for line in dmesg:
        print(line)
    print("================================")

    # List all IIO device names
    iio_names = shell.run_check("cat /sys/bus/iio/devices/*/name 2>/dev/null; true")
    print(f"IIO device names present: {iio_names}")

    # Find the AD9084 RX IIO device
    ad9084_search = shell.run_check(
        'for d in /sys/bus/iio/devices/iio:device*; do '
        'name=$(cat "$d/name" 2>/dev/null); '
        '[ "$name" = "axi-ad9084-rx-hpc" ] && echo "$d"; '
        'done; true'
    )

    if ad9084_search and len(ad9084_search) > 0 and ad9084_search[0]:
        ad9084_phy = ad9084_search[0].strip()
        print(f"Found AD9084 RX device: {ad9084_phy}")
    else:
        assert False, f"AD9084 RX device not found. IIO devices present: {iio_names}\n{dmesg_full}"
