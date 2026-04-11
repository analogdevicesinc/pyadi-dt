#!/usr/bin/env python3
"""Compile D2 diagram sources to SVG using pyd2lang-native."""

import re
from pathlib import Path

import d2 as d

D2_DIR = Path(__file__).parent / "d2"
SVG_DIR = Path(__file__).parent / "svg"

DEFAULT_THEMES = ["light", "dark"]

# Per-file overrides; everything else defaults to library="sw" and both themes.
# Optional keys:
#   library: str
#   themes: list[str]
DIAGRAM_CONFIG: dict[str, dict[str, object]] = {}

DEFAULT_CONFIG = {"library": "sw", "themes": DEFAULT_THEMES}


def _strip_inner_svg_dimensions(svg: str) -> str:
    """Remove hardcoded width/height from the inner D2 SVG node."""
    return re.sub(
        r'(<svg\s+id="d2-svg"\s+class="[^"]*"\s+)width="[^"]*"\s+height="[^"]*"\s+',
        r"\1",
        svg,
    )


def _make_canvas_transparent(svg: str) -> str:
    """Make the D2 canvas background rect transparent.

    D2 injects a full-size ``<rect>`` with a ``fill-N7`` CSS class as the
    first child of the inner ``<svg>`` element.  The class maps to an opaque
    fill (``#FFFFFF`` for light themes, ``#1E1E2E`` for DarkMauve) via an
    inline ``<style>`` block.

    We strip both the ``class`` and any ``fill`` attribute from this rect,
    set ``fill="transparent"`` and add an inline ``style`` override so that
    even leftover CSS rules cannot re-paint it.
    """

    def _replacer(match: re.Match[str]) -> str:
        rect_inner = match.group(2)
        # Replace any fill attr with transparent
        if 'fill="' in rect_inner:
            rect_inner = re.sub(r'fill="[^"]+"', 'fill="transparent"', rect_inner)
        else:
            rect_inner += ' fill="transparent"'
        # Remove class to prevent CSS fill override
        rect_inner = re.sub(r'\sclass="[^"]*"', "", rect_inner)
        # Add inline style as final override
        if 'style="' in rect_inner:
            rect_inner = rect_inner.replace('style="', 'style="fill:transparent;')
        else:
            rect_inner += ' style="fill:transparent;"'
        return match.group(1) + rect_inner + "/>"

    return re.sub(
        r'(<svg[^>]*class="d2-[^>]*>\s*<rect)([^>]+)/>',
        _replacer,
        svg,
        count=1,
    )


# Inline style.fill overrides in .d2 sources that don't adapt to dark mode.
# Map each light fill to a dark equivalent that keeps the semantic meaning
# (green = completed, amber = optional, yellow = highlighted) while ensuring
# light text (#e5e5e5) remains readable.
_DARK_FILL_REMAP: dict[str, str] = {
    "#c8e6c9": "#1e3a28",  # light green  → dark green  (completed/output)
    "#fff4e0": "#3a2e1a",  # light amber  → dark amber  (optional)
    "#fff9c4": "#3a3518",  # light yellow → dark yellow  (highlighted)
    "#FFFDE7": "#3a3518",  # light cream  → dark yellow  (notes)
}


def _remap_dark_fills(svg: str) -> str:
    """Replace light inline fills with dark equivalents in dark SVGs."""
    for light, dark in _DARK_FILL_REMAP.items():
        svg = svg.replace(f'fill="{light}"', f'fill="{dark}"')
        svg = svg.replace(f'fill="{light.lower()}"', f'fill="{dark}"')
        svg = svg.replace(f'fill="{light.upper()}"', f'fill="{dark}"')
    return svg


def _force_dark_css(svg: str) -> str:
    """Unwrap the ``@media (prefers-color-scheme:dark)`` block in dark SVGs.

    D2 embeds both light and dark CSS rules in every SVG.  The dark rules
    live inside ``@media screen and (prefers-color-scheme:dark){…}``.

    The Sphinx theme toggles dark mode via a CSS class, **not** the
    ``prefers-color-scheme`` media feature.  If the user's OS is in light
    mode but the Sphinx toggle is dark, the media query never fires and
    text/edge labels fall back to the light-theme fills (e.g. ``#0A0F25``
    or ``#676C7E``) — nearly invisible on dark backgrounds.

    Fix: strip the ``@media`` wrapper so the dark rules sit at the top
    level and override the earlier light rules via normal CSS cascade.
    """
    return re.sub(
        r"@media\s+screen\s+and\s+\(prefers-color-scheme:\s*dark\)\s*\{(.*)\}",
        r"\1",
        svg,
        count=1,
        flags=re.DOTALL,
    )


def main() -> None:
    SVG_DIR.mkdir(exist_ok=True)
    d2_files = sorted(D2_DIR.glob("*.d2"))
    if not d2_files:
        print("No .d2 files found in", D2_DIR)
        return

    for path in d2_files:
        name = path.stem
        cfg = DEFAULT_CONFIG | DIAGRAM_CONFIG.get(name, {})
        library = str(cfg.get("library", "sw"))
        themes = list(cfg.get("themes", DEFAULT_THEMES))
        code = path.read_text()
        print(f"Compiling {path.name} (library={library}, themes={themes}) ...")

        for theme in themes:
            svg = d.compile(code, library=library, theme=theme)
            if svg is None:
                raise RuntimeError(
                    f"d2.compile returned None for {path.name} (theme={theme})"
                )
            svg = _strip_inner_svg_dimensions(svg)
            svg = _make_canvas_transparent(svg)
            if theme == "dark":
                svg = _force_dark_css(svg)
                svg = _remap_dark_fills(svg)
            out = SVG_DIR / f"{name}.{theme}.svg"
            out.write_text(svg)
            print(f"  -> {out.name}")

        # Backward compatibility for existing references.
        if "light" in themes:
            legacy = SVG_DIR / f"{name}.svg"
            legacy.write_text((SVG_DIR / f"{name}.light.svg").read_text())
            print(f"  -> {legacy.name} (alias of {name}.light.svg)")

    print(f"\nDone: {len(d2_files)} diagrams compiled.")


if __name__ == "__main__":
    main()
