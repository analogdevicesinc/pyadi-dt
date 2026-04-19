"""AD9081 + VPK180 XSA pipeline hardware test.

Requires:
- LG_ENV environment variable pointing to labgrid environment YAML
- Vivado 2025.1 sdtgen on PATH
- AD9081-FMCA-EBZ + VPK180 hardware

HDL: analogdevicesinc/hdl main branch
Linux: analogdevicesinc/linux main branch
Vivado: 2025.1
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from adidt.xsa.pipeline import XsaPipeline

import iio
import pytest

if not os.environ.get("LG_ENV"):
    pytest.skip(
        "set LG_ENV for AD9081 VPK180 hardware test",
        allow_module_level=True,
    )

HERE = Path(__file__).parent
DEFAULT_OUT_DIR = HERE / "output"
DEFAULT_KUIPER_PROJECT = "versal-vpk180-reva-ad9081"
DEFAULT_VCXO_HZ = 100e6
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


def _resolve_config_from_adijif(
    vcxo_hz: float, solve: bool = False
) -> tuple[dict, dict]:
    """Build XSA pipeline config using pyadi-jif for AD9081 M8/L8 on VPK180."""
    import adijif

    sys = adijif.system("ad9081", "hmc7044", "xilinx", vcxo=vcxo_hz)

    sys.fpga.setup_by_dev_kit_name("vpk180")

    # VPK180 HDL default: JESD204C 64B66B, M=8/L=8/S=2/NP=12
    # ADC = 2 GHz, DAC = 4 GHz, CDDC dec=1, FDDC dec=1, CDUC int=2, FDUC int=1
    cddc = 1
    fddc = 1
    cduc = 2
    fduc = 1

    sys.converter.clocking_option = "integrated_pll"
    sys.converter.adc.sample_clock = 2000000000 / cddc / fddc
    sys.converter.dac.sample_clock = 4000000000 / cduc / fduc

    sys.converter.adc.datapath.cddc_decimations = [cddc] * 4
    sys.converter.dac.datapath.cduc_interpolation = cduc
    sys.converter.adc.datapath.fddc_decimations = [fddc] * 4
    sys.converter.dac.datapath.fduc_interpolation = fduc
    sys.converter.adc.datapath.fddc_enabled = [True] * 4
    sys.converter.dac.datapath.fduc_enabled = [True] * 4

    mode_rx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.adc,
        M=8,
        L=8,
        Np=12,
        S=2,
        jesd_class="jesd204c",
    )
    mode_tx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.dac,
        M=8,
        L=8,
        Np=12,
        S=2,
        jesd_class="jesd204c",
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
    """Compile DTS to DTB, handling #include preprocessing."""
    compile_input = dts_path
    text = dts_path.read_text()

    if "#include" in text:
        if shutil.which("cpp") is None:
            raise RuntimeError(
                "cpp not found on PATH (required for #include preprocessing)"
            )
        preprocessed = dts_path.with_suffix(".pp.dts")
        inc_dirs = [str(dts_path.parent)]
        linux_path = os.environ.get("LINUX_KERNEL_PATH", "./linux")
        for sub in [
            "include",
            "arch/arm64/boot/dts",
            "arch/arm64/boot/dts/xilinx",
        ]:
            inc_dirs.append(str(Path(linux_path) / sub))
        cmd = ["cpp", "-nostdinc", "-undef", "-x", "assembler-with-cpp"]
        for d in inc_dirs:
            cmd += ["-I", d]
        cmd += [str(dts_path), str(preprocessed)]
        subprocess.run(cmd, check=True)
        compile_input = preprocessed

    subprocess.run(
        [
            "dtc",
            "-I",
            "dts",
            "-O",
            "dtb",
            "-o",
            str(dtb_path),
            str(compile_input),
        ],
        check=True,
    )


class TestAD9081VPK180XsaPipeline:
    """AD9081 + VPK180 XSA pipeline integration tests."""

    @pytest.fixture(scope="class")
    def pipeline_config(self):
        """Resolve AD9081 M8/L8 config via adijif."""
        cfg, summary = _resolve_config_from_adijif(DEFAULT_VCXO_HZ, solve=True)
        return cfg, summary

    @pytest.fixture(scope="class")
    def xsa_path(self):
        """Path to the VPK180 AD9081 XSA file."""
        xsa = HERE / "system_top_vpk180_ad9081.xsa"
        if not xsa.exists():
            pytest.skip(f"XSA file not found: {xsa}")
        return xsa

    @pytest.fixture(scope="class")
    def pipeline_result(self, xsa_path, pipeline_config):
        """Run the XSA pipeline and return the result dict."""
        cfg, _ = pipeline_config
        pipeline = XsaPipeline()
        out_dir = DEFAULT_OUT_DIR / "vpk180_ad9081"
        out_dir.mkdir(parents=True, exist_ok=True)
        result = pipeline.run(
            xsa_path=xsa_path,
            cfg=cfg,
            output_dir=out_dir,
            profile="ad9081_vpk180",
            emit_report=True,
            lint=True,
        )
        return result

    def test_pipeline_produces_merged_dts(self, pipeline_result):
        merged = Path(pipeline_result["merged"])
        assert merged.exists(), f"Merged DTS not found: {merged}"
        text = merged.read_text()
        assert "ad9081" in text.lower() or "mxfe" in text.lower()

    def test_merged_dts_has_versal_clk(self, pipeline_result):
        merged = Path(pipeline_result["merged"])
        text = merged.read_text()
        assert "versal_clk" in text

    def test_merged_dts_compiles(self, pipeline_result):
        merged = Path(pipeline_result["merged"])
        dtb = merged.with_suffix(".dtb")
        _compile_dts_to_dtb(merged, dtb)
        assert dtb.exists()
