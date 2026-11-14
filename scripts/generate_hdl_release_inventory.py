#!/usr/bin/env python3
"""Generate the per-release inventory of Xilinx HDL reference designs.

Walks an ``analogdevicesinc/hdl`` git ref, lists every Xilinx
``projects/<project>/<carrier>`` design, and joins each one to:

* the kernel reference device trees in an ``analogdevicesinc/linux`` git ref
  (primarily through the ``hdl_project: <project/carrier>`` header tag), and
* the Kuiper boot-partition project directories that ship a
  ``bootgen_sysfiles.tgz`` (and therefore an XSA) for it.

The result records which pyadi-dt profile and builder (if any) cover each
design.  It is written to ``adidt/xsa/config/hdl_<release>_designs.json`` and
can also refresh ``adidt/xsa/config/kuiper_boards.json``.

Both repositories are read with ``git`` plumbing, so no checkout of the
release branch is needed -- only that the ref has been fetched.

Example::

    python scripts/generate_hdl_release_inventory.py \\
        --hdl ~/dev/hdl --hdl-ref origin/hdl_2026_r1 \\
        --linux ~/dev/linux --linux-ref origin/xlnx/release/v6.12.y-2026r1 \\
        --kuiper-tarball ~/.cache/adidt/kuiper/2026_r1_latest_boot_partition.tar.gz \\
        --release 2026_r1 --kuiper-boards
"""

from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "adidt" / "xsa" / "config"

# Carriers that are not Xilinx parts; everything else under projects/ is.
NON_XILINX_CARRIERS = {
    "a10gx",
    "a10soc",
    "a5gt",
    "a5soc",
    "c5soc",
    "de10nano",
    "fm87",
    "lfcpnx",
    "s10soc",
}
# projects/ entries that are infrastructure rather than board designs.
NON_DESIGN_PROJECTS = {"common", "scripts", "xcvr_wizard"}

CARRIER_ARCH = {
    "ac701": "microblaze",
    "kc705": "microblaze",
    "kcu105": "microblaze",
    "vc707": "microblaze",
    "vc709": "microblaze",
    "vcu118": "microblaze",
    "vcu128": "microblaze",
    "zed": "arm",
    "zc702": "arm",
    "zc706": "arm",
    "coraz7s": "arm",
    "ccbob_cmos": "arm",
    "ccbob_lvds": "arm",
    "ccfmc_lvds": "arm",
    "zcu102": "arm64",
    "k26": "arm64",
    "kv260": "arm64",
    "vck190": "arm64",
    "vmk180": "arm64",
    "vpk180": "arm64",
    "adrv2crr_fmc": "arm64",
    "adrv2crr_fmcomms8": "arm64",
    "adrv2crr_fmcxmwbr1": "arm64",
}

# Kernel DTS basename prefix used for each carrier (name-based join fallback).
CARRIER_DTS_PREFIX = {
    "zed": "zynq-zed-adv7511",
    "zc702": "zynq-zc702-adv7511",
    "zc706": "zynq-zc706-adv7511",
    "coraz7s": "zynq-coraz7s",
    "zcu102": "zynqmp-zcu102-rev10",
    "vck190": "versal-vck190-reva",
    "vmk180": "versal-vmk180-reva",
    "vpk180": "versal-vpk180-reva",
    "vcu118": "vcu118",
    "kcu105": "kcu105",
    "kc705": "kc705",
    "k26": "zynqmp-k26",
    "kv260": "zynqmp-kv260",
}

# pyadi-dt platform name used in profile names, when it differs from the carrier.
CARRIER_PLATFORM = {
    "adrv2crr_fmc": "zu11eg",
    "adrv2crr_fmcomms8": "zu11eg",
    "adrv2crr_fmcxmwbr1": "zu11eg",
}

# HDL project -> pyadi-dt converter families (first entry is the primary one).
PROJECT_FAMILIES: dict[str, list[str]] = {
    "ad9081_fmca_ebz": ["ad9081"],
    "ad9082_fmca_ebz": ["ad9082"],
    "ad9083_evb": ["ad9083"],
    "ad9084_ebz": ["ad9084"],
    "dac_fmc_ebz": ["ad9172"],
    "adrv9001": ["adrv9002", "adrv9003"],
    "adrv9009": ["adrv9009", "adrv9008"],
    "adrv9009zu11eg": ["adrv9009"],
    "adrv9026": ["adrv9025"],
    "adrv904x": ["adrv9040"],
    "adrv9371x": ["adrv937x"],
    "daq2": ["fmcdaq2"],
    "daq3": ["fmcdaq3"],
}

# pyadi-dt family -> builder class that renders it (None: generic rendering only).
FAMILY_BUILDERS: dict[str, str | None] = {
    "ad9081": "AD9081Builder",
    "ad9082": "AD9081Builder",
    "ad9083": None,
    "ad9084": "AD9084Builder",
    "ad9172": "AD9172Builder",
    "adrv9002": None,
    "adrv9003": "ADRV9003Builder",
    "adrv9008": "ADRV9009Builder",
    "adrv9009": "ADRV9009Builder",
    "adrv9025": "ADRV9009Builder",
    "adrv9040": "ADRV9040Builder",
    "adrv937x": "ADRV937xBuilder",
    "fmcdaq2": "FMCDAQ2Builder",
    "fmcdaq3": "FMCDAQ3Builder",
}

# Joins the tag and name heuristics cannot find.  Keys are "project/carrier";
# values are kernel DTS basenames (without ".dts").
DTS_OVERRIDES: dict[str, list[str]] = {}

_PROJECT_SUFFIX_RE = re.compile(
    r"_(fmca_ebz|fmc_evb|fmc_ebz|fmcz|fmc|evb|ebz|sdz|ardz|asdz)$"
)
_DTS_DIRS = (
    "arch/arm/boot/dts/xilinx",
    "arch/arm64/boot/dts/xilinx",
    "arch/microblaze/boot/dts",
)


def _git(repo: Path, *args: str, check: bool = True) -> str:
    """Run a read-only git command in *repo* and return its stdout."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def project_stem(project: str) -> str:
    """Return *project* without its board-form-factor suffix (``_fmc``, ``_evb``...)."""
    prev = None
    stem = project
    while prev != stem:
        prev = stem
        stem = _PROJECT_SUFFIX_RE.sub("", stem)
    return stem


def list_hdl_designs(hdl: Path, ref: str) -> list[tuple[str, str]]:
    """Return sorted Xilinx ``(project, carrier)`` pairs present in the HDL ref."""
    out = _git(hdl, "ls-tree", "-r", "--name-only", ref, "projects/")
    pairs = set()
    for line in out.splitlines():
        parts = line.split("/")
        if len(parts) != 4 or parts[3] != "system_project.tcl":
            continue
        _, project, carrier, _ = parts
        if project in NON_DESIGN_PROJECTS or carrier in NON_XILINX_CARRIERS:
            continue
        pairs.add((project, carrier))
    return sorted(pairs)


def classify_projects(hdl: Path, ref: str, projects: set[str]) -> dict[str, str]:
    """Classify each HDL project by the kind of data path its block design uses."""

    def grep(pattern: str) -> set[str]:
        out = _git(
            hdl,
            "grep",
            "-l",
            "-I",
            "-E",
            pattern,
            ref,
            "--",
            "projects/*.tcl",
            check=False,
        )
        hits = set()
        for line in out.splitlines():
            path = line.split(":", 1)[1] if ":" in line else line
            parts = path.split("/")
            if len(parts) > 2:
                hits.add(parts[1])
        return hits

    jesd = grep(r"axi_jesd204_(rx|tx)|adi_axi_jesd204_(rx|tx)_create")
    trx = grep(r"ad_ip_instance axi_(ad9361|adrv9001)")
    spi_engine = grep(r"spi_engine")
    i3c = grep(r"i3c_controller")
    parallel = grep(r"ad_ip_instance axi_(ad[0-9]|adaq|ada[0-9]|ltc|pulsar)")

    def direct(project: str) -> str:
        if re.match(r"adrv936[14]z", project):
            return "som"
        if project in jesd:
            return "jesd"
        if project in trx:
            return "transceiver_lvds"
        if project in spi_engine:
            return "spi_engine"
        if project in i3c:
            return "i3c"
        if project in parallel:
            return "parallel_if"
        return "misc"

    # Projects that only re-use another project's block design (e.g. ad9082
    # sourcing ad9081's system_bd.tcl) inherit that project's class.
    sourced: dict[str, set[str]] = {}
    out = _git(
        hdl,
        "grep",
        "-I",
        "-E",
        r"^\s*source .*projects/[a-z0-9_]+/",
        ref,
        "--",
        "projects/*.tcl",
        check=False,
    )
    for line in out.splitlines():
        match = re.match(r"[^:]+:projects/([^/]+)/[^:]*:.*projects/([a-z0-9_]+)/", line)
        if match and match.group(2) not in NON_DESIGN_PROJECTS:
            sourced.setdefault(match.group(1), set()).add(match.group(2))

    classes = {}
    for project in projects:
        cls = direct(project)
        if cls == "misc":
            inherited = {direct(other) for other in sourced.get(project, ())}
            inherited.discard("misc")
            if len(inherited) == 1:
                cls = inherited.pop()
        classes[project] = cls
    return classes


def list_kernel_dts(linux: Path, ref: str) -> dict[str, str]:
    """Return ``{dts_basename: repo_path}`` for the Xilinx/MicroBlaze DTS dirs."""
    result = {}
    for dts_dir in _DTS_DIRS:
        out = _git(linux, "ls-tree", "--name-only", ref, dts_dir + "/")
        for line in out.splitlines():
            if line.endswith(".dts"):
                result[Path(line).stem] = line
    return result


def kernel_hdl_tags(linux: Path, ref: str) -> dict[str, str]:
    """Return ``{dts_basename: "project/carrier"}`` from ``hdl_project:`` tags."""
    out = _git(
        linux,
        "grep",
        "-I",
        "hdl_project:",
        ref,
        "--",
        *[f"{d}/*.dts" for d in _DTS_DIRS],
        check=False,
    )
    tags = {}
    for line in out.splitlines():
        match = re.match(r"[^:]+:([^:]+\.dts):.*hdl_project:\s*<?\s*([^>\s]+)", line)
        if not match:
            continue
        tag = match.group(2).strip("/").lower()
        if "/" in tag:
            tags[Path(match.group(1)).stem] = tag
    return tags


def _stem_regex(stem: str) -> re.Pattern[str]:
    """Regex matching *stem* in a DTS name; ``x`` is a digit wildcard, ``_`` ~ ``-``."""
    body = "".join(
        r"[0-9x]" if ch == "x" else (r"[-_]?" if ch == "_" else re.escape(ch))
        for ch in stem
    )
    return re.compile(rf"(?:^|[-_]){body}(?:[-_]|$)")


def join_kernel_dts(
    designs: list[tuple[str, str]],
    dts_files: dict[str, str],
    tags: dict[str, str],
) -> dict[tuple[str, str], tuple[list[str], str | None]]:
    """Map each design to ``(sorted DTS basenames, join method)``."""
    design_set = set(designs)
    by_stem: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for project, carrier in designs:
        by_stem.setdefault((project_stem(project), carrier), []).append(
            (project, carrier)
        )

    joined: dict[tuple[str, str], set[str]] = {d: set() for d in designs}
    method: dict[tuple[str, str], str] = {}

    for dts, tag in tags.items():
        project, carrier = tag.split("/", 1)
        key = (project, carrier)
        if key in design_set:
            joined[key].add(dts)
            method.setdefault(key, "tag")
            continue
        candidates = by_stem.get((project_stem(project), carrier), [])
        if len(candidates) == 1:
            joined[candidates[0]].add(dts)
            method.setdefault(candidates[0], "tag-fuzzy")

    for design in designs:
        project, carrier = design
        override = DTS_OVERRIDES.get(f"{project}/{carrier}")
        if override:
            joined[design] = {d for d in override if d in dts_files}
            method[design] = "override"
            continue
        if joined[design]:
            continue
        prefix = CARRIER_DTS_PREFIX.get(carrier)
        if not prefix:
            continue
        pattern = _stem_regex(project_stem(project))
        for dts in dts_files:
            if not dts.startswith(prefix):
                continue
            if pattern.search(dts[len(prefix) :]):
                joined[design].add(dts)
        if joined[design]:
            method[design] = "name"

    return {d: (sorted(joined[d]), method.get(d)) for d in designs}


def read_kuiper_archive(tarball: Path | None) -> tuple[list[str], set[str]]:
    """Read the boot-partition archive in one pass.

    Returns ``(member paths, directories whose bootgen_sysfiles.tgz holds an
    XSA)``.  Versal boot directories ship a PDI instead of an XSA, so having a
    ``bootgen_sysfiles.tgz`` is not enough to count as an XSA source.
    """
    if tarball is None:
        return [], set()
    suffix = "/bootgen_sysfiles.tgz"
    members: list[str] = []
    with_xsa: set[str] = set()
    with tarfile.open(tarball, "r:gz") as outer:
        for member in outer:
            name = member.name.removeprefix("./").rstrip("/")
            members.append(name)
            if not name.endswith(suffix):
                continue
            nested = outer.extractfile(member)
            if nested is None:
                continue
            with tarfile.open(fileobj=io.BytesIO(nested.read()), mode="r:gz") as inner:
                if any(n.endswith(".xsa") for n in inner.getnames()):
                    with_xsa.add(name[: -len(suffix)])
    return members, with_xsa


def list_kuiper_projects(members: list[str]) -> list[str]:
    """Return boot-partition directories that contain a ``bootgen_sysfiles.tgz``."""
    suffix = "/bootgen_sysfiles.tgz"
    return sorted({m[: -len(suffix)] for m in members if m.endswith(suffix)})


def list_kuiper_boards(members: list[str]) -> list[str]:
    """Return every top-level board directory in the boot partition."""
    tops = {m.split("/")[0] for m in members if "/" in m}
    return sorted(
        t for t in tops if t != "extlinux" and not re.search(r"[-_]common$", t)
    )


def _dts_key(name: str) -> str:
    """Normalise a DTS / Kuiper directory name for matching."""
    return name.lower().replace("_", "-").replace("-jesd204-fsm", "")


def kuiper_dts_candidates(kuiper_project: str, members: list[str]) -> list[str]:
    """Kernel DTS basenames a Kuiper project directory may correspond to.

    A boot directory is named after its device tree, but variants are also
    stored as ``<board>/<variant>`` and as per-DTB subdirectories that share
    the parent's boot files.
    """
    parts = kuiper_project.split("/")
    top, last = parts[0], parts[-1]
    candidates = []
    if len(parts) > 1:
        candidates.append(f"{top}-{last}")
    candidates.append(last)
    prefix = kuiper_project + "/"
    nested = sorted(
        {m[len(prefix) :].split("/")[0] for m in members if m.startswith(prefix)}
    )
    nested = [n for n in nested if "." not in n]
    candidates.extend(nested)
    # e.g. zynq-coraz7s-ad719x/ad7190 -> zynq-coraz7s-ad7190
    candidates.extend(f"{top.rsplit('-', 1)[0]}-{n}" for n in nested)
    candidates.append(top)
    return candidates


def join_kuiper(
    kuiper_projects: list[str],
    members: list[str],
    dts_join: dict[tuple[str, str], tuple[list[str], str | None]],
) -> dict[tuple[str, str], dict[str, str]]:
    """Map each design to ``{kuiper project directory: matched DTS basename}``."""
    dts_to_design = {}
    for design, (dts_names, _) in dts_join.items():
        for dts in dts_names:
            dts_to_design[_dts_key(dts)] = (design, dts)
    nested_projects = set(kuiper_projects)
    result: dict[tuple[str, str], dict[str, str]] = {}
    for kuiper_project in kuiper_projects:
        for candidate in kuiper_dts_candidates(kuiper_project, members):
            # A nested directory that is itself a boot project is joined on its own.
            if f"{kuiper_project}/{candidate}" in nested_projects:
                continue
            match = dts_to_design.get(_dts_key(candidate))
            if match is not None:
                design, dts = match
                result.setdefault(design, {})[kuiper_project] = dts
                break
    return result


def available_profiles() -> list[str]:
    """Return names of the built-in XSA profiles shipped in this checkout."""
    return sorted(p.stem for p in (CONFIG_DIR / "profiles").glob("*.json"))


def resolve_support(
    project: str, carrier: str, profiles: list[str]
) -> tuple[str | None, list[str], str | None, str]:
    """Return ``(profile, extra_profiles, builder, status)`` for a design."""
    platform = CARRIER_PLATFORM.get(carrier, carrier)
    matches: list[tuple[str, str]] = []
    for family in PROJECT_FAMILIES.get(project, []):
        base = f"{family}_{platform}"
        for profile in profiles:
            if profile == base or profile.startswith(base + "_"):
                matches.append((profile, family))
    if not matches:
        return None, [], None, "unsupported"
    profile, family = matches[0]
    builder = FAMILY_BUILDERS.get(family)
    status = "full" if builder else "profile_only"
    return profile, [m[0] for m in matches[1:]], builder, status


def build_inventory(args: argparse.Namespace) -> dict[str, Any]:
    """Assemble the inventory document from the HDL, Linux and Kuiper inputs."""
    designs = list_hdl_designs(args.hdl, args.hdl_ref)
    classes = classify_projects(args.hdl, args.hdl_ref, {p for p, _ in designs})
    dts_files = list_kernel_dts(args.linux, args.linux_ref)
    dts_join = join_kernel_dts(
        designs, dts_files, kernel_hdl_tags(args.linux, args.linux_ref)
    )
    members, with_xsa = read_kuiper_archive(args.kuiper_tarball)
    kuiper_join = join_kuiper(list_kuiper_projects(members), members, dts_join)
    profiles = available_profiles()

    entries = []
    for project, carrier in designs:
        dts_names, join_method = dts_join[(project, carrier)]
        joined = sorted(kuiper_join.get((project, carrier), {}).items())
        kuiper = {d: dts_files[dts] for d, dts in joined if d in with_xsa}
        no_xsa = [d for d, _ in joined if d not in with_xsa]
        profile, extra_profiles, builder, status = resolve_support(
            project, carrier, profiles
        )
        reasons = []
        if not dts_names:
            reasons.append("no kernel reference DTS found for this design")
        if not kuiper:
            reasons.append(
                "Kuiper boot files hold no XSA (PDI only)"
                if no_xsa
                else "no boot files for this design in the Kuiper boot partition"
            )
        entries.append(
            {
                "project": project,
                "carrier": carrier,
                "arch": CARRIER_ARCH.get(carrier, "unknown"),
                "class": classes[project],
                "kernel_dts": [dts_files[d] for d in dts_names],
                "kernel_dts_join": join_method,
                "kuiper_projects": kuiper,
                "kuiper_projects_without_xsa": no_xsa,
                "profile": profile,
                "extra_profiles": extra_profiles,
                "builder": builder,
                "status": status,
                "reason": "; ".join(reasons) or None,
            }
        )

    return {
        "release": args.release,
        "kuiper_boards": list_kuiper_boards(members),
        "hdl_ref": args.hdl_ref,
        "hdl_commit": _git(args.hdl, "rev-parse", args.hdl_ref).strip(),
        "linux_ref": args.linux_ref,
        "linux_commit": _git(args.linux, "rev-parse", args.linux_ref).strip(),
        "designs": entries,
    }


def _kuiper_platform_arch(name: str) -> tuple[str, str]:
    """Infer ``(platform, arch)`` from a top-level Kuiper directory name."""
    rules = (
        (r"^socfpga_arria10", "arria10", "arm"),
        (r"^socfpga_cyclone5", "cyclone5", "arm"),
        (r"^socfpga_stratix10", "stratix10", "arm64"),
        (r"^versal-(\w+?)-", None, "arm64"),
        (r"^zynq-adrv936\d-(z\d+)", None, "arm"),
        (r"^zynqmp-adrv9009-(zu11eg)", None, "arm64"),
        (r"^zynqmp-jupiter", "jupiter_sdr", "arm64"),
        (r"^zynqmp-(\w+?)-", None, "arm64"),
        (r"^zynq-(\w+?)(?:-|$)", None, "arm"),
        (r"_(zed)$", None, "arm"),
    )
    for pattern, platform, arch in rules:
        match = re.search(pattern, name)
        if match:
            return platform or match.group(1), arch
    return "unknown", "unknown"


def build_kuiper_boards(
    inventory: dict[str, Any], board_dirs: list[str], previous: dict[str, Any]
) -> dict[str, Any]:
    """Build the ``kuiper_boards.json`` document for the inventory's release.

    Entries already present in *previous* keep their hand-curated fields;
    new directories are filled in from the inventory.
    """
    by_kuiper_top: dict[str, dict[str, Any]] = {}
    for entry in inventory["designs"]:
        for kuiper_project in (
            *entry["kuiper_projects"],
            *entry["kuiper_projects_without_xsa"],
        ):
            by_kuiper_top.setdefault(kuiper_project.split("/")[0], entry)

    old_boards = previous.get("boards", {})
    boards = {}
    for top in board_dirs:
        if top in old_boards:
            boards[top] = old_boards[top]
            continue
        platform, arch = _kuiper_platform_arch(top)
        design = by_kuiper_top.get(top)
        converter, profile, builder, status = "unknown", None, None, "unsupported"
        if design is not None:
            families = PROJECT_FAMILIES.get(design["project"], [])
            # One HDL project can serve several parts (dac_fmc_ebz builds
            # AD9144/AD9154/AD9172 boards), so only trust the design's profile
            # when the directory itself names the profile's family, and never
            # promote an entry nobody has verified beyond "profile_only".
            family = next((f for f in families if f in top.lower()), None)
            stem = project_stem(design["project"])
            converter = family or (
                stem if re.search(r"\d", stem) else design["project"]
            )
            if family and design["profile"]:
                profile, builder = design["profile"], design["builder"]
                status = "profile_only"
        boards[top] = {
            "converter": converter,
            "platform": platform,
            "arch": arch,
            "profile": profile,
            "board_class": None,
            "builder": builder,
            "status": status,
        }
    return {"release": inventory["release"], "boards": boards}


def main() -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--hdl", type=Path, required=True, help="HDL git repository")
    parser.add_argument("--hdl-ref", required=True, help="HDL git ref of the release")
    parser.add_argument("--linux", type=Path, required=True, help="Linux git repo")
    parser.add_argument("--linux-ref", required=True, help="Linux ref of the release")
    parser.add_argument(
        "--release", required=True, help="Kuiper release name, e.g. 2026_r1"
    )
    parser.add_argument(
        "--kuiper-tarball",
        type=Path,
        required=True,
        help="Kuiper latest_boot_partition.tar.gz of the release",
    )
    parser.add_argument("--out", type=Path, help="Inventory output path")
    parser.add_argument(
        "--kuiper-boards",
        action="store_true",
        help="Also regenerate adidt/xsa/config/kuiper_boards.json",
    )
    args = parser.parse_args()

    inventory = build_inventory(args)
    board_dirs = inventory.pop("kuiper_boards")
    out = args.out or CONFIG_DIR / f"hdl_{args.release.lower()}_designs.json"
    out.write_text(json.dumps(inventory, indent=2) + "\n")

    designs = inventory["designs"]
    print(f"{out}: {len(designs)} designs")
    for status in ("full", "profile_only", "unsupported"):
        print(f"  {status:>13}: {sum(d['status'] == status for d in designs)}")
    print(f"  without kernel DTS: {sum(not d['kernel_dts'] for d in designs)}")
    print(f"  without Kuiper XSA: {sum(not d['kuiper_projects'] for d in designs)}")

    if args.kuiper_boards:
        boards_path = CONFIG_DIR / "kuiper_boards.json"
        previous = json.loads(boards_path.read_text()) if boards_path.exists() else {}
        boards = build_kuiper_boards(inventory, board_dirs, previous)
        boards_path.write_text(json.dumps(boards, indent=2) + "\n")
        print(f"{boards_path}: {len(boards['boards'])} boards")


if __name__ == "__main__":
    main()
