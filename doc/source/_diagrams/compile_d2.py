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
