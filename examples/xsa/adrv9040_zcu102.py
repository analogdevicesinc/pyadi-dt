"""Generate ADRV9040 ZCU102 DTS from a local standard or ORX/NLS XSA.

Examples::

    python examples/xsa/adrv9040_zcu102.py --xsa standard/system_top.xsa
    python examples/xsa/adrv9040_zcu102.py --xsa nls/system_top.xsa \\
        --profile adrv9040_zcu102_nls --config board-overrides.json

Firmware, CSV gain tables and ACE profile binaries are supplied separately.
This example does not download boot images or claim hardware qualification.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adidt.xsa.pipeline import XsaPipeline


def main(argv: list[str] | None = None) -> dict[str, Path]:
    """Run the XSA pipeline, selecting the observation layout automatically."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xsa", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("output/adrv9040"))
    parser.add_argument("--profile", choices=("adrv9040_zcu102", "adrv9040_zcu102_nls"))
    parser.add_argument("--config", type=Path, help="JSON configuration overrides")
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text()) if args.config else {}
    result = XsaPipeline().run(args.xsa, config, args.output_dir, profile=args.profile)
    for kind, path in result.items():
        print(f"{kind}: {path}")
    return result


if __name__ == "__main__":
    main()
