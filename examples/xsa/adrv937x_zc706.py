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

from adidt.profiles import resolve_ad9371_jif_config
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

    cfg, summary = resolve_ad9371_jif_config(
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
