# adidt/xsa/clock_graph.py
"""Generate clock-tree diagrams from merged DTS files.

Parses ``clocks``, ``clock-names``, and ``clock-output-names`` properties out
of a merged DTS string and produces directed graphs showing the clock
distribution path from provider to consumer.

Two output formats are supported:

* **Graphviz DOT** — always written; an SVG is rendered when ``dot`` is on PATH.
* **D2** — always written; an SVG is rendered when ``d2`` is on PATH.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from ._common import categorise, d2_label, run_tool, short_label


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


def _node_style(label: str) -> str:
    """Return a Graphviz attribute string for the node identified by *label*.

    Args:
        label: DTS node label used to look up the visual category.

    Returns:
        A space-separated string of ``key="value"`` Graphviz node attributes
        (e.g. ``'fillcolor="#1a3d5c" shape="box"'``).
    """
    style = _CATEGORY_STYLE.get(categorise(label), _CATEGORY_STYLE["other"])
    parts = [f'{k}="{v}"' for k, v in style.items()]
    return " ".join(parts)


def _edge_style(clock_name: str) -> str:
    """Return Graphviz edge attributes for an edge labelled *clock_name*.

    Args:
        clock_name: Value from the DTS ``clock-names`` property
            (e.g. ``"device_clk"``, ``"s_axi_aclk"``).

    Returns:
        A space-separated Graphviz edge attribute string.  Unknown names
        fall back to a neutral grey colour.
    """
    return _CLOCK_NAME_EDGE_STYLE.get(clock_name, 'color="#888888" fontcolor="#888888"')


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
        """Return a list of :class:`_DtsClockNode` objects parsed from *dts*.

        Both standard labeled-node declarations and DTS overlay reference
        blocks are handled.  When the same label appears in both forms the
        clock information is merged into a single entry.

        Args:
            dts: Full DTS source text to parse.

        Returns:
            List of clock-related nodes, deduplicated by label.
        """
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
        """Extract the block at *block_start* and return a node if it has clock data.

        Args:
            dts: Full DTS source text.
            block_start: Character offset immediately after the opening ``{``
                of the node block.
            label: DTS label for the node.
            node_name: DTS node name (may equal *label* for overlay blocks).

        Returns:
            A populated :class:`_DtsClockNode`, or ``None`` if the block
            contains neither ``clocks`` nor ``clock-output-names``.
        """
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

        Args:
            content: Raw text of a DTS node block (excluding the outer braces).

        Returns:
            A string containing only the characters at brace depth 0.
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
        """Return the text of the brace block that starts at *start* (after ``{``).

        Tracks brace nesting so that inner ``{ }`` pairs are included verbatim
        in the returned slice.

        Args:
            dts: Full DTS source text.
            start: Character offset immediately after the opening ``{``.

        Returns:
            The block contents up to (but not including) the matching ``}``.
        """
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
        """Parse the ``clocks`` and ``clock-names`` properties from *content*.

        Args:
            content: Top-level text of a DTS node block (nested sub-blocks
                already stripped by :meth:`_top_level_content`).

        Returns:
            A two-tuple of:

            * ``clocks`` — list of ``(provider_label, clock_index)`` pairs
              extracted from the ``clocks`` property.
            * ``clock_names`` — list of name strings from the
              ``clock-names`` property (may be empty).
        """
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
        """Parse the ``clock-output-names`` property from *content*.

        Args:
            content: Top-level text of a DTS node block.

        Returns:
            Ordered list of output clock name strings, or an empty list when
            the property is absent.
        """
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
        """Return a Graphviz DOT string for the clock topology of *nodes*.

        Args:
            nodes: Parsed clock nodes from :class:`_DtsParser`.
            title: Human-readable title embedded in the graph label.

        Returns:
            A complete ``digraph clock_topology { ... }`` DOT source string
            with dark-themed node fill colours, per-category shapes, and
            per-clock-name edge colours.
        """
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
            display = short_label(lbl, node_name)
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
# D2 renderer
# ---------------------------------------------------------------------------

_D2_CATEGORY_STYLE: dict[str, dict[str, str]] = {
    "ps_clock": {"shape": "oval", "fill": "#7a3800"},
    "clock_chip": {"shape": "rectangle", "fill": "#1a3d5c"},
    "xcvr": {"shape": "rectangle", "fill": "#4a1a5c"},
    "jesd": {"shape": "rectangle", "fill": "#1a4a20"},
    "clkgen": {"shape": "rectangle", "fill": "#1a4a4a"},
    "converter": {"shape": "rectangle", "fill": "#5c1a1a"},
    "dma": {"shape": "rectangle", "fill": "#3a3a3a"},
    "other": {"shape": "rectangle", "fill": "#2a2a2a"},
}

# clock_name → (stroke_color, stroke_dash)   dash=0 means solid
_D2_EDGE_STYLE: dict[str, tuple[str, int]] = {
    "s_axi_aclk": ("#555555", 5),
    "device_clk": ("#4a9eff", 0),
    "lane_clk": ("#44cc44", 0),
    "conv": ("#cc9944", 0),
    "div40": ("#cc9944", 5),
    "sampl_clk": ("#cc44cc", 0),
}
_D2_EDGE_DEFAULT = ("#888888", 0)


class _D2Renderer:
    """Converts a list of :class:`_DtsClockNode` objects into a D2 diagram string."""

    def render(self, nodes: list[_DtsClockNode], title: str) -> str:
        """Return a D2 diagram string for the clock topology of *nodes*.

        Args:
            nodes: Parsed clock nodes from :class:`_DtsParser`.
            title: Unused in the D2 output (reserved for future use).

        Returns:
            A D2 source string with ELK layout engine, ``direction: right``,
            per-node style blocks, and per-clock-name edge stroke colours.
        """
        defined_labels = {n.label for n in nodes}
        provider_labels: set[str] = set()
        for n in nodes:
            for prov, _ in n.clocks:
                provider_labels.add(prov)
        all_labels = defined_labels | provider_labels

        lines: list[str] = []
        lines.append("vars: {")
        lines.append("  d2-config: {")
        lines.append("    layout-engine: elk")
        lines.append("  }")
        lines.append("}")
        lines.append("direction: right")
        lines.append("")

        label_to_node = {n.label: n for n in nodes}
        for lbl in sorted(all_labels):
            node = label_to_node.get(lbl)
            node_name = node.node_name if node else lbl
            display = d2_label(lbl, node_name)
            cat = categorise(lbl)
            s = _D2_CATEGORY_STYLE.get(cat, _D2_CATEGORY_STYLE["other"])
            lines.append(f"{lbl}: {{")
            lines.append(f'  label: "{display}"')
            lines.append(f"  shape: {s['shape']}")
            lines.append(f'  style.fill: "{s["fill"]}"')
            lines.append("  style.font-color: white")
            lines.append("}")

        lines.append("")

        for n in nodes:
            for i, (prov, idx) in enumerate(n.clocks):
                clk_name = n.clock_names[i] if i < len(n.clock_names) else ""
                edge_lbl = f"{clk_name}[{idx}]" if clk_name else f"[{idx}]"
                stroke, dash = _D2_EDGE_STYLE.get(clk_name, _D2_EDGE_DEFAULT)
                lines.append(f'{prov} -> {n.label}: "{edge_lbl}" {{')
                lines.append(f'  style.stroke: "{stroke}"')
                if dash:
                    lines.append(f"  style.stroke-dash: {dash}")
                lines.append("}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class ClockGraphGenerator:
    """Parse a merged DTS and write clock-tree diagrams in DOT and D2 formats.

    Both a ``.dot`` and a ``.d2`` file are written unconditionally.  SVG
    renderings are produced alongside each when the corresponding tool
    (``dot`` for Graphviz, ``d2`` for D2) is available on PATH.
    """

    def generate(self, merged_dts: str, output_dir: Path, name: str) -> dict[str, Path]:
        """Parse *merged_dts* and write diagram files under *output_dir*.

        Args:
            merged_dts: Full text of the merged DTS file.
            output_dir: Directory where output files are written.
            name: Base name used for output file stems.

        Returns:
            Dict that always contains ``"clock_dot"`` and ``"clock_d2"``, plus
            ``"clock_dot_svg"`` and/or ``"clock_d2_svg"`` when the respective
            rendering tool is available.
        """
        nodes = _DtsParser().parse(merged_dts)
        safe_name = re.sub(r"[^\w\-.]", "_", name)

        # --- Graphviz DOT ---
        dot_path = output_dir / f"{safe_name}_clocks.dot"
        dot_path.write_text(_DotRenderer().render(nodes, name))
        result: dict[str, Path] = {"clock_dot": dot_path}
        dot_svg = output_dir / f"{safe_name}_clocks.dot.svg"
        if run_tool(["dot", "-Tsvg", "-o", str(dot_svg), str(dot_path)], "dot"):
            result["clock_dot_svg"] = dot_svg

        # --- D2 ---
        d2_path = output_dir / f"{safe_name}_clocks.d2"
        d2_path.write_text(_D2Renderer().render(nodes, name))
        result["clock_d2"] = d2_path
        d2_svg = output_dir / f"{safe_name}_clocks.d2.svg"
        if run_tool(["d2", str(d2_path), str(d2_svg)], "d2"):
            result["clock_d2_svg"] = d2_svg

        return result
