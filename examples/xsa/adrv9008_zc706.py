"""ADRV9008 + ZC706: full XSA -> DTS generation example."""

from __future__ import annotations

import argparse
from pathlib import Path

from adidt.xsa.kuiper import download_kuiper_xsa
from adidt.xsa.pipeline import XsaPipeline

HERE = Path(__file__).parent
DEFAULT_OUT_DIR = HERE / "output_adrv9008_zc706"
DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynq-zc706-adv7511-adrv9008-1-2"


def _default_config() -> dict:
    return {
        "jesd": {
            "rx": {"F": 4, "K": 32, "M": 4, "L": 4, "Np": 16, "S": 1},
            "tx": {"F": 2, "K": 32, "M": 4, "L": 4, "Np": 16, "S": 1},
        },
        "clock": {
            "rx_device_clk_label": "clkgen",
            "tx_device_clk_label": "clkgen",
            "hmc7044_rx_channel": 0,
            "hmc7044_tx_channel": 0,
        },
    }


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
    args = parser.parse_args()

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
        cfg=_default_config(),
        output_dir=out_dir,
        profile="adrv9008_zc706",
    )
    print("Generated artifacts (explicit profile=adrv9008_zc706):")
    for key, value in result.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
