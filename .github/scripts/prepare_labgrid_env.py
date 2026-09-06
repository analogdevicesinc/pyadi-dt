#!/usr/bin/env python3
"""Select deployment-capable labgrid environments for generated-DTB tests."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.request import urlopen


def remote_place_name(config: dict) -> str | None:
    """Read the main target's RemotePlace without acquiring hardware."""
    resources = config.get("targets", {}).get("main", {}).get("resources", {})
    entries = [resources] if isinstance(resources, dict) else resources
    for entry in entries:
        if "RemotePlace" in entry:
            return entry["RemotePlace"]["name"]
    return None


def deployment_config(
    config: dict, place: dict, *, tftp_root: str, render, uboot_image: str | None = None
) -> dict:
    """Render the advertised TFTP strategy, forcing staged-file deployment.

    Other strategies retain the supplied configuration. In particular this
    does not invent a deployment path for an unknown or recovery-only place.
    """
    if remote_place_name(config) != place.get("name"):
        raise ValueError(
            "Coordinator returned a different place from the supplied environment"
        )
    if place.get("tags", {}).get("boot-strategy") == "BootZynqMPJTAG":
        prepared = render(place, {})
        imports = prepared.setdefault("imports", [])
        strategy_import = "adi_lg_plugins.strategies.bootzynqmpjtag"
        if strategy_import not in imports:
            imports.append(strategy_import)
        strategy = prepared["targets"]["main"]["drivers"]["BootZynqMPJTAG"]
        # The SoM carrier has two Ethernet ports. Either can provide IIO;
        # eth0-only checks incorrectly reject the connected eth1 port.
        strategy["kuiper_verify_commands"] = [
            "i=0; until ip -4 -o addr show scope global | grep -q 'inet '; "
            "do i=$((i+1)); test $i -lt 90 || exit 1; sleep 1; done",
            "test $(for n in /sys/bus/iio/devices/iio:device*/name; "
            "do cat \"$n\"; done | grep -c '^adrv9009-phy') -eq 2",
            "test $(dmesg | grep -c 'successfully initialized via jesd204-fsm') -ge 2",
        ]
        return prepared
    if place.get("tags", {}).get("boot-strategy") != "BootFPGASoCTFTP":
        return config
    prepared = render(place, {"sd_autoboot": "false", "tftp_root": tftp_root})
    strategy = prepared["targets"]["main"]["drivers"]["BootFPGASoCTFTP"]
    strategy["sd_autoboot"] = False
    strategy["tftp_root_folder"] = tftp_root
    if uboot_image:
        if not Path(uboot_image).is_absolute():
            raise ValueError("U-Boot image must be an absolute exporter path")
        strategy["uboot_elf"] = uboot_image
    return prepared


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--coordinator", default=os.environ.get("LG_COORDINATOR"))
    parser.add_argument("--api", help="Override the coordinator REST API base URL")
    args = parser.parse_args()

    import yaml

    config = yaml.safe_load(args.env.read_text())
    name = remote_place_name(config)
    if name and args.coordinator:
        address = urlsplit(
            args.coordinator if "://" in args.coordinator else f"//{args.coordinator}"
        )
        host = address.hostname
        if not host:
            parser.error("Invalid coordinator address")
        if ":" in host:
            host = f"[{host}]"
        api = args.api or f"http://{host}:8000/api"
        with urlopen(
            f"{api.rstrip('/')}/places/{quote(name, safe='')}", timeout=15
        ) as response:
            place = json.load(response)

        def render(raw, substitutions):
            from adi_lg_plugins.hw_ci.render_env import render_env
            from adi_lg_plugins.hw_ci.schema import validate_place

            return yaml.safe_load(
                render_env(validate_place(raw), extra_subs=substitutions)
            )

        tftp_root = (
            tempfile.mkdtemp(prefix="adidt-tftp-")
            if place.get("tags", {}).get("boot-strategy") == "BootFPGASoCTFTP"
            else ""
        )
        config = deployment_config(
            config,
            place,
            tftp_root=tftp_root,
            render=render,
            uboot_image=os.environ.get("ADIDT_ZYNQ_UBOOT_IMAGE"),
        )
    with args.output.open("w") as output:
        os.chmod(args.output, 0o600)
        yaml.safe_dump(config, output, sort_keys=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
