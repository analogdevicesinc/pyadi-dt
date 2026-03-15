"""ADRV937x + ZC706: full XSA -> DTS generation example."""

from __future__ import annotations

import argparse
import io
import tarfile
from pathlib import Path

import requests

from adidt.xsa.pipeline import XsaPipeline

HERE = Path(__file__).parent
DEFAULT_OUT_DIR = HERE / "output_adrv937x_zc706"
DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynq-zc706-adv7511-adrv937x"


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
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    tarball = cache_dir / f"{release}_latest_boot_partition.tar.gz"
    if not tarball.exists():
        url = (
            "https://swdownloads.analog.com/cse/boot_partition_files/"
            f"{release}/latest_boot_partition.tar.gz"
        )
        response = requests.get(url, stream=True, timeout=120)
        response.raise_for_status()
        with tarball.open("wb") as fout:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fout.write(chunk)

    nested_member_name = f"{project}/bootgen_sysfiles.tgz"
    with tarfile.open(tarball, "r:gz") as outer_tar:
        nested_member = outer_tar.getmember(nested_member_name)
        nested_f = outer_tar.extractfile(nested_member)
        if nested_f is None:
            raise RuntimeError(f"missing member data: {nested_member_name}")
        nested_bytes = nested_f.read()

    with tarfile.open(fileobj=io.BytesIO(nested_bytes), mode="r:gz") as inner_tar:
        xsa_members = [m for m in inner_tar.getmembers() if m.name.endswith(".xsa")]
        if not xsa_members:
            raise RuntimeError(f"no .xsa found under project {project}")
        selected = next(
            (
                m
                for m in xsa_members
                if m.name.endswith("/system_top.xsa") or m.name == "system_top.xsa"
            ),
            xsa_members[0],
        )
        src = inner_tar.extractfile(selected)
        if src is None:
            raise RuntimeError(f"unable to read XSA member {selected.name}")
        xsa_path = out_dir / Path(selected.name).name
        xsa_path.write_bytes(src.read())
        return xsa_path


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
        profile="adrv937x_zc706",
    )
    print("Generated artifacts (explicit profile=adrv937x_zc706):")
    for key, value in result.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
