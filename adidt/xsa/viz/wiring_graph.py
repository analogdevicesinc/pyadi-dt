"""Generate control-plane wiring graphs for an XSA design or System composition.

Renders a single combined diagram showing SPI buses, JESD204 links, GPIO
control lines, interrupts, and I2C buses, with edges color-keyed by kind.
Two output formats: Graphviz DOT and D2 (with optional SVG when ``dot`` /
``d2`` are on PATH).

Two input adapters:

* :meth:`WiringGraph.from_topology` — XSA pipeline path; consumes an
  :class:`~adidt.xsa.parse.topology.XsaTopology` plus the merged DTS string
  for GPIO / I2C extraction.
* :meth:`WiringGraph.from_system` — declarative path; consumes a
  :class:`~adidt.system.System`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Literal

from ._common import categorise, d2_label, run_tool, short_label

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..parse.topology import XsaTopology


EdgeKind = Literal["spi", "jesd", "gpio", "irq", "i2c"]
ALL_KINDS: tuple[EdgeKind, ...] = ("spi", "jesd", "gpio", "irq", "i2c")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WiringNode:
    """One node in the wiring graph.

    ``label`` is the unique identifier (DTS label).  ``node_name`` is the
    DTS node name with optional ``@addr`` suffix; falls back to *label* when
    no node name is known.  ``kind`` is the visual category used to colour
    the node — one of the categories returned by
    :func:`adidt.xsa.viz._common.categorise` plus the wiring-specific
    ``spi_master``, ``gpio_controller``, ``i2c_master``, and
    ``interrupt_controller`` synthetic categories.
    """

    label: str
    node_name: str
    kind: str


@dataclass(frozen=True)
class WiringEdge:
    """One directed edge in the wiring graph."""

    src: str
    dst: str
    kind: EdgeKind
    label: str = ""


@dataclass
class WiringGraph:
    """Collected nodes + edges, source-agnostic."""

    nodes: list[WiringNode] = field(default_factory=list)
    edges: list[WiringEdge] = field(default_factory=list)

    def add_node(self, label: str, *, node_name: str | None = None, kind: str | None = None) -> None:
        if any(n.label == label for n in self.nodes):
            return
        self.nodes.append(
            WiringNode(label=label, node_name=node_name or label, kind=kind or categorise(label))
        )

    def add_edge(self, edge: WiringEdge) -> None:
        self.edges.append(edge)

    @classmethod
    def from_topology(
        cls,
        topology: "XsaTopology",
        cfg: dict[str, Any] | None = None,
        merged_dts: str | None = None,
    ) -> "WiringGraph":
        """Build a :class:`WiringGraph` from an XSA topology.

        ``cfg`` is currently unused but accepted for symmetry with the
        pipeline call sites that already plumb config dicts.  ``merged_dts``
        enables GPIO and I2C edge extraction; without it those edge kinds
        are skipped.
        """
        del cfg  # reserved for future use
        graph = cls()
        for edge in _extract_spi_from_topology(topology, graph):
            graph.add_edge(edge)
        for edge in _extract_jesd_from_topology(topology, graph):
            graph.add_edge(edge)
        for edge in _extract_irq_from_topology(topology, graph):
            graph.add_edge(edge)
        if merged_dts:
            for edge in _extract_gpio_from_dts(merged_dts, graph):
                graph.add_edge(edge)
            for edge in _extract_i2c_from_dts(merged_dts, graph):
                graph.add_edge(edge)
        return graph

    @classmethod
    def from_system(cls, system: Any) -> "WiringGraph":
        """Build a :class:`WiringGraph` from a :class:`adidt.system.System`."""
        graph = cls()
        for edge in _extract_spi_from_system(system, graph):
            graph.add_edge(edge)
        for edge in _extract_jesd_from_system(system, graph):
            graph.add_edge(edge)
        for edge in _extract_gpio_from_system(system, graph):
            graph.add_edge(edge)
        return graph


# ---------------------------------------------------------------------------
# Extractors — System (declarative) path
# ---------------------------------------------------------------------------


_GPIO_FIELD_NAMES = (
    "reset_gpio",
    "sysref_req_gpio",
    "rx1_enable_gpio",
    "rx2_enable_gpio",
    "tx1_enable_gpio",
    "tx2_enable_gpio",
    "tx_enable_gpio",
    "rx_enable_gpio",
    "test_gpio",
)


def _device_label(obj: Any, system: Any | None = None) -> str:
    """Best-effort, DOT-identifier-safe label for a System endpoint.

    Endpoints can be:

    * a Device (``label`` is a string),
    * :class:`SpiPort` / :class:`ClockOutput` (have a ``device`` attribute),
    * :class:`GtLane` (has ``fpga`` + ``index`` — render as
      ``<fpga>_gt<index>``),
    * a :class:`ConverterSide` (an ADC or DAC sub-model).  Has no back-
      reference, so when *system* is provided we walk
      ``system._all_devices()`` to find the parent converter and append
      ``_adc`` / ``_dac``.
    """
    if hasattr(obj, "label") and isinstance(getattr(obj, "label"), str):
        return obj.label

    fpga = getattr(obj, "fpga", None)
    index = getattr(obj, "index", None)
    if fpga is not None and hasattr(fpga, "label") and index is not None:
        return f"{fpga.label}_gt{index}"

    inner = getattr(obj, "device", None)
    if inner is not None and hasattr(inner, "label"):
        return inner.label

    if system is not None and hasattr(system, "_all_devices"):
        for dev in system._all_devices():
            if getattr(dev, "adc", None) is obj:
                return f"{dev.label}_adc"
            if getattr(dev, "dac", None) is obj:
                return f"{dev.label}_dac"

    # Last-resort sanitization — type name only, no pydantic repr.
    return type(obj).__name__


def _gpio_label(system: Any) -> str:
    """Return the FPGA's GPIO controller label, or ``'gpio'`` as fallback."""
    for comp in getattr(system, "components", []):
        gp = getattr(comp, "gpio_label", None)
        if gp:
            return gp
    return "gpio"


def _extract_spi_from_system(system: Any, graph: WiringGraph) -> list[WiringEdge]:
    edges: list[WiringEdge] = []
    for conn in getattr(system, "_spi", []):
        master = conn.primary
        slave = conn.secondary
        master_label = getattr(master, "label", None) or _device_label(master)
        slave_label = _device_label(slave)
        bus_label = master_label or f"spi{conn.bus_index}"
        graph.add_node(bus_label, kind="spi_master")
        graph.add_node(slave_label)
        edges.append(
            WiringEdge(src=bus_label, dst=slave_label, kind="spi", label=f"cs={conn.cs}")
        )
    return edges


def _extract_jesd_from_system(system: Any, graph: WiringGraph) -> list[WiringEdge]:
    edges: list[WiringEdge] = []
    for link in getattr(system, "_links", []):
        src = _device_label(link.source, system)
        dst = _device_label(link.sink, system)
        graph.add_node(src)
        graph.add_node(dst)
        edges.append(WiringEdge(src=src, dst=dst, kind="jesd", label="JESD204"))
    return edges


def _extract_gpio_from_system(system: Any, graph: WiringGraph) -> list[WiringEdge]:
    """Walk every device for known GPIO fields; emit `gpio_controller -> dev` edges."""
    edges: list[WiringEdge] = []
    gpio = _gpio_label(system)
    devices: Iterable[Any] = ()
    if hasattr(system, "_all_devices"):
        devices = list(system._all_devices())
    seen_gpio_node = False
    for dev in devices:
        dev_label = getattr(dev, "label", None)
        if not dev_label:
            continue
        for field_name in _GPIO_FIELD_NAMES:
            value = getattr(dev, field_name, None)
            if value is None:
                continue
            if not seen_gpio_node:
                graph.add_node(gpio, kind="gpio_controller")
                seen_gpio_node = True
            graph.add_node(dev_label)
            short = field_name.replace("_gpio", "").replace("_", "-")
            edges.append(
                WiringEdge(src=gpio, dst=dev_label, kind="gpio", label=f"{short}={value}")
            )
    return edges


# ---------------------------------------------------------------------------
# Extractors — XsaTopology path
# ---------------------------------------------------------------------------


def _extract_spi_from_topology(topology: "XsaTopology", graph: WiringGraph) -> list[WiringEdge]:
    edges: list[WiringEdge] = []
    for conv in topology.converters:
        if conv.spi_bus is None:
            continue
        bus_label = f"spi{conv.spi_bus}"
        graph.add_node(bus_label, kind="spi_master")
        graph.add_node(conv.name)
        cs = conv.spi_cs if conv.spi_cs is not None else "?"
        edges.append(
            WiringEdge(src=bus_label, dst=conv.name, kind="spi", label=f"cs={cs}")
        )
    return edges


def _extract_jesd_from_topology(topology: "XsaTopology", graph: WiringGraph) -> list[WiringEdge]:
    """Pair JESD instances with converters by direction.

    The XSA HWH netlist exposes JESD cores and converters as separate IPs;
    use the converter's ``ip_type`` plus the JESD instance's ``direction``
    to draw an edge between them.  When multiple converters share a
    direction (e.g. AD9680 + AD9144 in a DAQ2 design) the matching is done
    by index — the order JESD instances appear in topology mirrors the
    order their converters do for every ADI design we have today.
    """
    edges: list[WiringEdge] = []
    rx_converters = [c for c in topology.converters if any(t in c.ip_type for t in ("9680", "9081", "9082", "9083", "9084", "9208", "adrv"))]
    tx_converters = [c for c in topology.converters if any(t in c.ip_type for t in ("9144", "9152", "9172", "9081", "9082", "9084", "adrv"))]
    for inst, converters in ((topology.jesd204_rx, rx_converters), (topology.jesd204_tx, tx_converters)):
        for jesd, conv in zip(inst, converters):
            graph.add_node(jesd.name, kind="jesd")
            graph.add_node(conv.name)
            label = f"L{jesd.num_lanes}"
            if jesd.direction == "rx":
                edges.append(WiringEdge(src=conv.name, dst=jesd.name, kind="jesd", label=label))
            else:
                edges.append(WiringEdge(src=jesd.name, dst=conv.name, kind="jesd", label=label))
    return edges


def _extract_irq_from_topology(topology: "XsaTopology", graph: WiringGraph) -> list[WiringEdge]:
    edges: list[WiringEdge] = []
    seen = False
    for j in (*topology.jesd204_rx, *topology.jesd204_tx):
        if j.irq is None:
            continue
        if not seen:
            graph.add_node("interrupt_controller", kind="interrupt_controller")
            seen = True
        graph.add_node(j.name, kind="jesd")
        edges.append(
            WiringEdge(src=j.name, dst="interrupt_controller", kind="irq", label=f"IRQ {j.irq}")
        )
    return edges


# ---------------------------------------------------------------------------
# Extractors — DTS regex path (used by the topology path; can also be used
# to enrich the System path post-rendering if a merged DTS is available).
# ---------------------------------------------------------------------------


_GPIO_RE = re.compile(
    r"(?P<key>[a-z][a-z0-9-]*-gpios)\s*=\s*<&(?P<gpio>\w+)\s+(?P<num>\d+)",
    re.MULTILINE,
)
_LABELED_NODE_RE = re.compile(
    r"^\s*(?P<label>[a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(?P<name>[a-zA-Z_][a-zA-Z0-9_,.@-]*)\s*\{",
    re.MULTILINE,
)


def _find_enclosing_label(merged_dts: str, prop_offset: int) -> str | None:
    """Walk backward from *prop_offset* to find the nearest enclosing labelled node."""
    head = merged_dts[:prop_offset]
    last_match: re.Match[str] | None = None
    for m in _LABELED_NODE_RE.finditer(head):
        last_match = m
    return last_match.group("label") if last_match else None


def _extract_gpio_from_dts(merged_dts: str, graph: WiringGraph) -> list[WiringEdge]:
    edges: list[WiringEdge] = []
    seen_gpio: set[str] = set()
    for m in _GPIO_RE.finditer(merged_dts):
        key = m.group("key")
        gpio_label = m.group("gpio")
        num = m.group("num")
        owner = _find_enclosing_label(merged_dts, m.start())
        if not owner:
            continue
        if gpio_label not in seen_gpio:
            graph.add_node(gpio_label, kind="gpio_controller")
            seen_gpio.add(gpio_label)
        graph.add_node(owner)
        short = key.removesuffix("-gpios")
        edges.append(
            WiringEdge(src=gpio_label, dst=owner, kind="gpio", label=f"{short}={num}")
        )
    return edges


_I2C_OVERLAY_RE = re.compile(
    r"&(?P<bus>i2c\d+)\s*\{(?P<body>[^{}]*(?:\{[^{}]*\}[^{}]*)*)\}",
    re.MULTILINE | re.DOTALL,
)
_I2C_CHILD_RE = re.compile(
    r"^\s*(?:(?P<label>[a-zA-Z_][\w]*)\s*:\s*)?(?P<name>[a-zA-Z_][\w,.@-]*)\s*\{",
    re.MULTILINE,
)


def _extract_i2c_from_dts(merged_dts: str, graph: WiringGraph) -> list[WiringEdge]:
    edges: list[WiringEdge] = []
    for m in _I2C_OVERLAY_RE.finditer(merged_dts):
        bus = m.group("bus")
        body = m.group("body")
        graph.add_node(bus, kind="i2c_master")
        for child in _I2C_CHILD_RE.finditer(body):
            label = child.group("label") or child.group("name").split("@", 1)[0]
            if not label or label in {"compatible", "status", "reg"}:
                continue
            graph.add_node(label)
            edges.append(WiringEdge(src=bus, dst=label, kind="i2c"))
    return edges


# ---------------------------------------------------------------------------
# DOT / D2 renderers
# ---------------------------------------------------------------------------


_KIND_NODE_STYLE: dict[str, dict[str, str]] = {
    "spi_master": {"fillcolor": "#2a4d6e", "shape": "ellipse"},
    "gpio_controller": {"fillcolor": "#6e4d2a", "shape": "ellipse"},
    "i2c_master": {"fillcolor": "#5a2a6e", "shape": "ellipse"},
    "interrupt_controller": {"fillcolor": "#6e2a2a", "shape": "ellipse"},
    # All other kinds delegate to clock_graph._CATEGORY_STYLE via categorise().
    "ps_clock": {"fillcolor": "#7a3800", "shape": "ellipse"},
    "clock_chip": {"fillcolor": "#1a3d5c", "shape": "box"},
    "xcvr": {"fillcolor": "#4a1a5c", "shape": "box"},
    "jesd": {"fillcolor": "#1a4a20", "shape": "box"},
    "clkgen": {"fillcolor": "#1a4a4a", "shape": "box"},
    "converter": {"fillcolor": "#5c1a1a", "shape": "box"},
    "dma": {"fillcolor": "#3a3a3a", "shape": "box"},
    "other": {"fillcolor": "#2a2a2a", "shape": "box"},
}

# D2 uses ``oval`` / ``rectangle`` rather than Graphviz's ``ellipse`` / ``box``.
_D2_KIND_NODE_STYLE: dict[str, dict[str, str]] = {
    "spi_master": {"fill": "#2a4d6e", "shape": "oval"},
    "gpio_controller": {"fill": "#6e4d2a", "shape": "oval"},
    "i2c_master": {"fill": "#5a2a6e", "shape": "oval"},
    "interrupt_controller": {"fill": "#6e2a2a", "shape": "oval"},
    "ps_clock": {"fill": "#7a3800", "shape": "oval"},
    "clock_chip": {"fill": "#1a3d5c", "shape": "rectangle"},
    "xcvr": {"fill": "#4a1a5c", "shape": "rectangle"},
    "jesd": {"fill": "#1a4a20", "shape": "rectangle"},
    "clkgen": {"fill": "#1a4a4a", "shape": "rectangle"},
    "converter": {"fill": "#5c1a1a", "shape": "rectangle"},
    "dma": {"fill": "#3a3a3a", "shape": "rectangle"},
    "other": {"fill": "#2a2a2a", "shape": "rectangle"},
}

_DOT_EDGE_KIND_STYLE: dict[EdgeKind, str] = {
    "spi": 'color="#4ac4d8" fontcolor="#4ac4d8"',
    "jesd": 'color="#44cc44" fontcolor="#44cc44"',
    "gpio": 'color="#cc9944" fontcolor="#cc9944"',
    "irq": 'color="#cc4444" fontcolor="#cc4444" style=dashed',
    "i2c": 'color="#a04ac4" fontcolor="#a04ac4"',
}

_D2_EDGE_KIND_STYLE: dict[EdgeKind, str] = {
    "spi": "#4ac4d8",
    "jesd": "#44cc44",
    "gpio": "#cc9944",
    "irq": "#cc4444",
    "i2c": "#a04ac4",
}


class _WiringDotRenderer:
    def render(self, graph: WiringGraph, name: str) -> str:
        lines = [
            f'digraph "{name}_wiring" {{',
            "    rankdir=LR;",
            '    node [style="filled,rounded" fontcolor="#ffffff" '
            'color="#000000" fontname="Helvetica"];',
            '    edge [fontname="Helvetica" fontsize=10];',
            f'    bgcolor="#1a1a1a";',
            "",
        ]
        for n in graph.nodes:
            style = _KIND_NODE_STYLE.get(n.kind, _KIND_NODE_STYLE["other"])
            attrs = " ".join(f'{k}="{v}"' for k, v in style.items())
            display = short_label(n.label, n.node_name)
            lines.append(f'    {n.label} [label="{display}" {attrs}];')
        lines.append("")
        for e in graph.edges:
            style = _DOT_EDGE_KIND_STYLE.get(e.kind, "")
            label = f' label="{e.label}"' if e.label else ""
            lines.append(f"    {e.src} -> {e.dst} [{style}{label}];")
        lines.append("}")
        return "\n".join(lines)


class _WiringD2Renderer:
    def render(self, graph: WiringGraph, name: str) -> str:
        lines = [f"# {name}_wiring", "direction: right", ""]
        for n in graph.nodes:
            style = _D2_KIND_NODE_STYLE.get(n.kind, _D2_KIND_NODE_STYLE["other"])
            display = d2_label(n.label, n.node_name)
            lines.extend([
                f"{n.label}: {{",
                f'  label: "{display}"',
                f"  shape: {style['shape']}",
                f"  style.fill: \"{style['fill']}\"",
                "  style.font-color: \"#ffffff\"",
                "}",
            ])
        lines.append("")
        for e in graph.edges:
            color = _D2_EDGE_KIND_STYLE.get(e.kind, "#888888")
            lbl = f': "{e.label}"' if e.label else ""
            lines.append(f'{e.src} -> {e.dst}{lbl} {{ style.stroke: "{color}" }}')
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public generator
# ---------------------------------------------------------------------------


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]")


class WiringGraphGenerator:
    """Write DOT + D2 wiring diagrams (and optional SVGs) for a graph."""

    def generate(
        self,
        graph: WiringGraph,
        output_dir: Path,
        name: str,
        *,
        kinds: set[EdgeKind] | None = None,
    ) -> dict[str, Path]:
        """Render *graph* to ``{name}_wiring.dot``/``.d2`` under *output_dir*.

        Returns a dict of artifact paths with keys ``wiring_dot``,
        ``wiring_d2``, plus ``wiring_dot_svg`` / ``wiring_d2_svg`` when the
        respective renderer is available on PATH.

        ``kinds`` filters edges to the given kinds; ``None`` keeps all.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_name = _SAFE_NAME_RE.sub("_", name)

        rendered = (
            graph
            if kinds is None
            else WiringGraph(
                nodes=list(graph.nodes),
                edges=[e for e in graph.edges if e.kind in kinds],
            )
        )

        result: dict[str, Path] = {}

        dot_path = output_dir / f"{safe_name}_wiring.dot"
        dot_path.write_text(_WiringDotRenderer().render(rendered, name))
        result["wiring_dot"] = dot_path
        dot_svg = output_dir / f"{safe_name}_wiring.dot.svg"
        if run_tool(["dot", "-Tsvg", "-o", str(dot_svg), str(dot_path)], "dot"):
            result["wiring_dot_svg"] = dot_svg

        d2_path = output_dir / f"{safe_name}_wiring.d2"
        d2_path.write_text(_WiringD2Renderer().render(rendered, name))
        result["wiring_d2"] = d2_path
        d2_svg = output_dir / f"{safe_name}_wiring.d2.svg"
        if run_tool(["d2", str(d2_path), str(d2_svg)], "d2"):
            result["wiring_d2_svg"] = d2_svg

        return result
