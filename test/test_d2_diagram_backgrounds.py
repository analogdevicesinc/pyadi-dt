"""Verify that compiled D2 diagram SVGs have transparent canvas backgrounds.

D2 injects an opaque background rect (``fill-N7`` CSS class) into every SVG.
The compile_d2.py build step must strip this so diagrams sit seamlessly on
both the light and dark Sphinx page backgrounds.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

SVG_DIR = Path(__file__).resolve().parents[1] / "doc" / "source" / "_diagrams" / "svg"

TRANSPARENT_VALUES = {"none", "transparent"}


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _extract_style_fill(style: str) -> str | None:
    for part in style.split(";"):
        key, sep, value = part.partition(":")
        if sep and key.strip().lower() == "fill":
            return value.strip().lower()
    return None


def _css_class_fills(root: ET.Element) -> dict[str, str]:
    """Extract .class { fill: X } from inline <style> blocks."""
    fills: dict[str, str] = {}
    pattern = re.compile(
        r"\.([A-Za-z0-9_-]+)\s*\{[^}]*?\bfill\s*:\s*([^;}\s]+)", re.IGNORECASE
    )
    for node in root.iter():
        if _local_name(node.tag) == "style" and node.text:
            for cls_name, fill in pattern.findall(node.text):
                fills[cls_name.lower()] = fill.strip().lower()
    return fills


def _canvas_fill(svg_text: str) -> str | None:
    """Return the effective fill of the D2 canvas background rect."""
    root = ET.fromstring(svg_text)

    # Find inner <svg> (D2 wraps in an outer + inner SVG)
    ns = {"svg": "http://www.w3.org/2000/svg"}
    inner = root.find("svg:svg", ns)
    if inner is None:
        return None

    rect = inner.find("svg:rect", ns)
    if rect is None:
        return None

    # Priority: inline style > fill attr > CSS class fill
    style_fill = _extract_style_fill(rect.attrib.get("style", ""))
    if style_fill:
        return style_fill

    direct_fill = rect.attrib.get("fill", "").strip().lower() or None
    if direct_fill:
        return direct_fill

    class_fills = _css_class_fills(root)
    for cls in rect.attrib.get("class", "").split():
        mapped = class_fills.get(cls.strip().lower())
        if mapped:
            return mapped

    return None


def _svg_files() -> list[Path]:
    if not SVG_DIR.is_dir():
        return []
    return sorted(SVG_DIR.glob("*.svg"))


@pytest.fixture(scope="module")
def svg_files() -> list[Path]:
    files = _svg_files()
    if not files:
        pytest.skip("No compiled SVG files found — run `nox -s d2_diagrams` first")
    return files


def test_all_diagram_svgs_have_transparent_background(svg_files: list[Path]) -> None:
    """Every compiled D2 SVG must have a transparent canvas rect."""
    issues: list[str] = []
    for svg_path in svg_files:
        fill = _canvas_fill(svg_path.read_text(encoding="utf-8"))
        if fill is not None and fill not in TRANSPARENT_VALUES:
            issues.append(f"{svg_path.name}: canvas fill is {fill!r}")

    assert not issues, "SVGs with non-transparent backgrounds:\n" + "\n".join(issues)


def test_dark_svgs_have_no_opaque_white_fills(svg_files: list[Path]) -> None:
    """Dark-variant SVGs must not contain white/light fills on visible shapes."""
    disallowed = {"#ffffff", "#fff", "white", "#f5f5f5"}
    non_rendered = {"defs", "mask", "clippath", "marker"}
    shape_tags = {"rect", "path", "polygon", "circle", "ellipse"}

    dark_svgs = [f for f in svg_files if ".dark." in f.name]
    assert dark_svgs, "No .dark.svg files found"

    issues: list[str] = []
    for svg_path in dark_svgs:
        root = ET.fromstring(svg_path.read_text(encoding="utf-8"))
        bad_fills: list[str] = []

        def walk(node: ET.Element, hidden: int = 0) -> None:
            name = _local_name(node.tag).lower()
            next_hidden = hidden + 1 if name in non_rendered else hidden
            if not hidden and name in shape_tags:
                fill = node.attrib.get("fill")
                if fill is None:
                    fill = _extract_style_fill(node.attrib.get("style", ""))
                if fill and fill.strip().lower() in disallowed:
                    bad_fills.append(fill.strip().lower())
            for child in node:
                walk(child, next_hidden)

        walk(root)
        if bad_fills:
            values = ", ".join(sorted(set(bad_fills)))
            issues.append(f"{svg_path.name}: disallowed fills {values}")

    assert not issues, "Dark SVGs with white/light fills:\n" + "\n".join(issues)


def test_light_and_dark_variants_exist(svg_files: list[Path]) -> None:
    """Every diagram should have both .light.svg and .dark.svg variants."""
    names = {f.name for f in svg_files}
    stems = {f.stem.rsplit(".", 1)[0] for f in svg_files if ".light." in f.name}

    missing: list[str] = []
    for stem in sorted(stems):
        if f"{stem}.dark.svg" not in names:
            missing.append(f"{stem}: missing .dark.svg variant")

    assert not missing, "Missing dark variants:\n" + "\n".join(missing)
