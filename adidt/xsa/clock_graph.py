# adidt/xsa/clock_graph.py
"""Generate Graphviz clock-tree diagrams from merged DTS files.

Parses ``clocks``, ``clock-names``, and ``clock-output-names`` properties out
of a merged DTS string and produces a directed DOT graph showing the clock
distribution path from provider to consumer.  An SVG is rendered alongside
the DOT file when the ``dot`` system tool is available.
"""

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class _DtsClockNode:
    """Minimal representation of a DTS node relevant to clock topology."""

    label: str
    node_name: str
    # (provider_label, clock_index) pairs from the ``clocks`` property
    clocks: list[tuple[str, int]] = field(default_factory=list)
    # Names matching each entry in ``clocks``, from ``clock-names``
    clock_names: list[str] = field(default_factory=list)
    # Declared output clock names, from ``clock-output-names``
    clock_output_names: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Node categorisation helpers
# ---------------------------------------------------------------------------

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

_CATEGORY_STYLE: dict[str, dict[str, str]] = {
    "ps_clock": {"fillcolor": "#7a3800", "shape": "ellipse"},
    "clock_chip": {"fillcolor": "#1a3d5c", "shape": "box"},
    "xcvr": {"fillcolor": "#4a1a5c", "shape": "box"},
    "jesd": {"fillcolor": "#1a4a20", "shape": "box"},
    "clkgen": {"fillcolor": "#1a4a4a", "shape": "box"},
    "converter": {"fillcolor": "#5c1a1a", "shape": "box"},
    "dma": {"fillcolor": "#3a3a3a", "shape": "box"},
    "other": {"fillcolor": "#2a2a2a", "shape": "box"},
}

_CLOCK_NAME_EDGE_STYLE: dict[str, str] = {
    "s_axi_aclk": 'color="#555555" style=dashed fontcolor="#666666"',
    "device_clk": 'color="#4a9eff" fontcolor="#4a9eff"',
    "lane_clk": 'color="#44cc44" fontcolor="#44cc44"',
    "conv": 'color="#cc9944" fontcolor="#cc9944"',
    "div40": 'color="#cc9944" style=dashed fontcolor="#996633"',
    "sampl_clk": 'color="#cc44cc" fontcolor="#cc44cc"',
}


def _categorise(label: str) -> str:
    """Return the category string for *label* using simple substring heuristics."""
    low = label.lower()
    for cat, keywords in _CATEGORY_TESTS:
        if any(kw in low for kw in keywords):
            return cat
    return "other"


def _node_style(label: str) -> str:
    """Return a Graphviz attribute string for the node identified by *label*."""
    style = _CATEGORY_STYLE.get(_categorise(label), _CATEGORY_STYLE["other"])
    parts = [f'{k}="{v}"' for k, v in style.items()]
    return " ".join(parts)


def _edge_style(clock_name: str) -> str:
    """Return Graphviz edge attributes for an edge labelled *clock_name*."""
    return _CLOCK_NAME_EDGE_STYLE.get(clock_name, 'color="#888888" fontcolor="#888888"')


def _short_label(label: str, node_name: str) -> str:
    """Return a concise display name combining *label* and a shortened *node_name*."""
    # Drop @address suffix for readability
    base = re.sub(r"@[\da-fA-F]+$", "", node_name)
    if base == label:
        return label
    return f"{label}\\n({base})"


# ---------------------------------------------------------------------------
# DTS parser
# ---------------------------------------------------------------------------


class _DtsParser:
    """Extracts clock-related properties from a merged DTS text.

    Handles both standard labeled-node declarations::

        label: node-name@addr { ... }

    and DTS overlay reference blocks::

        &label { ... }
    """

    # label : node-name[@addr] {
    _NODE_HEADER = re.compile(
        r"(\w+)\s*:\s*([\w.-]+(?:@[\da-fA-F]+)?)\s*\{", re.MULTILINE
    )
    # &label {  (overlay reference block — no node-name@addr)
    _REF_HEADER = re.compile(r"&(\w+)\s*\{", re.MULTILINE)

    def parse(self, dts: str) -> list[_DtsClockNode]:
        """Return a list of :class:`_DtsClockNode` objects parsed from *dts*."""
        seen: set[str] = set()
        nodes: list[_DtsClockNode] = []

        # Standard labeled declarations
        for m in self._NODE_HEADER.finditer(dts):
            label = m.group(1)
            node_name = m.group(2)
            node = self._make_node(dts, m.end(), label, node_name)
            if node:
                seen.add(label)
                nodes.append(node)

        # Overlay reference blocks  &label { ... }
        for m in self._REF_HEADER.finditer(dts):
            label = m.group(1)
            node = self._make_node(dts, m.end(), label, label)
            if node:
                if label in seen:
                    # Merge clock info into the existing entry
                    existing = next(n for n in nodes if n.label == label)
                    existing.clocks.extend(
                        c for c in node.clocks if c not in existing.clocks
                    )
                    if not existing.clock_names and node.clock_names:
                        existing.clock_names = node.clock_names
                    if not existing.clock_output_names and node.clock_output_names:
                        existing.clock_output_names = node.clock_output_names
                else:
                    seen.add(label)
                    nodes.append(node)

        return nodes

    def _make_node(
        self, dts: str, block_start: int, label: str, node_name: str
    ) -> "_DtsClockNode | None":
        """Extract the block at *block_start* and return a node if it has clock data."""
        full_content = self._extract_block(dts, block_start)
        # Only inspect top-level properties — nested sub-nodes are parsed separately.
        top = self._top_level_content(full_content)
        clocks, clock_names = self._parse_clocks(top)
        output_names = self._parse_output_names(top)
        if not (clocks or output_names):
            return None
        return _DtsClockNode(
            label=label,
            node_name=node_name,
            clocks=clocks,
            clock_names=clock_names,
            clock_output_names=output_names,
        )

    def _top_level_content(self, content: str) -> str:
        """Return *content* with all nested brace blocks removed.

        Only top-level property lines (outside ``{ }`` sub-blocks) are kept,
        preventing child-node clock properties from being attributed to the
        parent node.
        """
        result: list[str] = []
        depth = 0
        for ch in content:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            elif depth == 0:
                result.append(ch)
        return "".join(result)

    def _extract_block(self, dts: str, start: int) -> str:
        """Return the text of the brace block that starts at *start* (after ``{``)."""
        depth = 1
        pos = start
        while pos < len(dts) and depth > 0:
            ch = dts[pos]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            pos += 1
        return dts[start : pos - 1]

    def _parse_clocks(self, content: str) -> tuple[list[tuple[str, int]], list[str]]:
        """Parse the ``clocks`` and ``clock-names`` properties from *content*."""
        clocks: list[tuple[str, int]] = []
        clk_m = re.search(r"\bclocks\s*=\s*([^;]+);", content)
        if clk_m:
            for ref_m in re.finditer(r"<&(\w+)\s+(\d+)>", clk_m.group(1)):
                clocks.append((ref_m.group(1), int(ref_m.group(2))))
            # Handle single-cell refs without index: <&label>
            for ref_m in re.finditer(r"<&(\w+)>", clk_m.group(1)):
                clocks.append((ref_m.group(1), 0))

        names: list[str] = []
        names_m = re.search(r"\bclock-names\s*=\s*([^;]+);", content)
        if names_m:
            names = re.findall(r'"([^"]*)"', names_m.group(1))

        return clocks, names

    def _parse_output_names(self, content: str) -> list[str]:
        """Parse the ``clock-output-names`` property from *content*."""
        m = re.search(r"\bclock-output-names\s*=\s*([^;]+);", content)
        if not m:
            return []
        return re.findall(r'"([^"]*)"', m.group(1))


# ---------------------------------------------------------------------------
# DOT renderer
# ---------------------------------------------------------------------------


class _DotRenderer:
    """Converts a list of :class:`_DtsClockNode` objects into a DOT graph string."""

    def render(self, nodes: list[_DtsClockNode], title: str) -> str:
        """Return a Graphviz DOT string for the clock topology of *nodes*."""
        # Collect all labels that are referenced as providers or are defined
        defined_labels = {n.label for n in nodes}
        provider_labels: set[str] = set()
        for n in nodes:
            for prov, _ in n.clocks:
                provider_labels.add(prov)

        # Nodes to declare: defined + any external providers
        all_labels = defined_labels | provider_labels

        lines: list[str] = []
        lines.append("digraph clock_topology {")
        lines.append(f'    label="{title} — clock topology";')
        lines.append("    labelloc=t; labeljust=l;")
        lines.append(
            '    graph [bgcolor="#1e1e1e" fontcolor="#d4d4d4" fontname="monospace" fontsize=11];'
        )
        lines.append(
            '    node [style="filled,rounded" fontname="monospace" fontsize=9 fontcolor=white];'
        )
        lines.append('    edge [fontname="monospace" fontsize=8 arrowsize=0.7];')
        lines.append("    rankdir=LR;")
        lines.append("")

        # Declare all nodes
        label_to_node = {n.label: n for n in nodes}
        for lbl in sorted(all_labels):
            node = label_to_node.get(lbl)
            node_name = node.node_name if node else lbl
            display = _short_label(lbl, node_name)
            style = _node_style(lbl)
            lines.append(f'    {lbl} [label="{display}" {style}];')

        lines.append("")

        # Emit edges
        for n in nodes:
            for i, (prov, idx) in enumerate(n.clocks):
                clk_name = n.clock_names[i] if i < len(n.clock_names) else ""
                edge_lbl = f"{clk_name}[{idx}]" if clk_name else f"[{idx}]"
                edge_style = _edge_style(clk_name)
                lines.append(
                    f'    {prov} -> {n.label} [label="{edge_lbl}" {edge_style}];'
                )

        lines.append("}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class ClockGraphGenerator:
    """Parse a merged DTS and write a Graphviz clock-tree diagram.

    Produces a ``.dot`` file unconditionally.  If the ``dot`` system tool
    (Graphviz) is available an ``.svg`` is rendered alongside it.
    """

    def generate(self, merged_dts: str, output_dir: Path, name: str) -> dict[str, Path]:
        """Parse *merged_dts*, write DOT (and optionally SVG) under *output_dir*.

        Args:
            merged_dts: Full text of the merged DTS file.
            output_dir: Directory where output files are written.
            name: Base name used for output file stems.

        Returns:
            Dict with keys ``"clock_dot"`` (always present) and
            ``"clock_svg"`` (present only when Graphviz ``dot`` is available).
        """
        nodes = _DtsParser().parse(merged_dts)
        dot_text = _DotRenderer().render(nodes, name)

        safe_name = re.sub(r"[^\w\-.]", "_", name)
        dot_path = output_dir / f"{safe_name}_clocks.dot"
        dot_path.write_text(dot_text)

        result: dict[str, Path] = {"clock_dot": dot_path}

        svg_path = output_dir / f"{safe_name}_clocks.svg"
        if self._render_svg(dot_path, svg_path):
            result["clock_svg"] = svg_path

        return result

    def _render_svg(self, dot_path: Path, svg_path: Path) -> bool:
        """Run ``dot -Tsvg`` to produce *svg_path*; return ``True`` on success."""
        if shutil.which("dot") is None:
            return False
        res = subprocess.run(
            ["dot", "-Tsvg", "-o", str(svg_path), str(dot_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        return res.returncode == 0
