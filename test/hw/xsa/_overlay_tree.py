"""Prepare a test base in which the overlay owns its newly declared nodes."""

from __future__ import annotations

import subprocess
from pathlib import Path


def prepare_overlay_base(base: Path, overlay: Path) -> None:
    """Remove overlay-created children and their symbols from a compiled base.

    Generated overlays update existing PL targets but create SPI children.
    Booting the merged tree would give those children duplicate phandles.
    This mutates only the supplied private DTB, before it is booted. Drivers
    must remain unloaded until the overlay restores the complete topology.
    """

    def read(tree, *args, optional=False):
        result = subprocess.run(
            ["fdtget", str(tree), *args],
            capture_output=True,
            text=True,
        )
        if optional and result.returncode:
            return ""
        result.check_returncode()
        return result.stdout.strip()

    fixups = {}
    for label in read(overlay, "-p", "/__fixups__", optional=True).splitlines():
        for location in read(overlay, "-t", "s", "/__fixups__", label).split():
            fixups[location] = label

    targets = []
    removals = []
    for fragment in read(overlay, "-l", "/").splitlines():
        if not fragment.startswith("fragment@"):
            continue
        fragment_path = f"/{fragment}"
        target = read(overlay, "-t", "s", fragment_path, "target-path", optional=True)
        if not target:
            label = fixups.get(f"{fragment_path}:target:0")
            assert label, f"Unsupported overlay target: {fragment_path}"
            target = read(base, "-t", "s", "/__symbols__", label)
        targets.append(target)
        existing = read(base, "-l", target).splitlines()
        for child in read(overlay, "-l", f"{fragment_path}/__overlay__").splitlines():
            if child in existing:
                removals.append(f"{target.rstrip('/')}/{child}")

    def inside(path, ancestor):
        return path == ancestor or path.startswith(ancestor + "/")

    assert not any(inside(target, node) for target in targets for node in removals), (
        "An overlay-created node is also an external fragment target"
    )
    for symbol in read(base, "-p", "/__symbols__").splitlines():
        path = read(base, "-t", "s", "/__symbols__", symbol)
        if any(inside(path, node) for node in removals):
            subprocess.run(
                ["fdtput", "-d", str(base), "/__symbols__", symbol], check=True
            )
    for node in sorted(set(removals), key=len, reverse=True):
        subprocess.run(["fdtput", "-r", str(base), node], check=True)
