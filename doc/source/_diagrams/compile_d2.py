#!/usr/bin/env python3
"""Compile D2 diagram sources to SVG using pyd2lang-native."""

import re
from pathlib import Path

import d2

D2_DIR = Path(__file__).parent / "d2"
SVG_DIR = Path(__file__).parent / "svg"

# Per-file overrides; everything else defaults to library="sw", theme="light"
DIAGRAM_CONFIG: dict[str, dict[str, str]] = {}

DEFAULT_CONFIG = {"library": "sw", "theme": "light"}


def main() -> None:
    SVG_DIR.mkdir(exist_ok=True)
    d2_files = sorted(D2_DIR.glob("*.d2"))
    if not d2_files:
        print("No .d2 files found in", D2_DIR)
        return

    for path in d2_files:
        name = path.stem
        cfg = DIAGRAM_CONFIG.get(name, DEFAULT_CONFIG)
        code = path.read_text()
        print(f"Compiling {path.name} (library={cfg['library']}) ... ", end="")
        svg = d2.compile(code, library=cfg["library"], theme=cfg["theme"])
        if svg is None:
            raise RuntimeError(f"d2.compile returned None for {path.name}")
        # Strip hardcoded width/height from the inner <svg id="d2-svg"> so
        # the image scales to the CSS width set in the RST directives.
        svg = re.sub(
            r'(<svg\s+id="d2-svg"\s+)class="[^"]*"\s+width="[^"]*"\s+height="[^"]*"\s+',
            r"\1",
            svg,
        )
        out = SVG_DIR / f"{name}.svg"
        out.write_text(svg)
        print(f"-> {out.name}")

    print(f"\nDone: {len(d2_files)} diagrams compiled.")


if __name__ == "__main__":
    main()
