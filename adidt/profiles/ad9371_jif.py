"""Build pyadi-dt configuration from the corrected pyadi-jif AD9371 model."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_RX_JESD = {"M": 4, "L": 2, "S": 1, "Np": 16}
_OBS_JESD = {"M": 2, "L": 2, "S": 1, "Np": 16}
_TX_JESD = {"M": 4, "L": 4, "S": 1, "Np": 16}
_JESD_FIELDS = ("F", "K", "M", "L", "N", "Np", "S", "CS")


def _jesd_config(path: Any) -> dict[str, int]:
    return {key: int(getattr(path, key)) for key in _JESD_FIELDS}


def resolve_ad9371_jif_config(
    profile_path: str | Path, *, solve: bool = False
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply a canonical AD9371 profile to pyadi-jif's three-link model.

    The returned configuration is accepted directly by :class:`XsaPipeline`.
    When ``solve`` is true, the solved JESD and FPGA settings replace quick-mode
    values and the summary includes the AD9528 output-clock solution.
    """
    adijif = importlib.import_module("adijif")

    if not hasattr(adijif, "ad9371"):
        raise RuntimeError(
            "Installed pyadi-jif does not provide the AD9371 profile model. "
            "Install the AD9371-capable revision documented for this example."
        )

    resolved_profile = Path(profile_path).expanduser().resolve()
    if not resolved_profile.is_file():
        raise FileNotFoundError(f"AD9371 profile file not found: {resolved_profile}")

    system = adijif.system("ad9371", "ad9528", "xilinx", 122_880_000)
    system.converter.apply_profile_settings(
        str(resolved_profile),
        rx_jesd=_RX_JESD,
        obs_jesd=_OBS_JESD,
        tx_jesd=_TX_JESD,
    )
    system.fpga.setup_by_dev_kit_name("zc706")
    system.fpga.force_qpll = True

    converter = system.converter
    metadata = converter.get_config()
    cfg: dict[str, Any] = {
        "jesd": {
            "rx": _jesd_config(converter.adc),
            "obs": _jesd_config(converter.obs),
            "tx": _jesd_config(converter.dac),
        },
        "clock": {
            "rx_device_clk_label": "clkgen",
            "tx_device_clk_label": "clkgen",
        },
        "adrv9009_board": {
            "ad9371_profile_path": str(resolved_profile),
            "ad9528_vcxo_freq": int(metadata["device_clock"]),
            "ad9528_jesd204_max_sysref_hz": int(
                metadata["jesd204_max_sysref_hz"]
            ),
        },
    }
    summary: dict[str, Any] = {
        "profile": str(resolved_profile),
        "rates_hz": {
            "rx": int(converter.adc.sample_clock),
            "obs": int(converter.obs.sample_clock),
            "tx": int(converter.dac.sample_clock),
        },
        "lane_rates_hz": {
            "rx": int(converter.adc.bit_clock),
            "obs": int(converter.obs.bit_clock),
            "tx": int(converter.dac.bit_clock),
        },
        "solver_attempted": solve,
        "solver_succeeded": False,
        "clock_output_clocks": None,
    }

    if solve:
        solved = system.solve()
        summary["solver_succeeded"] = True
        summary["clock_output_clocks"] = solved["clock"]["output_clocks"]
        for cfg_name, solved_name in (
            ("rx", "adc"),
            ("obs", "obs"),
            ("tx", "dac"),
        ):
            solved_jesd = solved[f"jesd_{solved_name}"]
            for key in _JESD_FIELDS:
                if key in solved_jesd:
                    cfg["jesd"][cfg_name][key] = int(solved_jesd[key])
            cfg[f"fpga_{solved_name}"] = solved[f"fpga_{solved_name}"]

    return cfg, summary
