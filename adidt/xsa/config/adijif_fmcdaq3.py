"""JESD204 configuration helpers for FMC-DAQ3 boards using adijif."""

from __future__ import annotations

from typing import Any


def _default_cfg() -> dict[str, Any]:
    """Return a hard-coded fallback JESD and clock configuration for FMCDAQ3."""
    return {
        "jesd": {
            "rx": {
                "F": 1,
                "K": 32,
                "M": 2,
                "L": 4,
                "Np": 16,
                "S": 1,
            },
            "tx": {
                "F": 1,
                "K": 32,
                "M": 2,
                "L": 4,
                "Np": 16,
                "S": 1,
            },
        },
        "clock": {
            "rx_device_clk_label": "clkgen",
            "tx_device_clk_label": "clkgen",
            "rx_device_clk_index": 0,
            "tx_device_clk_index": 0,
        },
    }


def _jesd_mode_val(mode: dict[str, Any], key: str, default: int) -> int:
    """Extract a JESD parameter from a mode dict, checking both a nested 'settings' key and the top level."""
    settings = mode.get("settings", {}) if isinstance(mode, dict) else {}
    if key in settings:
        return int(settings[key])
    if key in mode:
        return int(mode[key])
    return default


def resolve_fmcdaq3_config(
    vcxo_hz: float, sample_rate_hz: float, dev_kit_name: str, solve: bool = True
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Compute JESD204B and clock configuration for the FMCDAQ3 board via adijif.

    Attempts to use adijif to select JESD modes and solve clocking for the AD9680
    (ADC) and AD9152 (DAC) at the requested sample rate.  Falls back to a static
    default configuration when adijif is unavailable or the solver fails.

    Args:
        vcxo_hz (float): VCXO frequency in Hz for the AD9523-1 clock chip.
        sample_rate_hz (float): Desired converter sample rate in Hz.
        dev_kit_name (str): adijif FPGA dev-kit identifier (e.g. 'ZCU102').
        solve (bool): Run the adijif solver; set False to skip solving and only
            populate JESD mode fields.

    Returns:
        tuple: (cfg dict, summary dict).  cfg contains 'jesd', optionally
            'fpga_adc'/'fpga_dac' clock keys.  summary reports solver success,
            output clocks, and any fallback reason.
    """
    cfg: dict[str, Any] = _default_cfg()
    summary: dict[str, Any] = {
        "solver_succeeded": False,
        "clock_output_clocks": None,
        "fallback_used": False,
        "fallback_reason": "",
    }

    try:
        import adijif

        sys = adijif.system(["ad9680", "ad9152"], "ad9523_1", "xilinx", vcxo_hz)
        sys.fpga.setup_by_dev_kit_name(dev_kit_name)
        sys.fpga.ref_clock_constraint = "Unconstrained"

        rx_mode = adijif.utils.get_jesd_mode_from_params(
            sys.converter[0], L=2, M=2, Np=16, F=1
        )
        tx_mode = adijif.utils.get_jesd_mode_from_params(
            sys.converter[1], L=2, M=2, Np=16, F=2
        )
        if not rx_mode or not tx_mode:
            raise RuntimeError("No matching FMCDAQ3 JESD modes found via adijif")

        sys.converter[0].set_quick_configuration_mode(rx_mode[0]["mode"], "jesd204b")
        sys.converter[1].set_quick_configuration_mode(tx_mode[0]["mode"], "jesd204b")
        sys.converter[0].sample_clock = sample_rate_hz
        sys.converter[1].sample_clock = sample_rate_hz

        rxm = rx_mode[0]
        txm = tx_mode[0]
        for key, default in (
            ("F", 1),
            ("K", 32),
            ("M", 2),
            ("L", 2),
            ("Np", 16),
            ("S", 1),
        ):
            cfg["jesd"]["rx"][key] = _jesd_mode_val(rxm, key, default)
        for key, default in (
            ("F", 2),
            ("K", 32),
            ("M", 2),
            ("L", 2),
            ("Np", 16),
            ("S", 1),
        ):
            cfg["jesd"]["tx"][key] = _jesd_mode_val(txm, key, default)

        if solve:
            conf = sys.solve()
            summary["solver_succeeded"] = True
            summary["clock_output_clocks"] = conf.get("clock", {}).get("output_clocks")
            rx_conf = conf.get("jesd_AD9680", {})
            tx_conf = conf.get("jesd_AD9152", {})
            for key in ("F", "K", "M", "L", "Np", "S"):
                if key in rx_conf:
                    cfg["jesd"]["rx"][key] = int(rx_conf[key])
                if key in tx_conf:
                    cfg["jesd"]["tx"][key] = int(tx_conf[key])
            cfg["fpga_adc"] = conf.get("fpga_adc", {})
            cfg["fpga_dac"] = conf.get("fpga_dac", {})
    except Exception as ex:  # pragma: no cover - exercised by unit tests via stubs
        summary["fallback_used"] = True
        summary["fallback_reason"] = str(ex)

    return cfg, summary
