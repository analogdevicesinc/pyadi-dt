"""FMCDAQ2 + ZCU102: generate full DTS from XSA with pyadi-jif config."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from adidt.xsa.pipeline import XsaPipeline

HERE = Path(__file__).parent
DEFAULT_OUT_DIR = HERE / "output_fmcdaq2_zcu102"
DEFAULT_VCXO_HZ = 125e6
DEFAULT_SAMPLE_RATE_HZ = 500e6


def _resolve_config_from_adijif(
    vcxo_hz: float, sample_rate_hz: float
) -> tuple[dict[str, Any], dict[str, Any]]:
    import adijif

    sys = adijif.system(["ad9680", "ad9144"], "ad9523_1", "xilinx", vcxo_hz)
    sys.fpga.setup_by_dev_kit_name("zcu102")
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

    def _jesd_mode_val(mode: dict[str, Any], key: str, default: int) -> int:
        settings = mode.get("settings", {}) if isinstance(mode, dict) else {}
        if key in settings:
            return int(settings[key])
        if key in mode:
            return int(mode[key])
        return default

    rxm = rx_mode[0]
    txm = tx_mode[0]

    cfg: dict[str, Any] = {
        "jesd": {
            "rx": {
                "F": _jesd_mode_val(rxm, "F", 1),
                "K": _jesd_mode_val(rxm, "K", 32),
                "M": _jesd_mode_val(rxm, "M", 2),
                "L": _jesd_mode_val(rxm, "L", 4),
                "Np": _jesd_mode_val(rxm, "Np", 16),
                "S": _jesd_mode_val(rxm, "S", 1),
            },
            "tx": {
                "F": _jesd_mode_val(txm, "F", 1),
                "K": _jesd_mode_val(txm, "K", 32),
                "M": _jesd_mode_val(txm, "M", 2),
                "L": _jesd_mode_val(txm, "L", 4),
                "Np": _jesd_mode_val(txm, "Np", 16),
                "S": _jesd_mode_val(txm, "S", 1),
            },
        },
        "clock": {
            "rx_device_clk_label": "clk0_ad9523",
            "tx_device_clk_label": "clk0_ad9523",
            "rx_device_clk_index": 13,
            "tx_device_clk_index": 1,
        },
    }
    summary: dict[str, Any] = {
        "solver_succeeded": False,
        "sample_rate_hz": sample_rate_hz,
        "clock_output_clocks": None,
    }
    try:
        conf = sys.solve()
    except Exception:
        return cfg, summary

    summary["solver_succeeded"] = True
    summary["clock_output_clocks"] = conf.get("clock", {}).get("output_clocks")
    rx = conf.get("jesd_AD9680", {})
    tx = conf.get("jesd_AD9144", {})
    for key in ("F", "K", "M", "L", "Np", "S"):
        if key in rx:
            cfg["jesd"]["rx"][key] = int(rx[key])
        if key in tx:
            cfg["jesd"]["tx"][key] = int(tx[key])
    cfg["fpga_adc"] = conf.get("fpga_adc", {})
    cfg["fpga_dac"] = conf.get("fpga_dac", {})
    return cfg, summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--xsa", type=Path, required=True, help="Path to system_top.xsa"
    )
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
