"""Generate an ADRV9009 DTS and retrieve a canonical Talise profile.

Two different profile types are involved:

* The built-in ``adrv9009_zc706`` and optional JSON board profile configure
  device-tree wiring and properties for :class:`XsaPipeline`.
* A Talise filter profile from ``analogdevicesinc/iio-oscilloscope`` configures
  the running ADRV9009 through the driver's ``profile_config`` attribute.

Inspect the merged board configuration without XSA/Vivado::

    python examples/xsa/adrv9009_profile_file.py --show-config

Download and verify one canonical Talise profile without touching hardware::

    python examples/xsa/adrv9009_profile_file.py \
        --talise-profile tx200-rx200-orx200 \
        --download-talise-profile

Run the XSA pipeline and retrieve that runtime profile::

    python examples/xsa/adrv9009_profile_file.py \
        --talise-profile tx200-rx200-orx200 \
        --xsa /path/to/system_top.xsa \
        --output-dir build/adrv9009

The script prints explicit copy/application steps but never writes hardware.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import urllib.request
from pathlib import Path
from typing import Any, NamedTuple

from adidt.xsa.config.profiles import ProfileManager, merge_profile_defaults
from adidt.xsa.pipeline import XsaPipeline

HERE = Path(__file__).parent
DEFAULT_BOARD_PROFILE_FILE = HERE / "profiles" / "adrv9009_zc706_custom.json"
DEFAULT_BASE_PROFILE = "adrv9009_zc706"
DEFAULT_OUT_DIR = HERE / "output_adrv9009_profile"
IIO_OSCILLOSCOPE_COMMIT = "c4baaaafe2f91c41c2d4c800f017655296f8a001"
IIO_OSCILLOSCOPE_PROFILE_ROOT = (
    "https://raw.githubusercontent.com/analogdevicesinc/iio-oscilloscope/"
    f"{IIO_OSCILLOSCOPE_COMMIT}/filters/adrv9009"
)


class TaliseProfile(NamedTuple):
    """One reviewed profile in iio-oscilloscope's ADRV9009 filter set."""

    filename: str
    sha256: str


TALISE_PROFILES = {
    "tx100-rx100-orx100": TaliseProfile(
        "Tx_BW100_IR122p88_Rx_BW100_OR122p88_ORx_BW100_OR122p88_DC245p76.txt",
        "d1f6cf05c9f39a63d2cc3bbf18ebaf63e7d0ca4df0c8c9b29733c93386555edd",
    ),
    "tx200-rx100-orx200": TaliseProfile(
        "Tx_BW200_IR245p76_Rx_BW100_OR122p88_ORx_BW200_OR245p76_DC245p76.txt",
        "58fe2c44a69b4cced645b952d14b6d746de39e5a8e7f14e8b600d3121bf38b4b",
    ),
    "tx200-rx200-orx200": TaliseProfile(
        "Tx_BW200_IR245p76_Rx_BW200_OR245p76_ORx_BW200_OR245p76_DC245p76.txt",
        "85e93c550f7b5ca87ec15e5720551bd75eb47753f82f12bc8d740834cc8c4bb7",
    ),
    "tx400-rx100-orx400": TaliseProfile(
        "Tx_BW400_IR491p52_Rx_BW100_OR122p88_ORx_BW400_OR491p52_DC245p76.txt",
        "ad8111a7abbcde2cb4e6505c8cf6e56a81ebd1e3c454d33ccbded93f61c02087",
    ),
}
DEFAULT_TALISE_PROFILE = "tx100-rx100-orx100"


def load_board_profile_file(path: Path) -> dict[str, Any]:
    """Load and validate one JSON board profile using the public profile API."""
    path = path.expanduser().resolve()
    return ProfileManager(profile_dir=path.parent).load(path.stem)


def effective_config(
    board_profile_file: Path, base_profile: str = DEFAULT_BASE_PROFILE
) -> dict[str, Any]:
    """Merge custom board values over a built-in board profile."""
    custom = load_board_profile_file(board_profile_file)
    built_in = ProfileManager().load(base_profile)
    custom_defaults = custom["defaults"]
    return merge_profile_defaults(custom_defaults, built_in)


def _validate_talise_profile(body: bytes, profile: TaliseProfile) -> None:
    digest = hashlib.sha256(body).hexdigest()
    if digest != profile.sha256:
        raise ValueError(
            f"Talise profile SHA-256 mismatch for {profile.filename}: "
            f"expected {profile.sha256}, got {digest}"
        )
    if not body.lstrip().startswith(b"<profile Talise "):
        raise ValueError(f"Talise profile is not expected XML: {profile.filename}")


def download_talise_profile(alias: str, destination: Path) -> Path:
    """Download, verify, and cache one canonical Talise profile."""
    try:
        profile = TALISE_PROFILES[alias]
    except KeyError as ex:
        choices = ", ".join(sorted(TALISE_PROFILES))
        raise ValueError(f"unknown Talise profile {alias!r}; choose from: {choices}") from ex

    destination = destination.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / profile.filename
    if output.exists():
        cached = output.read_bytes()
        try:
            _validate_talise_profile(cached, profile)
        except ValueError:
            output.unlink()
        else:
            return output

    url = f"{IIO_OSCILLOSCOPE_PROFILE_ROOT}/{profile.filename}"
    with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310
        body = response.read()
    _validate_talise_profile(body, profile)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_bytes(body)
    temporary.replace(output)
    return output


def print_talise_application(profile_path: Path) -> None:
    """Print explicit target-side steps without modifying hardware."""
    filename = shlex.quote(profile_path.name)
    print(f"Canonical Talise profile: {profile_path}")
    print("This example does not write hardware automatically.")
    print("Copy the profile to the target, then apply it explicitly:")
    print(f"  scp {shlex.quote(str(profile_path))} root@TARGET:/tmp/{filename}")
    print(
        "  PROFILE_CONFIG=$(find /sys/kernel/debug/iio /sys/bus/iio/devices "
        "-name profile_config 2>/dev/null | head -1)"
    )
    print(f'  cat /tmp/{filename} > "$PROFILE_CONFIG"')


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--board-profile-file",
        "--profile-file",
        dest="board_profile_file",
        type=Path,
        default=DEFAULT_BOARD_PROFILE_FILE,
        help="Validated JSON board-profile overrides (not the Talise filter profile)",
    )
    parser.add_argument(
        "--base-profile",
        default=DEFAULT_BASE_PROFILE,
        help="Built-in board profile used for unspecified values",
    )
    parser.add_argument(
        "--talise-profile",
        choices=sorted(TALISE_PROFILES),
        default=DEFAULT_TALISE_PROFILE,
        help="Canonical iio-oscilloscope ADRV9009 filter profile alias",
    )
    parser.add_argument(
        "--list-talise-profiles",
        action="store_true",
        help="List canonical profile aliases and filenames, then exit",
    )
    parser.add_argument(
        "--download-talise-profile",
        action="store_true",
        help="Download and verify the selected Talise profile without running SDTGen",
    )
    parser.add_argument("--xsa", type=Path, help="Path to the Vivado XSA")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Print the validated board config and exit without running SDTGen",
    )
    return parser


def main() -> None:
    """Inspect profiles, retrieve Talise XML, or run the profiled pipeline."""
    args = _parser().parse_args()

    if args.list_talise_profiles:
        for alias, profile in TALISE_PROFILES.items():
            print(f"{alias}: {profile.filename}")
        return

    cfg = effective_config(args.board_profile_file, args.base_profile)
    if args.show_config:
        print(json.dumps(cfg, indent=2, sort_keys=True))
        return

    output_dir = args.output_dir.expanduser().resolve()
    if args.download_talise_profile:
        profile_path = download_talise_profile(
            args.talise_profile, output_dir / "profiles"
        )
        print_talise_application(profile_path)
        return

    if args.xsa is None:
        raise SystemExit(
            "Provide --xsa, --download-talise-profile, --list-talise-profiles, "
            "or --show-config"
        )

    profile_path = download_talise_profile(args.talise_profile, output_dir / "profiles")
    result = XsaPipeline().run(
        xsa_path=args.xsa.expanduser().resolve(),
        cfg=cfg,
        output_dir=output_dir,
        profile=args.base_profile,
    )
    print(f"Loaded JSON board profile: {args.board_profile_file}")
    print(f"Built-in base profile: {args.base_profile}")
    print("Generated artifacts:")
    for name, path in result.items():
        print(f"  {name}: {path}")
    print_talise_application(profile_path)


if __name__ == "__main__":
    main()
