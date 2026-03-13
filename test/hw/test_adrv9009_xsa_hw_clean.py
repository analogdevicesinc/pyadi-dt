from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from adidt.xsa.pipeline import XsaPipeline

import iio
import pytest

HERE = Path(__file__).parent
DEFAULT_OUT_DIR = HERE / "output"
DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynqmp-zcu102-rev10-adrv9009"
DEFAULT_VCXO_HZ = 122.88e6
DEFAULT_SAMPLE_RATE_HZ = 245.76e6


def _resolve_config_from_adijif(
    vcxo_hz: float, sample_rate_hz: float, solve: bool = False
) -> tuple[dict, dict]:
    """Build XSA pipeline config using pyadi-jif settings from adrv9009_pcbz example.

    Reference:
    https://raw.githubusercontent.com/analogdevicesinc/pyadi-jif/refs/heads/main/examples/adrv9009_pcbz_example.py
    """
    import adijif

    sys = adijif.system("adrv9009", "ad9528", "xilinx", vcxo=vcxo_hz)

    sys.fpga.setup_by_dev_kit_name("zcu102")

    mode_rx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.adc,
        M=4,
        L=2,
        S=1,
        Np=16,
    )
    mode_tx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.dac,
        M=4,
        L=4,
        S=1,
        Np=16,
    )
    if not mode_rx or not mode_tx:
        raise RuntimeError("No matching ADRV9009 JESD modes found via adijif")

    sys.converter.adc.set_quick_configuration_mode(
        mode_rx[0]["mode"], mode_rx[0]["jesd_class"]
    )
    sys.converter.dac.set_quick_configuration_mode(
        mode_tx[0]["mode"], mode_tx[0]["jesd_class"]
    )

    sys.converter.adc.decimation = 8
    sys.converter.adc.sample_clock = sample_rate_hz
    sys.converter.dac.interpolation = 8
    sys.converter.dac.sample_clock = sample_rate_hz

    rx_settings = mode_rx[0]["settings"]
    tx_settings = mode_tx[0]["settings"]

    # Keep clock labels aligned with current ADRV9009 NodeBuilder path.
    cfg: dict[str, Any] = {
        "jesd": {
            "rx": {
                "F": int(rx_settings["F"]),
                "K": int(rx_settings["K"]),
                "M": int(rx_settings["M"]),
                "L": int(rx_settings["L"]),
                "Np": int(rx_settings["Np"]),
                "S": int(rx_settings["S"]),
            },
            "tx": {
                "F": int(tx_settings["F"]),
                "K": int(tx_settings["K"]),
                "M": int(tx_settings["M"]),
                "L": int(tx_settings["L"]),
                "Np": int(tx_settings["Np"]),
                "S": int(tx_settings["S"]),
            },
        },
        "clock": {
            "rx_device_clk_label": "clkgen",
            "tx_device_clk_label": "clkgen",
            "hmc7044_rx_channel": 0,
            "hmc7044_tx_channel": 0,
        },
    }

    summary: dict[str, Any] = {
        "vcxo_hz": vcxo_hz,
        "sample_rate_hz": sample_rate_hz,
        "clock_m1": 3,
        "clock_use_vcxo_doubler": True,
        "rx_mode": mode_rx[0]["mode"],
        "tx_mode": mode_tx[0]["mode"],
        "rx_jesd_class": mode_rx[0]["jesd_class"],
        "tx_jesd_class": mode_tx[0]["jesd_class"],
        "solver_used": None,
        "solver_succeeded": False,
        "solver_attempted": solve,
        "clock_output_clocks": None,
        "solve_error": None,
    }

    conf = sys.solve()
    summary["solver_used"] = "default"
    summary["solver_succeeded"] = True
    summary["clock_output_clocks"] = conf.get("clock", {}).get("output_clocks")
    rx_conf = conf.get("jesd_ADRV9009_RX", {})
    tx_conf = conf.get("jesd_ADRV9009_TX", {})
    for key in ("F", "K", "M", "L", "Np", "S"):
        if key in rx_conf:
            cfg["jesd"]["rx"][key] = int(rx_conf[key])
        if key in tx_conf:
            cfg["jesd"]["tx"][key] = int(tx_conf[key])

    return cfg, summary


def _compile_dts_to_dtb(dts_path: Path, dtb_path: Path):
    compile_input = dts_path
    text = dts_path.read_text()

    if "#include" in text:
        if shutil.which("cpp") is None:
            raise RuntimeError(
                "cpp not found on PATH (required for #include preprocessing)"
            )
        preprocessed = dtb_path.parent / f"{dts_path.stem}.pp.dts"
        include_dirs = [dts_path.parent, dts_path.parent / "base"]
        cmd = ["cpp", "-P", "-nostdinc", "-undef", "-x", "assembler-with-cpp"]
        for inc in include_dirs:
            if inc.exists():
                cmd.extend(["-I", str(inc)])
        cmd.extend([str(dts_path), str(preprocessed)])
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise RuntimeError(f"cpp failed:\n{res.stderr}")
        compile_input = preprocessed

    res = subprocess.run(
        ["dtc", "-I", "dts", "-O", "dtb", "-o", str(dtb_path), str(compile_input)],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(f"dtc failed:\n{res.stderr}")


@pytest.fixture(scope="module")
def board(strategy):
    # with capsys.disabled():
    strategy.transition("powered_off")
    # strategy.transition("shell")
    # strategy.target["ADIShellDriver"].get_ip_addresses()

    yield strategy
    # with capsys.disabled():
    # strategy.transition("soft_off")


@pytest.mark.lg_feature(["adrv9009", "zcu102"])
def test_adrv9009_zcu102_xsa_hw(board):

    here = Path(__file__).parent
    out_dir = here / "output"
    xsa_path = here / "ref_data" / "system_top_adrv9009_zcu102.xsa"

    if not xsa_path.exists():
        raise SystemExit(f"XSA not found: {xsa_path}")

    cfg, _summary = _resolve_config_from_adijif(
        DEFAULT_VCXO_HZ, DEFAULT_SAMPLE_RATE_HZ, solve=False
    )

    result = XsaPipeline().run(
        xsa_path=xsa_path,
        cfg=cfg,
        output_dir=out_dir,
        sdtgen_timeout=300,
    )

    dtb = out_dir / "system.dtb"
    _compile_dts_to_dtb(result["merged"], dtb)

    kuiper = board.target.get_driver("KuiperDLDriver")
    kuiper.get_boot_files_from_release()
    kuiper.add_files_to_target(dtb)

    # Boot
    board.transition("shell")

    # Check
    shell = board.target.get_driver("ADIShellDriver")
    addresses = shell.get_ip_addresses()
    ip_address = addresses[0]
    ip_address = str(ip_address.ip)
    print(f"Using IP address for IIO context: {ip_address}")
    if "/" in ip_address:
        ip_address = ip_address.split("/")[0]
    ctx = iio.Context(f"ip:{ip_address}")
    assert ctx is not None, "Failed to create IIO context"

    expected_devices = ["axi-adrv9009-rx-hpc", "adrv9009-phy", "ad9528-1"]
    found_devices = [d.name for d in ctx.devices]

    for device_name in expected_devices:
        assert device_name in found_devices, (
            f"Expected IIO device '{device_name}' not found on ZCU102. "
            f"Available devices: {found_devices}"
        )
        device = [d for d in ctx.devices if d.name == device_name][0]
        num_channels = len(device.channels)
        print(f"Found IIO device: {device_name} ({num_channels} channels)")
