from __future__ import annotations

import os
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
DEFAULT_KUIPER_PROJECT = "zynqmp-zcu102-rev10-ad9081"
DEFAULT_VCXO_HZ = 122.88e6
DEFAULT_BUILD_KERNEL = os.environ.get("ADI_XSA_BUILD_KERNEL", "1").lower() not in {
    "0",
    "false",
    "no",
}
_SYS_CLK_SELECT_MAP = {
    "XCVR_CPLL": 0,
    "XCVR_QPLL1": 2,
    "XCVR_QPLL0": 3,
}
_OUT_CLK_SELECT_MAP = {
    "XCVR_REFCLK": 4,
    "XCVR_REFCLK_DIV2": 4,
}


def _is_valid_xsa(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    try:
        with path.open("rb") as f:
            return f.read(4) == b"PK\x03\x04"
    except OSError:
        return False


def test_is_valid_xsa_detects_zip_signature(tmp_path: Path):
    good = tmp_path / "good.xsa"
    bad = tmp_path / "bad.xsa"
    good.write_bytes(b"PK\x03\x04rest")
    bad.write_bytes(b"\x1f\x8b\x08\x00rest")
    assert _is_valid_xsa(good)
    assert not _is_valid_xsa(bad)


def test_resolve_config_from_adijif_m4_l8_uses_250m_and_valid_clk_selects():
    pytest.importorskip("adijif")
    cfg, summary = _resolve_config_from_adijif(DEFAULT_VCXO_HZ, solve=True)

    assert cfg["ad9081"]["rx_sys_clk_select"] == 0
    assert cfg["ad9081"]["tx_sys_clk_select"] == 3
    clocks = summary.get("clock_output_clocks") or {}
    assert int(clocks["zcu102_adc_device_clk"]["rate"]) == 250_000_000
    assert int(clocks["zcu102_dac_device_clk"]["rate"]) == 250_000_000


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

    cddc = 2
    fddc = 1
    cduc = 8
    fduc = 1

    sys.converter.clocking_option = "integrated_pll"
    # Keep M4/L8 lane-rate at 10 Gbps (250 MHz link clock) for this bitstream.
    sys.converter.adc.sample_clock = 1_000_000_000
    sys.converter.dac.sample_clock = 1_000_000_000

    sys.converter.adc.datapath.cddc_decimations = [cddc] * 4
    sys.converter.dac.datapath.cduc_interpolation = cduc
    sys.converter.adc.datapath.fddc_decimations = [fddc] * 8
    sys.converter.dac.datapath.fduc_interpolation = fduc
    sys.converter.adc.datapath.fddc_enabled = [True] * 8
    sys.converter.dac.datapath.fduc_enabled = [True] * 8

    mode_rx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.adc,
        M=4,
        L=8,
        # S=1,
        Np=16,
        jesd_class="jesd204b",
    )
    mode_tx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.dac,
        M=4,
        L=8,
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
        "ad9081": {
            "rx_link_mode": int(float(mode_rx[0]["mode"])),
            "tx_link_mode": int(float(mode_tx[0]["mode"])),
            "adc_frequency_hz": int(sys.converter.adc.sample_clock * cddc * fddc),
            "dac_frequency_hz": int(sys.converter.dac.sample_clock * cduc * fduc),
            "rx_cddc_decimation": cddc,
            "rx_fddc_decimation": fddc,
            "tx_cduc_interpolation": cduc,
            "tx_fduc_interpolation": fduc,
            "rx_sys_clk_select": 0,
            "tx_sys_clk_select": 0,
            "rx_out_clk_select": 4,
            "tx_out_clk_select": 4,
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
    rx_fpga = conf.get("fpga_adc", {})
    tx_fpga = conf.get("fpga_dac", {})
    rx_sys_clk_select = int(
        _SYS_CLK_SELECT_MAP.get(str(rx_fpga.get("sys_clk_select", "")).upper(), 0)
    )
    tx_sys_clk_select = int(
        _SYS_CLK_SELECT_MAP.get(str(tx_fpga.get("sys_clk_select", "")).upper(), 0)
    )
    rx_out_clk_select = int(
        _OUT_CLK_SELECT_MAP.get(str(rx_fpga.get("out_clk_select", "")).upper(), 4)
    )
    tx_out_clk_select = int(
        _OUT_CLK_SELECT_MAP.get(str(tx_fpga.get("out_clk_select", "")).upper(), 4)
    )
    cfg["ad9081"]["rx_sys_clk_select"] = rx_sys_clk_select
    cfg["ad9081"]["tx_sys_clk_select"] = tx_sys_clk_select
    cfg["ad9081"]["rx_out_clk_select"] = rx_out_clk_select
    cfg["ad9081"]["tx_out_clk_select"] = tx_out_clk_select
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


@pytest.fixture(scope="module")
def built_kernel_image() -> Path | None:
    if not DEFAULT_BUILD_KERNEL:
        return None

    try:
        from adibuild import LinuxBuilder, BuildConfig
        from adibuild.platforms import ZynqMPPlatform
    except ModuleNotFoundError as ex:
        pytest.skip(f"pyadi-build dependency missing: {ex}")

    config_path = HERE.parent / "2023_R2.yaml"
    if not config_path.exists():
        pytest.skip(f"pyadi-build config not found: {config_path}")

    config = BuildConfig.from_yaml(config_path)
    platform_config = config.get_platform("zynqmp")
    platform = ZynqMPPlatform(platform_config)
    builder = LinuxBuilder(config, platform)
    builder.prepare_source()
    result = builder.build(clean_before=False)

    kernel = result.get("kernel_image")
    if not kernel:
        raise RuntimeError(f"pyadi-build returned no kernel image: {result}")

    kernel_path = Path(kernel)
    if not kernel_path.exists():
        raise RuntimeError(f"Built kernel image not found: {kernel_path}")

    return kernel_path


@pytest.mark.lg_feature(["ad9081", "zcu102"])
def test_ad9081_zcu102_xsa_hw(board, built_kernel_image):

    here = Path(__file__).parent
    out_dir = here / "output"
    xsa_path = here / "system_top_m4_l8.xsa"
    if not _is_valid_xsa(xsa_path):
        xsa_path = here / "system_top.xsa"

    if not _is_valid_xsa(xsa_path):
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
    if built_kernel_image is not None:
        kuiper.add_files_to_target(built_kernel_image)
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
        "cat /sys/kernel/debug/devices_deferred || true",
        "cat /sys/bus/platform/devices/84a90000.axi_jesd204_rx/status 2>/dev/null || true",
        "cat /sys/bus/platform/devices/84b90000.axi_jesd204_tx/status 2>/dev/null || true",
        "timeout 15 jesd_status 2>&1 || true",
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

    assert "AD9081 Rev." in dmesg_txt or "probed ADC AD9081" in dmesg_txt, (
        "AD9081 probe signature was not found in kernel dmesg output"
    )

    jesd_status_txt = _shell_out(shell, "timeout 15 jesd_status 2>&1 || true")
    print("$ jesd_status")
    print(jesd_status_txt)
    rx_status_txt = _shell_out(
        shell, "cat /sys/bus/platform/devices/84a90000.axi_jesd204_rx/status || true"
    )
    tx_status_txt = _shell_out(
        shell, "cat /sys/bus/platform/devices/84b90000.axi_jesd204_tx/status || true"
    )
    print("$ cat /sys/bus/platform/devices/84a90000.axi_jesd204_rx/status")
    print(rx_status_txt)
    print("$ cat /sys/bus/platform/devices/84b90000.axi_jesd204_tx/status")
    print(tx_status_txt)
    assert "Link status: DATA" in rx_status_txt, (
        "RX JESD link is not in DATA mode. "
        f"RX status:\n{rx_status_txt}\njesd_status output:\n{jesd_status_txt}"
    )
    assert "Link status: DATA" in tx_status_txt, (
        "TX JESD link is not in DATA mode. "
        f"TX status:\n{tx_status_txt}\njesd_status output:\n{jesd_status_txt}"
    )
