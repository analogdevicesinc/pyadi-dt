#!/usr/bin/env python3
"""Seed declarative design profiles from kernel reference device trees.

For every Kuiper boot directory selected from an HDL release inventory, this
pairs the released XSA with its kernel reference DTS and writes a profile
whose ``design`` section the ``DeclarativeBuilder`` renders.  Addresses and
interrupts are tied to the XSA; everything else is taken from the reference.

The output is meant to be reviewed: the ``notes`` in each profile list what
was dropped, created or overridden.

Example::

    python scripts/seed_declarative_profile.py \\
        --inventory adidt/xsa/config/hdl_2026_r1_designs.json \\
        --linux ~/dev/linux \\
        --xsa-cache ~/.cache/adidt/kuiper/2026_r1_xsa \\
        --only 'zynqmp-zcu102-rev10-ad9083*'

Needs ``sdtgen``, ``cpp`` and ``git`` on ``PATH``.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from adidt.xsa.declarative.seed import (  # noqa: E402
    SeedError,
    export_kernel_tree,
    seed_profile_for_xsa,
    seed_profile_without_xsa,
)

PROFILE_DIR = REPO_ROOT / "adidt/xsa/config/profiles"


def profile_name(project: str, carrier: str, variant: str, suffix: str = "") -> str:
    """Return the profile name for an HDL design identity."""
    parts = [project, carrier]
    if variant:
        parts.append(variant.lower())
    if suffix:
        parts.append(suffix)
    return re.sub(r"[^a-z0-9_]+", "_", "_".join(parts).lower())


def reference_suffix(reference: str) -> str:
    """Return what a reference DTS name adds beyond its carrier prefix."""
    stem = Path(reference).stem
    return re.sub(r"^zynq(mp)?-[a-z0-9]+-(rev[\w.]+-)?(adv7511-)?", "", stem) or stem


def default_owners(profile_dir: Path) -> dict[tuple[str, str, str], str]:
    """Return ``{(project, carrier, variant): reference}`` of default profiles."""
    found: dict[tuple[str, str, str], str] = {}
    for path in sorted(profile_dir.glob("*.json")):
        design = json.loads(path.read_text()).get("design")
        if isinstance(design, dict) and design.get("default", True):
            key = (design["project"], design["carrier"], design.get("variant") or "")
            found[key] = design.get("reference", "")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--linux", type=Path, required=True, help="Linux checkout")
    parser.add_argument("--xsa-cache", type=Path, required=True)
    parser.add_argument("--kernel-tree", type=Path, help="reuse an exported tree")
    parser.add_argument("--only", action="append", default=[], help="glob of boot dirs")
    parser.add_argument("--skip", action="append", default=[], help="glob of boot dirs")
    parser.add_argument("--out", type=Path, default=PROFILE_DIR)
    parser.add_argument("--report", type=Path, help="write a JSON seeding report")
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument(
        "--base-for",
        action="append",
        default=[],
        metavar="CARRIER=SYSTEM_TOP_DTS",
        help="also seed designs that ship no XSA, borrowing this sdtgen base "
        "tree for their carrier; such profiles are marked unvalidated",
    )
    args = parser.parse_args(argv)

    inventory = json.loads(args.inventory.read_text())
    work = args.work_dir or Path(tempfile.mkdtemp(prefix="adidt-seed-"))
    kernel_tree = args.kernel_tree or export_kernel_tree(
        args.linux, inventory["linux_commit"], work / "kernel"
    )
    owners = default_owners(args.out)
    report: list[dict[str, Any]] = []
    failures = 0

    tasks: list[tuple[dict[str, Any], str, str]] = []
    for design in inventory["designs"]:
        for directory, reference in sorted(design["kuiper_projects"].items()):
            if args.only and not any(fnmatch.fnmatch(directory, g) for g in args.only):
                continue
            if any(fnmatch.fnmatch(directory, g) for g in args.skip):
                continue
            tasks.append((design, directory, reference))

    def seed(task: tuple[dict[str, Any], str, str]) -> Any:
        _, directory, reference = task
        xsa = args.xsa_cache / directory / "system_top.xsa"
        try:
            if not xsa.exists():
                raise SeedError(f"no XSA at {xsa}")
            return seed_profile_for_xsa(
                xsa,
                kernel_tree / reference,
                kernel_tree,
                work / re.sub(r"\W+", "_", directory),
            )
        except Exception as exc:  # noqa: BLE001 - report and carry on
            return exc

    # sdtgen dominates the run time and is a subprocess, so threads suffice.
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        outcomes = list(pool.map(seed, tasks))

    # Naming is order-dependent (the first tree to claim a bitstream's
    # identity becomes its default profile), so it stays sequential.
    for (design, directory, reference), outcome in zip(tasks, outcomes):
        if True:
            record: dict[str, Any] = {
                "kuiper_project": directory,
                "reference": reference,
            }
            report.append(record)
            if isinstance(outcome, Exception):
                record["error"] = f"{type(outcome).__name__}: {outcome}"[:400]
                failures += 1
                print(f"FAIL {directory}: {record['error']}", file=sys.stderr)
                continue
            result, topology = outcome

            identity = (
                topology.hdl_project or design["project"],
                topology.hdl_carrier or design["carrier"],
                topology.hdl_variant,
            )
            # Boards that share a bitstream differ only in the part fitted,
            # which no XSA can tell: the first reference to claim an identity
            # is its default profile, the rest are selectable by name.
            default = owners.setdefault(identity, reference) == reference
            name = profile_name(
                *identity, suffix="" if default else reference_suffix(reference)
            )
            body = result.profile
            profile = {
                "name": name,
                "defaults": {},
                "design": {
                    "project": identity[0],
                    "carrier": identity[1],
                    "variant": identity[2],
                    "default": default,
                    "reference": reference,
                    "kernel_commit": inventory["linux_commit"],
                    "notes": result.notes,
                    "pl": body["pl"],
                    "bus": body["bus"],
                    "root": body["root"],
                    "overlays": body["overlays"],
                },
            }
            (args.out / f"{name}.json").write_text(json.dumps(profile, indent=1) + "\n")
            record.update(
                profile=name,
                default=default,
                pl=len(body["pl"]),
                notes=result.notes,
                unresolved=body["unresolved"],
            )
            print(f"ok   {directory} -> {name} ({len(body['pl'])} PL nodes)")

    bases = dict(item.split("=", 1) for item in args.base_for)
    for design in inventory["designs"]:
        base_dts = bases.get(design["carrier"])
        if design["kuiper_projects"] or not design["kernel_dts"] or not base_dts:
            continue
        # Shortest name first: the plain board file, then its variants.
        references = sorted(design["kernel_dts"], key=lambda r: (len(r), r))
        for index, reference in enumerate(references):
            record = {"design": f"{design['project']}/{design['carrier']}"}
            record["reference"] = reference
            report.append(record)
            try:
                result = seed_profile_without_xsa(
                    kernel_tree / reference, kernel_tree, Path(base_dts)
                )
            except Exception as exc:  # noqa: BLE001 - report and carry on
                record["error"] = f"{type(exc).__name__}: {exc}"[:400]
                failures += 1
                print(f"FAIL {record['design']}: {record['error']}", file=sys.stderr)
                continue
            identity = (design["project"], design["carrier"], "")
            suffix = "" if index == 0 else reference_suffix(reference)
            name = profile_name(*identity, suffix=suffix)
            body = result.profile
            profile = {
                "name": name,
                "defaults": {},
                "design": {
                    "project": identity[0],
                    "carrier": identity[1],
                    "variant": "",
                    "default": index == 0,
                    "validated": False,
                    "reference": reference,
                    "kernel_commit": inventory["linux_commit"],
                    "notes": [
                        "seeded without an XSA: the release ships none for "
                        "this design, so nothing here was checked against a "
                        "bitstream",
                        *result.notes,
                    ],
                    "pl": body["pl"],
                    "bus": body["bus"],
                    "root": body["root"],
                    "overlays": body["overlays"],
                },
            }
            (args.out / f"{name}.json").write_text(json.dumps(profile, indent=1) + "\n")
            record.update(profile=name, pl=len(body["pl"]), notes=result.notes)
            record["unresolved"] = body["unresolved"]
            print(f"ok   {record['design']} -> {name} (unvalidated)")

    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
