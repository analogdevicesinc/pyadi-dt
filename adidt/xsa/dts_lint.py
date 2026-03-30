"""Structural DTS linter for generated device tree source files.

Operates on merged DTS text using regex-based parsing — no external tools
(``dtc``, ``dt-schema``) required.  Produces a list of :class:`LintDiagnostic`
items with severity, rule ID, node location, and actionable message.

Usage::

    from adidt.xsa.dts_lint import DtsLinter

    diagnostics = DtsLinter().lint(dts_text)
    errors = [d for d in diagnostics if d.severity == "error"]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class LintDiagnostic:
    """One issue found by the DTS linter."""

    severity: str  # "error", "warning", "info"
    rule: str  # Machine-readable rule ID, e.g., "phandle-unresolved"
    node: str  # Node label or path where issue was found
    message: str  # Human-readable description
    binding_confidence: Optional[str] = None  # For Phase 8 binding rules

    def __str__(self) -> str:
        return f"[{self.severity}] {self.rule}: {self.message} (node: {self.node})"


# ---------------------------------------------------------------------------
# DTS parsing helpers
# ---------------------------------------------------------------------------

# Matches labeled nodes: "label: node_name@addr { body };"
_LABELED_NODE_RE = re.compile(
    r"(?P<label>[A-Za-z_][\w-]*)\s*:\s*[^{;\n]+\{(?P<body>.*?)\};",
    re.S,
)

# Matches overlay ref nodes: "&label { body };"
_OVERLAY_REF_RE = re.compile(
    r"&(?P<label>[A-Za-z_][\w-]*)\s*\{(?P<body>.*?)\};",
    re.S,
)

# Matches phandle references: <&label ...>
_PHANDLE_REF_RE = re.compile(r"<\s*&(?P<label>[A-Za-z_][\w-]*)\b(?P<args>[^>]*)>")

# Matches #clock-cells, #address-cells, etc.: #foo-cells = <N>;
_CELLS_RE = re.compile(r"#(?P<kind>\w+)-cells\s*=\s*<(?P<count>\d+)>")

# Matches reg = <...>; property
_REG_RE = re.compile(r"\breg\s*=\s*<(?P<value>[^>]+)>")

# Matches compatible = "..."; property
_COMPATIBLE_RE = re.compile(r'\bcompatible\s*=\s*"[^"]*"')

# Matches SPI child nodes: device@N { ... }
_SPI_CHILD_RE = re.compile(
    r"(?P<name>[A-Za-z_][\w-]*)\s*:\s*\S+@(?P<unit>\d+)\s*\{(?P<body>.*?)\};",
    re.S,
)


def _parse_nodes(dts: str) -> dict[str, str]:
    """Return a mapping of node label -> body text for all labeled nodes."""
    nodes: dict[str, str] = {}
    for m in _LABELED_NODE_RE.finditer(dts):
        nodes[m.group("label")] = m.group("body")
    for m in _OVERLAY_REF_RE.finditer(dts):
        label = m.group("label")
        if label not in nodes:
            nodes[label] = m.group("body")
        else:
            nodes[label] += "\n" + m.group("body")
    return nodes


def _parse_spi_buses(dts: str) -> dict[str, list[tuple[str, str]]]:
    """Parse SPI bus overlay blocks and return child (label, body) pairs.

    Uses brace counting instead of regex to handle nested nodes correctly.
    Returns a mapping of bus_label -> [(child_label, child_body), ...].
    """
    result: dict[str, list[tuple[str, str]]] = {}
    for m in _OVERLAY_REF_RE.finditer(dts):
        bus_label = m.group("label")
        # Re-parse the full block with brace counting to get the complete body
        start = m.start()
        depth = 0
        full_body_start = None
        full_body_end = None
        for i in range(start, len(dts)):
            if dts[i] == "{":
                if depth == 0:
                    full_body_start = i + 1
                depth += 1
            elif dts[i] == "}":
                depth -= 1
                if depth == 0:
                    full_body_end = i
                    break
        if full_body_start is None or full_body_end is None:
            continue
        full_body = dts[full_body_start:full_body_end]
        if "#address-cells" not in full_body or "spi-max-frequency" not in full_body:
            continue
        children: list[tuple[str, str]] = []
        for child_m in _LABELED_NODE_RE.finditer(full_body):
            children.append((child_m.group("label"), child_m.group("body")))
        if children:
            result[bus_label] = children
    return result


def _parse_cells(nodes: dict[str, str]) -> dict[str, dict[str, int]]:
    """Return per-label mapping of cell kind -> count."""
    result: dict[str, dict[str, int]] = {}
    for label, body in nodes.items():
        cells: dict[str, int] = {}
        for m in _CELLS_RE.finditer(body):
            cells[m.group("kind")] = int(m.group("count"))
        if cells:
            result[label] = cells
    return result


# ---------------------------------------------------------------------------
# Lint rules
# ---------------------------------------------------------------------------


def _check_phandle_unresolved(
    dts: str, nodes: dict[str, str]
) -> list[LintDiagnostic]:
    """Check that every <&label> phandle reference has a matching node."""
    defined_labels = set(nodes.keys())
    diagnostics: list[LintDiagnostic] = []
    seen: set[str] = set()

    for m in _PHANDLE_REF_RE.finditer(dts):
        ref_label = m.group("label")
        if ref_label in defined_labels or ref_label in seen:
            continue
        seen.add(ref_label)
        diagnostics.append(
            LintDiagnostic(
                severity="error",
                rule="phandle-unresolved",
                node=ref_label,
                message=f"phandle reference <&{ref_label}> has no matching node definition",
            )
        )
    return diagnostics


# Matches "clocks = <...>;" property values (may span multiple phandles)
_CLOCKS_PROP_RE = re.compile(r"\bclocks\s*=\s*(?P<value>[^;]+);")


def _check_clock_cells_mismatch(
    dts: str, nodes: dict[str, str], cells_map: dict[str, dict[str, int]]
) -> list[LintDiagnostic]:
    """Check that clock phandle refs provide correct arg count matching #clock-cells.

    Only checks phandle references inside ``clocks = <...>;`` properties,
    not ``jesd204-inputs`` or other phandle-bearing properties that use
    different cell counts (e.g., ``#jesd204-cells``).
    """
    diagnostics: list[LintDiagnostic] = []

    for prop_m in _CLOCKS_PROP_RE.finditer(dts):
        clocks_value = prop_m.group("value")
        for ref_m in _PHANDLE_REF_RE.finditer(clocks_value):
            ref_label = ref_m.group("label")
            args_str = ref_m.group("args").strip()
            provider_cells = cells_map.get(ref_label, {}).get("clock", None)
            if provider_cells is None:
                continue

            arg_tokens = [t for t in args_str.split() if t]
            actual_args = len(arg_tokens)

            if actual_args != provider_cells:
                diagnostics.append(
                    LintDiagnostic(
                        severity="error",
                        rule="clock-cells-mismatch",
                        node=ref_label,
                        message=(
                            f"<&{ref_label}> has #clock-cells = <{provider_cells}> "
                            f"but reference provides {actual_args} argument(s)"
                        ),
                    )
                )
    return diagnostics


def _check_spi_cs_duplicate(
    dts: str, nodes: dict[str, str]
) -> list[LintDiagnostic]:
    """Check that no two SPI child nodes share the same chip select."""
    diagnostics: list[LintDiagnostic] = []
    spi_buses = _parse_spi_buses(dts)

    for bus_label, children in spi_buses.items():
        cs_map: dict[int, list[str]] = {}
        for child_label, child_body in children:
            reg_m = _REG_RE.search(child_body)
            if reg_m:
                try:
                    cs = int(reg_m.group("value").strip())
                except ValueError:
                    continue
                cs_map.setdefault(cs, []).append(child_label)

        for cs, devices in cs_map.items():
            if len(devices) > 1:
                diagnostics.append(
                    LintDiagnostic(
                        severity="error",
                        rule="spi-cs-duplicate",
                        node=bus_label,
                        message=(
                            f"SPI bus &{bus_label} has {len(devices)} devices "
                            f"on chip select {cs}: {', '.join(devices)}"
                        ),
                    )
                )
    return diagnostics


# Matches "label: channel@N" node headers — these are child nodes that
# don't need their own compatible string (parent driver handles them).
_CHILD_NODE_LABEL_RE = re.compile(r"channel@\d+")


def _find_child_labels(dts: str) -> set[str]:
    """Return labels of nodes that are DT child nodes (channel@N etc.)."""
    child_labels: set[str] = set()
    for m in re.finditer(
        r"(?P<label>[A-Za-z_][\w-]*)\s*:\s*channel@\d+", dts
    ):
        child_labels.add(m.group("label"))
    return child_labels


def _check_compatible_missing(
    dts: str, nodes: dict[str, str]
) -> list[LintDiagnostic]:
    """Check that device nodes with reg also have a compatible string.

    Skips child nodes (e.g., HMC7044 ``channel@N`` nodes) — these are
    sub-nodes managed by a parent driver and don't need their own
    compatible string.
    """
    diagnostics: list[LintDiagnostic] = []
    child_labels = _find_child_labels(dts)

    for label, body in nodes.items():
        if label in child_labels:
            continue
        if not _REG_RE.search(body):
            continue
        # Skip bus nodes (they have #address-cells but may not need compatible)
        if "#address-cells" in body and "spi-max-frequency" not in body:
            continue
        if not _COMPATIBLE_RE.search(body):
            diagnostics.append(
                LintDiagnostic(
                    severity="error",
                    rule="compatible-missing",
                    node=label,
                    message=f"node {label} has reg property but no compatible string",
                )
            )
    return diagnostics


# ---------------------------------------------------------------------------
# Linter
# ---------------------------------------------------------------------------


class DtsLinter:
    """Structural linter for generated DTS files.

    Example::

        linter = DtsLinter()
        diagnostics = linter.lint(dts_text)
        for d in diagnostics:
            print(d)
    """

    def lint(
        self,
        dts_text: str,
        topology: Any = None,
        bindings: Any = None,
    ) -> list[LintDiagnostic]:
        """Run all lint rules on *dts_text* and return diagnostics.

        Args:
            dts_text: Merged DTS content as a string.
            topology: Optional :class:`XsaTopology` for topology-aware rules.
            bindings: Optional :class:`BindingRegistry` for binding cross-reference
                rules (Phase 8).

        Returns:
            List of :class:`LintDiagnostic` items, sorted by severity.
        """
        nodes = _parse_nodes(dts_text)
        cells_map = _parse_cells(nodes)
        diagnostics: list[LintDiagnostic] = []

        diagnostics.extend(_check_phandle_unresolved(dts_text, nodes))
        diagnostics.extend(
            _check_clock_cells_mismatch(dts_text, nodes, cells_map)
        )
        diagnostics.extend(_check_spi_cs_duplicate(dts_text, nodes))
        diagnostics.extend(_check_compatible_missing(dts_text, nodes))

        # Sort: errors first, then warnings, then info
        severity_order = {"error": 0, "warning": 1, "info": 2}
        diagnostics.sort(key=lambda d: severity_order.get(d.severity, 3))
        return diagnostics

    def lint_file(
        self,
        dts_path: Path,
        topology: Any = None,
        bindings: Any = None,
    ) -> list[LintDiagnostic]:
        """Convenience wrapper that reads a file and lints its content."""
        return self.lint(dts_path.read_text(), topology, bindings)
