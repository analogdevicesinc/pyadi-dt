"""FMCDAQ2 + ZC706: generate full DTS from XSA with pyadi-jif config."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from adidt.xsa.pipeline import XsaPipeline

HERE = Path(__file__).parent
DEFAULT_OUT_DIR = HERE / "output_fmcdaq2_zc706"
DEFAULT_VCXO_HZ = 125e6
DEFAULT_SAMPLE_RATE_HZ = 500e6


def _resolve_config_from_adijif(
    vcxo_hz: float, sample_rate_hz: float
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
    conf = sys.solve()

    rx = conf.get("jesd_AD9680", {})
    tx = conf.get("jesd_AD9144", {})
    cfg: dict[str, Any] = {
        "jesd": {
            "rx": {
                "F": int(rx.get("F", 1)),
                "K": int(rx.get("K", 32)),
                "M": int(rx.get("M", 2)),
                "L": int(rx.get("L", 4)),
                "Np": int(rx.get("Np", 16)),
                "S": int(rx.get("S", 1)),
            },
            "tx": {
                "F": int(tx.get("F", 1)),
                "K": int(tx.get("K", 32)),
                "M": int(tx.get("M", 2)),
                "L": int(tx.get("L", 4)),
                "Np": int(tx.get("Np", 16)),
                "S": int(tx.get("S", 1)),
            },
        },
        "clock": {
            "rx_device_clk_label": "clk0_ad9523",
            "tx_device_clk_label": "clk0_ad9523",
            "rx_device_clk_index": 13,
            "tx_device_clk_index": 1,
        },
        "fpga_adc": conf.get("fpga_adc", {}),
        "fpga_dac": conf.get("fpga_dac", {}),
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
    summary = {
        "sample_rate_hz": sample_rate_hz,
        "clock_output_clocks": conf.get("clock", {}).get("output_clocks"),
    }
    return cfg, summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--xsa", type=Path, required=True, help="Path to system_top.xsa")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--vcxo-hz", type=float, default=DEFAULT_VCXO_HZ)
    parser.add_argument("--sample-rate-hz", type=float, default=DEFAULT_SAMPLE_RATE_HZ)
    args = parser.parse_args()

    cfg, summary = _resolve_config_from_adijif(args.vcxo_hz, args.sample_rate_hz)
    result = XsaPipeline().run(args.xsa, cfg, args.output_dir, sdtgen_timeout=300)
    print(f"Generated overlay: {result['overlay']}")
    print(f"Generated merged : {result['merged']}")
    print(f"Generated report : {result['report']}")
    print(f"Clock outputs    : {summary['clock_output_clocks']}")


if __name__ == "__main__":
    main()
