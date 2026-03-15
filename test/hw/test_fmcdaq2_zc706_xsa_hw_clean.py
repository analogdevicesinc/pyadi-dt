from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import iio
import pytest

from adidt.xsa.pipeline import XsaPipeline
from test.xsa.kuiper_release import download_project_xsa

if not os.environ.get("LG_ENV"):
    pytest.skip(
        "set LG_ENV for FMCDAQ2 ZC706 hardware test",
        allow_module_level=True,
    )

HERE = Path(__file__).parent
DEFAULT_OUT_DIR = HERE / "output"
DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynq-zc706-adv7511-fmcdaq2"
DEFAULT_KUIPER_BOOTBIN = "release:zynq-zc706-adv7511-fmcdaq2/BOOT.BIN"
DEFAULT_VCXO_HZ = 125e6
DEFAULT_SAMPLE_RATE_HZ = 500e6
DEFAULT_BUILD_KERNEL = os.environ.get("ADI_XSA_BUILD_KERNEL", "1").lower() not in {
    "0",
    "false",
    "no",
}


def _require_hw_prereqs():
    if not os.environ.get("LG_ENV"):
        pytest.skip("set LG_ENV for FMCDAQ2 ZC706 hardware test")
    if shutil.which("sdtgen") is None:
        pytest.skip("sdtgen not found on PATH (Vivado tools required)")
    if shutil.which("dtc") is None:
        pytest.skip("dtc not found on PATH")
    if shutil.which("usbsdmux") is None:
        local_usbsdmux = Path.cwd() / "venv" / "bin" / "usbsdmux"
        if local_usbsdmux.exists():
            os.environ["PATH"] = f"{local_usbsdmux.parent}:{os.environ.get('PATH', '')}"
    if shutil.which("usbsdmux") is None:
        pytest.skip("usbsdmux not found on PATH")


def _resolve_config_from_adijif(
    vcxo_hz: float, sample_rate_hz: float, solve: bool = True
) -> tuple[dict[str, Any], dict[str, Any]]:
    import adijif

    sys = adijif.system(["ad9680", "ad9144"], "ad9523_1", "xilinx", vcxo_hz)
    sys.fpga.setup_by_dev_kit_name("zc706")
    sys.fpga.ref_clock_constraint = "Unconstrained"

    rx_mode = adijif.utils.get_jesd_mode_from_params(
        sys.converter[0], L=4, M=2, Np=16, F=1
    )
    tx_mode = adijif.utils.get_jesd_mode_from_params(
        sys.converter[1], L=4, M=2, Np=16, F=1
    )
    if not rx_mode or not tx_mode:
        raise RuntimeError("No matching FMCDAQ2 JESD modes found via adijif")

    sys.converter[0].set_quick_configuration_mode(rx_mode[0]["mode"], "jesd204b")
    sys.converter[1].set_quick_configuration_mode(tx_mode[0]["mode"], "jesd204b")
    sys.converter[0].sample_clock = sample_rate_hz
    sys.converter[1].sample_clock = sample_rate_hz

    rx = rx_mode[0]["settings"]
    tx = tx_mode[0]["settings"]
    cfg: dict[str, Any] = {
        "jesd": {
            "rx": {
                "F": int(rx["F"]),
                "K": int(rx["K"]),
                "M": int(rx["M"]),
                "L": int(rx["L"]),
                "Np": int(rx["Np"]),
                "S": int(rx["S"]),
            },
            "tx": {
                "F": int(tx["F"]),
                "K": int(tx["K"]),
                "M": int(tx["M"]),
                "L": int(tx["L"]),
                "Np": int(tx["Np"]),
                "S": int(tx["S"]),
            },
        },
        "clock": {
            "rx_device_clk_label": "clk0_ad9523",
            "tx_device_clk_label": "clk0_ad9523",
            "rx_device_clk_index": 13,
            "tx_device_clk_index": 1,
        },
        "fmcdaq2_board": {
            "spi_bus": "spi0",
            "clock_cs": 0,
            "adc_cs": 1,
            "dac_cs": 2,
            "clock_vcxo_hz": int(vcxo_hz),
            "adc_core_label": "axi_ad9680_core",
            "dac_core_label": "axi_ad9144_core",
            "adc_xcvr_label": "axi_ad9680_adxcvr",
            "dac_xcvr_label": "axi_ad9144_adxcvr",
            "adc_jesd_label": "axi_ad9680_jesd204_rx",
            "dac_jesd_label": "axi_ad9144_jesd204_tx",
            "adc_jesd_link_id": 1,
            "dac_jesd_link_id": 0,
        },
    }
    summary: dict[str, Any] = {
        "solver_succeeded": False,
        "clock_output_clocks": None,
    }

    if solve:
        conf = sys.solve()
        summary["solver_succeeded"] = True
        summary["clock_output_clocks"] = conf.get("clock", {}).get("output_clocks")
        cfg["fpga_adc"] = conf.get("fpga_adc", {})
        cfg["fpga_dac"] = conf.get("fpga_dac", {})

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
    _require_hw_prereqs()
    strategy.transition("powered_off")
    yield strategy


@pytest.fixture(scope="module")
def built_kernel_image() -> Path | None:
    if not DEFAULT_BUILD_KERNEL:
        return None

    try:
        from adibuild import BuildConfig, LinuxBuilder
        from adibuild.platforms import ZynqPlatform
    except ModuleNotFoundError as ex:
        pytest.skip(f"pyadi-build dependency missing: {ex}")

    config_path = HERE / "2023_R2.yaml"
    if not config_path.exists():
        pytest.skip(f"pyadi-build config not found: {config_path}")

    config = BuildConfig.from_yaml(config_path)
    platform_cfg = config.get_platform("zynq")
    platform = ZynqPlatform(platform_cfg)
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


def _shell_out(shell, cmd: str) -> str:
    res = shell.run(cmd)
    out = res[0] if isinstance(res, tuple) else res
    if isinstance(out, list):
        return "\n".join(out)
    return str(out)


@pytest.mark.lg_feature(["fmcdaq2", "zc706"])
def test_fmcdaq2_zc706_xsa_hw(board, built_kernel_image, tmp_path):
    release = os.environ.get("ADI_KUIPER_BOOT_RELEASE", DEFAULT_KUIPER_RELEASE)
    project = os.environ.get("ADI_KUIPER_XSA_PROJECT", DEFAULT_KUIPER_PROJECT)
    bootbin = os.environ.get("ADI_KUIPER_BOOTBIN", DEFAULT_KUIPER_BOOTBIN)

    xsa_path = download_project_xsa(
        release=release,
        project_dir=project,
        cache_dir=tmp_path / "kuiper_cache",
        output_dir=tmp_path / "xsa",
    )
    assert xsa_path.exists(), f"XSA extraction failed: {xsa_path}"

    cfg, _summary = _resolve_config_from_adijif(
        DEFAULT_VCXO_HZ, DEFAULT_SAMPLE_RATE_HZ, solve=True
    )
    out_dir = DEFAULT_OUT_DIR
    result = XsaPipeline().run(
        xsa_path=xsa_path,
        cfg=cfg,
        output_dir=out_dir,
        sdtgen_timeout=300,
    )

    dtb = out_dir / "devicetree.dtb"
    _compile_dts_to_dtb(result["merged"], dtb)

    kuiper = board.target.get_driver("KuiperDLDriver")
    kuiper.kuiper_resource.BOOTBIN_path = bootbin
    kuiper.get_boot_files_from_release()
    if built_kernel_image is not None:
        kuiper.add_files_to_target(built_kernel_image)
    kuiper.add_files_to_target(dtb)

    board.transition("shell")
    shell = board.target.get_driver("ADIShellDriver")
    dmesg_txt = _shell_out(shell, "dmesg")
    (out_dir / "dmesg_fmcdaq2_zc706_xsa.log").write_text(dmesg_txt)

    addresses = shell.get_ip_addresses()
    ip_address = str(addresses[0].ip)
    if "/" in ip_address:
        ip_address = ip_address.split("/")[0]
    ctx = iio.Context(f"ip:{ip_address}")
    assert ctx is not None, "Failed to create IIO context"

    expected = ["axi-ad9680-hpc", "axi-ad9144-hpc"]
    found = [d.name for d in ctx.devices]
    for device_name in expected:
        assert device_name in found, (
            f"Expected IIO device '{device_name}' not found. "
            f"Available devices: {found}"
        )
