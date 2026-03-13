from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
import re
from typing import Any

from adidt.xsa.pipeline import XsaPipeline

import iio
import pytest

HERE = Path(__file__).parent
DEFAULT_OUT_DIR = HERE / "output"
DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynqmp-zcu102-rev10-ad9081"
DEFAULT_VCXO_HZ = 122.88e6


def _resolve_config_from_adijif(
    vcxo_hz: float, solve: bool = False
) -> tuple[dict, dict]:
    """Build XSA pipeline config using pyadi-jif settings from ad9081_pcbz example.

    Reference:
    https://raw.githubusercontent.com/analogdevicesinc/pyadi-jif/refs/heads/main/examples/ad9081_pcbz_example.py
    """
    import adijif

    sys = adijif.system("ad9081", "hmc7044", "xilinx", vcxo=vcxo_hz)

    sys.fpga.setup_by_dev_kit_name("zcu102")

    cddc = 4
    fddc = 4
    cduc = 8
    fduc = 6

    sys.converter.clocking_option = "integrated_pll"
    sys.converter.adc.sample_clock = 4000000000 / cddc / fddc
    sys.converter.dac.sample_clock = 12000000000 / cduc / fduc

    sys.converter.adc.datapath.cddc_decimations = [cddc] * 4
    sys.converter.dac.datapath.cduc_interpolation = cduc
    sys.converter.adc.datapath.fddc_decimations = [fddc] * 8
    sys.converter.dac.datapath.fduc_interpolation = fduc
    sys.converter.adc.datapath.fddc_enabled = [True] * 8
    sys.converter.dac.datapath.fduc_enabled = [True] * 8

    mode_rx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.adc,
        M=8,
        L=4,
        # S=1,
        Np=16,
        jesd_class="jesd204b",
    )
    mode_tx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.dac,
        M=8,
        L=4,
        # S=1,
        Np=16,
        jesd_class="jesd204b",
    )
    if not mode_rx or not mode_tx:
        raise RuntimeError("No matching AD9081 JESD modes found via adijif")

    sys.converter.adc.set_quick_configuration_mode(
        mode_rx[0]["mode"], mode_rx[0]["jesd_class"]
    )
    sys.converter.dac.set_quick_configuration_mode(
        mode_tx[0]["mode"], mode_tx[0]["jesd_class"]
    )

    rx_settings = mode_rx[0]["settings"]
    tx_settings = mode_tx[0]["settings"]

    # Keep clock labels aligned with current AD9081 NodeBuilder path.
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
            "rx_device_clk_label": "hmc7044",
            "tx_device_clk_label": "hmc7044",
            "hmc7044_rx_channel": 10,
            "hmc7044_tx_channel": 6,
        },
    }

    summary: dict[str, Any] = {
        "vcxo_hz": vcxo_hz,
        # "sample_rate_hz": sample_rate_hz,
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
    rx_conf = conf.get("jesd_AD9081_RX", {})
    tx_conf = conf.get("jesd_AD9081_TX", {})
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


def _shell_out(shell, cmd: str) -> str:
    res = shell.run(cmd)
    out = res[0] if isinstance(res, tuple) else res
    if isinstance(out, list):
        return "\n".join(out)
    return str(out)


@pytest.fixture(scope="module")
def board(strategy):
    # with capsys.disabled():
    strategy.transition("powered_off")
    # strategy.transition("shell")
    # strategy.target["ADIShellDriver"].get_ip_addresses()

    yield strategy
    # with capsys.disabled():
    # strategy.transition("soft_off")


@pytest.mark.lg_feature(["ad9081", "zcu102"])
def test_ad9081_zcu102_xsa_hw(board):

    here = Path(__file__).parent
    out_dir = here / "output"
    xsa_path = here / "system_top.xsa"

    if not xsa_path.exists():
        raise SystemExit(f"XSA not found: {xsa_path}")

    cfg, _summary = _resolve_config_from_adijif(DEFAULT_VCXO_HZ, solve=True)

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
    dmesg_log = out_dir / "dmesg_ad9081_xsa_clean.log"
    dmesg_err_log = out_dir / "dmesg_ad9081_xsa_clean_err.log"
    dmesg_txt = _shell_out(shell, "dmesg")
    dmesg_log.write_text(dmesg_txt)
    dmesg_err = _shell_out(shell, "dmesg --level=err,warn")
    dmesg_err_log.write_text(dmesg_err)
    print(f"Saved dmesg logs: {dmesg_log} and {dmesg_err_log}")

    for cmd in [
        "ls /sys/bus/spi/devices",
        "lsmod | grep -E 'ad9081|hmc7044|jesd204|axi_'",
        "jesd_status || true",
        "dmesg | grep -Ei 'ad9081|hmc7044|jesd204|spi|axi-ad9081|probe|failed|error' | tail -n 200",
    ]:
        print(f"$ {cmd}")
        print(_shell_out(shell, cmd))

    addresses = shell.get_ip_addresses()
    ip_address = addresses[0]
    ip_address = str(ip_address.ip)
    print(f"Using IP address for IIO context: {ip_address}")
    if "/" in ip_address:
        ip_address = ip_address.split("/")[0]
    ctx = iio.Context(f"ip:{ip_address}")
    assert ctx is not None, "Failed to create IIO context"

    found_devices = [d.name for d in ctx.devices]
    assert "hmc7044" in found_devices, (
        f"Expected IIO clock device 'hmc7044' not found. "
        f"Available devices: {found_devices}"
    )
    assert any(
        n in found_devices for n in ("axi-ad9081-rx-hpc", "ad_ip_jesd204_tpl_adc")
    ), (
        "Expected AD9081 RX frontend IIO device not found "
        f"(accepted: axi-ad9081-rx-hpc or ad_ip_jesd204_tpl_adc). "
        f"Available devices: {found_devices}"
    )
    assert any(
        n in found_devices for n in ("axi-ad9081-tx-hpc", "ad_ip_jesd204_tpl_dac")
    ), (
        "Expected AD9081 TX frontend IIO device not found "
        f"(accepted: axi-ad9081-tx-hpc or ad_ip_jesd204_tpl_dac). "
        f"Available devices: {found_devices}"
    )

    assert (
        "AD9081 Rev." in dmesg_txt or "probed ADC AD9081" in dmesg_txt
    ), "AD9081 probe signature was not found in kernel dmesg output"

    jesd_status_txt = _shell_out(shell, "jesd_status || true")
    print("$ jesd_status")
    print(jesd_status_txt)
    assert "jesd_status: not found" not in jesd_status_txt, (
        "jesd_status tool is missing on target image"
    )
    assert re.search(r"\bDATA\b", jesd_status_txt), (
        "jesd_status did not report DATA mode. "
        f"Output:\n{jesd_status_txt}"
    )
