"""Generate an ADRV9009 DTS using built-in and custom JSON profile files.

The built-in ``adrv9009_zc706`` profile supplies normal board wiring.  A
user-owned JSON profile supplies only site-specific overrides; explicit values
from that file win while missing values continue to come from the built-in
profile.

Inspect the effective configuration without an XSA or Vivado installation::

    python examples/xsa/adrv9009_profile_file.py \
        --profile-file examples/xsa/profiles/adrv9009_zc706_custom.json \
        --show-config

Run the complete XSA pipeline with the same profile file::

    python examples/xsa/adrv9009_profile_file.py \
        --profile-file my-adrv9009.json \
        --xsa /path/to/system_top.xsa \
        --output-dir build/adrv9009

A custom profile has the same validated shape as a built-in profile::

    {
      "name": "my_adrv9009",
      "defaults": {
        "adrv9009_board": {
          "trx_spi_max_frequency": 10000000
        }
      }
    }
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from adidt.xsa.config.profiles import ProfileManager, merge_profile_defaults
from adidt.xsa.pipeline import XsaPipeline

HERE = Path(__file__).parent
DEFAULT_PROFILE_FILE = HERE / "profiles" / "adrv9009_zc706_custom.json"
DEFAULT_BASE_PROFILE = "adrv9009_zc706"
DEFAULT_OUT_DIR = HERE / "output_adrv9009_profile"


def load_profile_file(path: Path) -> dict[str, Any]:
    """Load and validate one JSON profile using the public profile API."""
    path = path.expanduser().resolve()
    return ProfileManager(profile_dir=path.parent).load(path.stem)


def effective_config(
    profile_file: Path, base_profile: str = DEFAULT_BASE_PROFILE
) -> dict[str, Any]:
    """Merge custom values over a built-in board profile."""
    custom = load_profile_file(profile_file)
    built_in = ProfileManager().load(base_profile)
    custom_defaults = custom["defaults"]
    return merge_profile_defaults(custom_defaults, built_in)


def main() -> None:
    """Parse command-line arguments and inspect or run the profiled pipeline."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile-file",
        type=Path,
        default=DEFAULT_PROFILE_FILE,
        help="Custom JSON profile containing site-specific overrides",
    )
    parser.add_argument(
        "--base-profile",
        default=DEFAULT_BASE_PROFILE,
        help="Built-in board profile used for unspecified values",
    )
    parser.add_argument("--xsa", type=Path, help="Path to the Vivado XSA")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Print the validated merged config and exit without running SDTGen",
    )
    args = parser.parse_args()

    cfg = effective_config(args.profile_file, args.base_profile)
    if args.show_config:
        print(json.dumps(cfg, indent=2, sort_keys=True))
        return

    if args.xsa is None:
        raise SystemExit("Provide --xsa, or use --show-config to inspect the merge")

    result = XsaPipeline().run(
        xsa_path=args.xsa.expanduser().resolve(),
        cfg=cfg,
        output_dir=args.output_dir.expanduser().resolve(),
        profile=args.base_profile,
    )
    print(f"Loaded custom profile: {args.profile_file}")
    print(f"Built-in base profile: {args.base_profile}")
    print("Generated artifacts:")
    for name, path in result.items():
        print(f"  {name}: {path}")


if __name__ == "__main__":
    main()
