#!/usr/bin/env python3
# scripts/embed_d3.py
"""Download and inline D3.js v7.9.0 into adidt/xsa/viz/d3_bundle.js.

Run once (or to update the pinned version):
    python scripts/embed_d3.py
"""

import urllib.request
from pathlib import Path

D3_URL = "https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"
OUTPUT = Path(__file__).parent.parent / "adidt" / "xsa" / "viz" / "d3_bundle.js"


def main():
    print(f"Downloading D3.js from {D3_URL}...")
    with urllib.request.urlopen(D3_URL) as resp:
        content = resp.read().decode("utf-8")
    OUTPUT.write_text(content)
    print(f"Written {len(content)} bytes to {OUTPUT}")


if __name__ == "__main__":
    main()
