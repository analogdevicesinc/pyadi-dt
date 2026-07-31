"""ADRV937x + ZC706: profile-driven XSA -> DTS generation.

The canonical AD9371 profile drives both the Linux Mykonos properties and the
corrected three-link ``pyadi-jif`` model.  pyadi-jif owns the RX, observation-RX,
TX, FPGA, and shared-SYSREF electrical intent; pyadi-dt owns physical ZC706 and
AD9528 placement in the generated device tree.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from adidt.xsa.parse.kuiper import download_kuiper_xsa
from adidt.xsa.pipeline import XsaPipeline

HERE = Path(__file__).parent
DEFAULT_OUT_DIR = HERE / "output_adrv937x_zc706"
DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynq-zc706-adv7511-adrv937x"
DEFAULT_AD9371_PROFILE = (
    HERE
    / "profiles"
    / "ad9371_5"
    / "profile_TxBW200_ORxBW200_RxBW100.txt"
)

# The profile contains datapath rates and interpolation/decimation but not JESD
# transport framing.  These are ADI's standard Mykonos transport modes.  The
# corrected pyadi-jif AD9371 model validates them and supplies F/N/CS details.
_RX_JESD = {"M": 4, "L": 2, "S": 1, "Np": 16}
_OBS_JESD = {"M": 2, "L": 2, "S": 1, "Np": 16}
_TX_JESD = {"M": 4, "L": 4, "S": 1, "Np": 16}


def _jesd_config(path: Any) -> dict[str, int]:
    """Return pyadi-dt framing fields from one configured pyadi-jif path."""
    return {
        key: int(getattr(path, key))
        for key in ("F", "K", "M", "L", "N", "Np", "S", "CS")
    }


def _resolve_config_from_adijif(
    profile_path: Path, *, solve: bool = False
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply an AD9371 profile to the corrected pyadi-jif Mykonos model.

    Args:
        profile_path: Canonical AD9371 profile-wizard text file.
        solve: Run the full AD9528 + FPGA CPLEX solve when true.  Profile and
            quick-mode validation do not require a solver.

    Returns:
        A pyadi-dt pipeline configuration and a human-readable solver summary.

    Raises:
        RuntimeError: If the installed pyadi-jif predates AD9371 support.
    """
    import adijif

    if not hasattr(adijif, "ad9371"):
        raise RuntimeError(
            "Installed pyadi-jif does not provide the AD9371 profile model. "
            "Install the AD9371-capable revision documented for this example."
        )

    resolved_profile = profile_path.expanduser().resolve()
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
            for key in ("F", "K", "M", "L", "N", "Np", "S", "CS"):
                if key in solved_jesd:
                    cfg["jesd"][cfg_name][key] = int(solved_jesd[key])
            cfg[f"fpga_{solved_name}"] = solved[f"fpga_{solved_name}"]

    return cfg, summary


def _download_kuiper_xsa(
    release: str, project: str, cache_dir: Path, out_dir: Path
) -> Path:
    return download_kuiper_xsa(
        release=release,
        project=project,
        cache_dir=cache_dir,
        out_dir=out_dir,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xsa", type=Path, default=None, help="Path to local .xsa")
    parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUT_DIR, help="Output directory"
    )
    parser.add_argument(
        "--download-kuiper",
        action="store_true",
        help="Download XSA from Kuiper boot-partition release",
    )
    parser.add_argument("--release", default=DEFAULT_KUIPER_RELEASE)
    parser.add_argument("--project", default=DEFAULT_KUIPER_PROJECT)
    parser.add_argument(
        "--ad9371-profile",
        type=Path,
        default=DEFAULT_AD9371_PROFILE,
        help="Canonical AD9371 profile used by both pyadi-jif and the DTS renderer",
    )
    parser.add_argument(
        "--solve-adijif",
        action="store_true",
        help="Run the full AD9528/FPGA CPLEX solve instead of profile validation only",
    )
    parser.add_argument(
        "--show-jif-config",
        action="store_true",
        help="Print profile-derived configuration as JSON and exit without an XSA",
    )
    args = parser.parse_args()

    cfg, summary = _resolve_config_from_adijif(
        args.ad9371_profile, solve=args.solve_adijif
    )
    if args.show_jif_config:
        print(json.dumps({"config": cfg, "summary": summary}, indent=2, sort_keys=True))
        return

    out_dir = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.download_kuiper:
        xsa_path = _download_kuiper_xsa(
            release=args.release,
            project=args.project,
            cache_dir=out_dir / "kuiper_cache",
            out_dir=out_dir / "xsa",
        )
    else:
        if args.xsa is None:
            raise SystemExit("Provide --xsa or use --download-kuiper")
        xsa_path = args.xsa.resolve()

    result = XsaPipeline().run(
        xsa_path=xsa_path,
        cfg=cfg,
        output_dir=out_dir,
        profile="adrv937x_zc706",
    )
    print("Generated artifacts (explicit profile=adrv937x_zc706):")
    for key, value in result.items():
        print(f"  {key}: {value}")
    print("pyadi-jif summary:")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
