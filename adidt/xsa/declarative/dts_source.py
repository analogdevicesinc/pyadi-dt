"""A small device-tree *source* parser that keeps labels and references intact.

``dtc`` and ``fdt`` resolve phandles and drop labels, which is the opposite
of what profile seeding needs: the reference trees are only reusable if
``<&clkc 15>`` stays ``<&clkc 15>``.  This parser reads C-preprocessed DTS,
remembers which file every node and property came from (via the
preprocessor's line markers), and applies ``&label`` overlays and
``/delete-node/`` directives the way ``dtc`` would.

It understands the subset of DTS syntax the kernel trees use; property
values are kept as raw text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_LINEMARKER_RE = re.compile(r'#(?:line)? +\d+ +"([^"]*)"[^\n]*')
_LABEL_REF_RE = re.compile(r"&(\w+)|&\{([^}]+)\}")
_HEADER_RE = re.compile(r"^((?:\w+\s*:\s*)*)(\S+)$", re.DOTALL)
_TOP_DIRECTIVES = ("/dts-v1/", "/plugin/", "/memreserve/")


class DtsSyntaxError(ValueError):
    """Raised when the source cannot be parsed."""


@dataclass
class DtsProperty:
    """One property; *value* is the raw text right of ``=`` (None for flags)."""

    name: str
    value: str | None
    origin: str = ""

    def render(self, indent: str) -> str:
        """Return the property as one DTS statement."""
        if self.value is None:
            return f"{indent}{self.name};"
        return f"{indent}{self.name} = {self.value};"

    def references(self) -> set[str]:
        """Return the labels this property's value refers to."""
        if self.value is None:
            return set()
        matches = _LABEL_REF_RE.finditer(_strip_strings(self.value))
        return {m.group(1) for m in matches if m.group(1)}


@dataclass
class DtsNode:
    """One node with its labels, properties and children in source order."""

    name: str
    labels: list[str] = field(default_factory=list)
    properties: dict[str, DtsProperty] = field(default_factory=dict)
    children: list["DtsNode"] = field(default_factory=list)
    origin: str = ""
    parent: "DtsNode | None" = field(default=None, repr=False, compare=False)

    @property
    def unit_address(self) -> int | None:
        """Return the unit address as an integer, or None."""
        _, _, unit = self.name.partition("@")
        try:
            return int(unit, 16) if unit else None
        except ValueError:
            return None

    @property
    def base_name(self) -> str:
        """Return the node name without its unit address."""
        return self.name.partition("@")[0]

    def child(self, name: str) -> "DtsNode | None":
        """Return the direct child called *name*, or None."""
        return next((c for c in self.children if c.name == name), None)

    def walk(self):
        """Yield this node and every descendant, depth first."""
        yield self
        for child in self.children:
            yield from child.walk()

    def path(self) -> str:
        """Return the absolute path of this node."""
        if self.parent is None:
            return "/"
        prefix = self.parent.path().rstrip("/")
        return f"{prefix}/{self.name}"

    def compatible(self) -> list[str]:
        """Return the node's compatible strings."""
        prop = self.properties.get("compatible")
        if prop is None or prop.value is None:
            return []
        return re.findall(r'"([^"]*)"', prop.value)

    def references(self) -> set[str]:
        """Return every label referenced from this node or below it."""
        refs: set[str] = set()
        for node in self.walk():
            for prop in node.properties.values():
                refs |= prop.references()
        return refs

    def defined_labels(self) -> set[str]:
        """Return every label defined on this node or below it."""
        return {label for node in self.walk() for label in node.labels}

    def render(self, indent: str = "") -> str:
        """Return the node as DTS source."""
        head = "".join(f"{label}: " for label in self.labels) + self.name
        lines = [f"{indent}{head} {{"]
        inner = indent + "\t"
        lines.extend(p.render(inner) for p in self.properties.values())
        for child in self.children:
            if self.properties or child is not self.children[0]:
                lines.append("")
            lines.append(child.render(inner))
        lines.append(f"{indent}}};")
        return "\n".join(lines)


def _strip_strings(text: str) -> str:
    """Blank out quoted strings so their contents are not mistaken for syntax."""
    return re.sub(r'"(?:\\.|[^"\\])*"', '""', text)


class _Scanner:
    """Splits DTS text into statements while tracking the originating file."""

    def __init__(self, text: str, origin: str) -> None:
        self.text = text
        self.pos = 0
        self.origin = origin

    def _skip_blank(self) -> None:
        text = self.text
        while self.pos < len(text):
            ch = text[self.pos]
            if ch.isspace():
                self.pos += 1
            elif text.startswith("/*", self.pos):
                end = text.find("*/", self.pos + 2)
                self.pos = len(text) if end < 0 else end + 2
            elif text.startswith("//", self.pos):
                end = text.find("\n", self.pos)
                self.pos = len(text) if end < 0 else end
            elif ch == "#" and self._at_line_start():
                marker = _LINEMARKER_RE.match(text, self.pos)
                if marker is None:
                    return
                self.origin = marker.group(1)
                self.pos = marker.end()
            else:
                return

    def _at_line_start(self) -> bool:
        line_start = self.text.rfind("\n", 0, self.pos) + 1
        return not self.text[line_start : self.pos].strip()

    def next_statement(self) -> tuple[str, str, str]:
        """Return ``(kind, text, origin)``; kind is ``{``, ``;``, ``}`` or ``""``."""
        self._skip_blank()
        text = self.text
        if self.pos >= len(text):
            return "", "", self.origin
        origin = self.origin
        start = self.pos
        if text[start] == "}":
            self.pos += 1
            self._skip_blank()
            if self.pos < len(text) and text[self.pos] == ";":
                self.pos += 1
            return "}", "", origin
        chunks: list[str] = []
        while self.pos < len(text):
            ch = text[self.pos]
            if ch == '"':
                end = self.pos + 1
                while end < len(text) and text[end] != '"':
                    end += 2 if text[end] == "\\" else 1
                chunks.append(text[self.pos : end + 1])
                self.pos = end + 1
            elif text.startswith("/*", self.pos):
                end = text.find("*/", self.pos + 2)
                self.pos = len(text) if end < 0 else end + 2
            elif text.startswith("//", self.pos):
                end = text.find("\n", self.pos)
                self.pos = len(text) if end < 0 else end
            elif ch == "\n":
                chunks.append(ch)
                self.pos += 1
                marker = _LINEMARKER_RE.match(text, self.pos)
                if marker is not None:
                    self.origin = marker.group(1)
                    self.pos = marker.end()
            elif ch in "{;}":
                # ``&{/path}`` references keep their braces.
                if ch == "{" and chunks and "".join(chunks).rstrip().endswith("&"):
                    end = text.find("}", self.pos)
                    chunks.append(text[self.pos : end + 1])
                    self.pos = end + 1
                    continue
                if ch == "}":
                    raise DtsSyntaxError(
                        f"unterminated statement before '}}' in {origin}: "
                        f"{''.join(chunks).strip()[:60]!r}"
                    )
                self.pos += 1
                return ch, " ".join("".join(chunks).split()), origin
            else:
                chunks.append(ch)
                self.pos += 1
        raise DtsSyntaxError(f"unexpected end of input in {origin}")


class DtsTree:
    """A parsed tree with overlays applied, plus the labels it defines."""

    def __init__(self) -> None:
        self.root = DtsNode(name="/")
        self.labels: dict[str, DtsNode] = {}
        # Overlays whose target label the source never defines.
        self.unresolved: list[DtsNode] = []

    # -- construction ---------------------------------------------------

    @classmethod
    def parse(cls, text: str, origin: str = "<input>") -> "DtsTree":
        """Parse preprocessed DTS *text* into a merged tree."""
        tree = cls()
        scanner = _Scanner(text, origin)
        while True:
            kind, stmt, stmt_origin = scanner.next_statement()
            if kind == "":
                break
            if kind == "}":
                raise DtsSyntaxError(f"unbalanced '}}' in {stmt_origin}")
            if kind == ";":
                tree._top_directive(stmt)
                continue
            labels, name = _split_header(stmt)
            if name == "/":
                target: DtsNode | None = tree.root
            elif name.startswith("&"):
                target = tree._resolve(name)
                if target is None:
                    target = DtsNode(name=name, origin=stmt_origin)
                    tree.unresolved.append(target)
            else:
                raise DtsSyntaxError(
                    f"unexpected top-level node {name!r} in {stmt_origin}"
                )
            if not target.origin:
                target.origin = stmt_origin
            tree._add_labels(target, labels)
            tree._parse_body(scanner, target)
        return tree

    def _top_directive(self, stmt: str) -> None:
        if stmt.startswith("/delete-node/"):
            self._delete_node(self.root, stmt.split(None, 1)[1].strip())
        elif stmt and not stmt.startswith(_TOP_DIRECTIVES):
            raise DtsSyntaxError(f"unexpected top-level statement {stmt[:60]!r}")

    def _resolve(self, ref: str) -> DtsNode | None:
        ref = ref.lstrip("&")
        if ref.startswith("{"):
            node: DtsNode | None = self.root
            for part in ref.strip("{}").strip("/").split("/"):
                node = node.child(part) if node is not None and part else node
            return node
        return self.labels.get(ref)

    def _add_labels(self, node: DtsNode, labels: list[str]) -> None:
        for label in labels:
            if label not in node.labels:
                node.labels.append(label)
            self.labels[label] = node

    def _delete_node(self, parent: DtsNode, target: str) -> None:
        node = self._resolve(target) if target.startswith("&") else parent.child(target)
        if node is None or node.parent is None:
            return
        node.parent.children.remove(node)
        for gone in node.walk():
            for label in gone.labels:
                if self.labels.get(label) is gone:
                    del self.labels[label]

    def _parse_body(self, scanner: _Scanner, node: DtsNode) -> None:
        while True:
            kind, stmt, origin = scanner.next_statement()
            if kind == "}":
                return
            if kind == "":
                raise DtsSyntaxError(f"missing '}}' for node {node.name}")
            if kind == ";":
                self._statement(node, stmt, origin)
                continue
            if stmt.startswith("/omit-if-no-ref/"):
                stmt = stmt[len("/omit-if-no-ref/") :].strip()
            labels, name = _split_header(stmt)
            child = node.child(name)
            if child is None:
                child = DtsNode(name=name, origin=origin, parent=node)
                node.children.append(child)
            self._add_labels(child, labels)
            self._parse_body(scanner, child)

    def _statement(self, node: DtsNode, stmt: str, origin: str) -> None:
        if stmt.startswith("/delete-node/"):
            self._delete_node(node, stmt.split(None, 1)[1].strip())
            return
        if stmt.startswith("/delete-property/"):
            node.properties.pop(stmt.split(None, 1)[1].strip(), None)
            return
        if not stmt:
            return
        name, eq, value = stmt.partition("=")
        name = name.strip()
        # A property may carry a label (``label: prop = ...``); drop it.
        if ":" in name:
            name = name.rsplit(":", 1)[1].strip()
        # Re-assignment keeps the property's original position, as dtc does.
        node.properties[name] = DtsProperty(
            name=name, value=value.strip() if eq else None, origin=origin
        )

    # -- queries --------------------------------------------------------

    def node_at(self, path: str) -> DtsNode | None:
        """Return the node at absolute *path*, or None."""
        node: DtsNode | None = self.root
        for part in path.strip("/").split("/"):
            if node is None:
                return None
            if part:
                node = node.child(part)
        return node

    def find_compatible(self, compatible: str) -> list[DtsNode]:
        """Return every node listing *compatible*."""
        return [n for n in self.root.walk() if compatible in n.compatible()]


def _split_header(stmt: str) -> tuple[list[str], str]:
    """Split ``"a: b: name@1"`` into its labels and node name."""
    match = _HEADER_RE.match(stmt.strip())
    if match is None:
        raise DtsSyntaxError(f"cannot parse node header {stmt[:60]!r}")
    labels = [part.strip() for part in match.group(1).split(":") if part.strip()]
    return labels, match.group(2)


def parse_cells(value: str | None) -> list[int] | None:
    """Return the integers of a ``<...>`` cell list, or None if not plain numbers."""
    if value is None:
        return None
    cells: list[int] = []
    for group in re.findall(r"<([^>]*)>", value):
        for token in group.split():
            try:
                cells.append(int(token, 0))
            except ValueError:
                return None
    return cells
