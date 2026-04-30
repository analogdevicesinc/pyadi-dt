"""Shared helpers for the XSA visualization renderers.

These utilities are imported by both :mod:`adidt.xsa.viz.clock_graph` and
:mod:`adidt.xsa.viz.wiring_graph` so that both renderers categorize nodes
and shell out to ``dot`` / ``d2`` consistently.
"""

from __future__ import annotations

import re
import shutil
import subprocess


_CATEGORY_TESTS: list[tuple[str, list[str]]] = [
    ("ps_clock", ["zynqmp_clk", "ps7_clkc", "ps_clk", "sys_clk"]),
    ("clock_chip", ["hmc7044", "ad9528", "ad9523", "ad9516", "clk0_"]),
    ("xcvr", ["xcvr"]),
    ("jesd", ["jesd"]),
    ("clkgen", ["clkgen", "clk_gen"]),
    (
        "converter",
        [
            "trx",
            "adrv9009",
            "adrv9004",
            "ad9081",
            "ad9084",
            "ad9172",
            "ad9144",
            "ad9152",
            "ad9680",
            "ad9208",
        ],
    ),
    ("dma", ["dma", "dmac"]),
]


def categorise(label: str) -> str:
    """Return the visual category for *label* using substring heuristics.

    One of ``ps_clock``, ``clock_chip``, ``xcvr``, ``jesd``, ``clkgen``,
    ``converter``, ``dma``, or ``other``.
    """
    low = label.lower()
    for cat, keywords in _CATEGORY_TESTS:
        if any(kw in low for kw in keywords):
            return cat
    return "other"


def short_label(label: str, node_name: str) -> str:
    r"""Return a concise display name (Graphviz form, ``\n`` separator).

    Strips the ``@address`` suffix from *node_name*; collapses to *label*
    alone when label and stripped node-name are identical.
    """
    base = re.sub(r"@[\da-fA-F]+$", "", node_name)
    if base == label:
        return label
    return f"{label}\\n({base})"


def d2_label(label: str, node_name: str) -> str:
    r"""Return a D2 display label (uses ``\n`` as a line separator).

    D2 uses the same ``\n`` escape as Graphviz so this is currently identical
    to :func:`short_label`; kept as a separate function so per-format
    formatting can diverge without touching call sites.
    """
    return short_label(label, node_name)


def run_tool(cmd: list[str], tool: str) -> bool:
    """Run *cmd* if *tool* is on PATH; return ``True`` on success."""
    if shutil.which(tool) is None:
        return False
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return res.returncode == 0
