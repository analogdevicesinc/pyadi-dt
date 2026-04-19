"""Declarative device-tree node renderer.

Walks a pydantic model's fields and emits a DT node string directly —
no Jinja2 template, no intermediate context dict.  Field types drive
the output format; :mod:`adidt.devices._fields` markers cover the
non-scalar cases (sub-nodes, explicit skips).

The entry point is :func:`render_node`.  Devices that opt into
declarative rendering expose it via ``Device.render_node(...)``.
"""

from __future__ import annotations

from typing import Any, get_args

from pydantic import BaseModel

from ._fields import DtBits64, DtSkip, DtSubnodes

TAB = "\t"


def _fmt_value(value: Any) -> str:
    """Format *value* as a DT property right-hand-side (no alias, no ``;``).

    Conventions:
    - ``int`` / numeric-looking ``str`` (``"0xE1"``) → ``<N>``
    - ``str`` → ``"N"`` (quoted)
    - ``list[int]`` → ``<v1 v2 ...>``
    - ``list[str]`` → ``"a", "b", ...``
    - ``bool`` is never reached here (bools are flags, handled upstream)
    """
    if isinstance(value, bool):
        raise TypeError("bool should be emitted as a flag, not a prop value")
    if isinstance(value, int):
        return f"<{value}>"
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.lower().startswith("0x"):
            return f"<{stripped}>"
        if stripped.lstrip("-").isdigit():
            return f"<{stripped}>"
        return f'"{value}"'
    if isinstance(value, list):
        if not value:
            return "<>"
        if all(isinstance(v, int) and not isinstance(v, bool) for v in value):
            return "<" + " ".join(str(v) for v in value) + ">"
        if all(isinstance(v, str) for v in value):
            return ", ".join(f'"{v}"' for v in value)
    raise TypeError(f"unsupported DT value type: {type(value).__name__} = {value!r}")


def _field_marker(info: Any, cls: type) -> Any:
    """Return the first marker instance in a field's ``Annotated`` metadata."""
    for meta in getattr(info, "metadata", ()):
        if isinstance(meta, (DtSubnodes, DtSkip, DtBits64)):
            return meta
    return None


def render_node(
    model: BaseModel,
    *,
    label: str,
    node_name: str | None = None,
    reg: int | None = None,
    indent: str = TAB + TAB,
    context: dict | None = None,
    trailing_block: str | None = None,
    overlay: bool = False,
    delete_properties: tuple[str, ...] = (),
) -> str:
    """Render a pydantic model as a DT node string.

    Args:
        model: The pydantic model to render.  Its class may declare
            class-level ``compatible`` (str), ``dt_header`` (dict of
            ``key = <value>;`` properties), and ``dt_flags`` (tuple of
            bare flag property names) that are emitted before the
            per-field properties.
        label: DT label (``<label>:``) preceding the node name.
        node_name: Full node name including unit address (``hmc7044@0``).
        reg: If set, emit ``reg = <value>;`` before per-field properties.
        indent: Indentation for the node header line.  Properties get
            one extra ``\\t``.
    """
    cls = type(model)
    prop_indent = indent + TAB
    if overlay:
        # ``&label { ... };`` form — used to modify an existing DT node.
        lines: list[str] = [f"{indent}&{label} {{"]
        for prop in delete_properties or getattr(cls, "delete_properties", ()):
            lines.append(f"{prop_indent}/delete-property/ {prop};")
    else:
        lines = [f"{indent}{label}: {node_name} {{"]

    # Class-level fixed header.
    compatible = getattr(cls, "compatible", None)
    if compatible:
        lines.append(f'{prop_indent}compatible = "{compatible}";')
    for hkey, hval in getattr(cls, "dt_header", {}).items():
        lines.append(f"{prop_indent}{hkey} = {_fmt_value(hval)};")
    for flag in getattr(cls, "dt_flags", ()):
        lines.append(f"{prop_indent}{flag};")

    # reg = <reg>; — universal for unit-addressed nodes.
    if reg is not None:
        lines.append(f"{prop_indent}reg = <{reg}>;")

    # Extra per-instance lines spliced in before per-field rendering.
    extra = getattr(model, "extra_dt_lines", None)
    if callable(extra):
        for line in extra(context or {}):
            lines.append(f"{prop_indent}{line}")

    # Per-field properties, in declaration order.
    subnode_fields: list[tuple[DtSubnodes, Any]] = []
    for name, info in cls.model_fields.items():
        marker = _field_marker(info, cls)
        if isinstance(marker, DtSkip):
            continue
        value = getattr(model, name)
        if isinstance(marker, DtSubnodes):
            subnode_fields.append((marker, value))
            continue

        alias = info.alias
        if alias is None:
            # Not a DT property; skip silently.
            continue

        annotation = info.annotation
        if _is_bool_type(annotation):
            if value:
                lines.append(f"{prop_indent}{alias};")
            continue

        if value is None:
            continue

        if isinstance(marker, DtBits64):
            lines.append(f"{prop_indent}{alias} = /bits/ 64 <{int(value)}>;")
        else:
            lines.append(f"{prop_indent}{alias} = {_fmt_value(value)};")

    # Sub-nodes (nested DT child nodes).
    for marker, value in subnode_fields:
        if value is None:
            continue
        if isinstance(value, dict):
            for key in sorted(value.keys()):
                child = value[key]
                child_label = marker.label_template.format(
                    parent=label,
                    key=key,
                    cs=reg if reg is not None else "",
                )
                child_name = f"{marker.node_name}@{key}"
                lines.append(
                    render_node(
                        child,
                        label=child_label,
                        node_name=child_name,
                        reg=key,
                        indent=prop_indent,
                    )
                )

    # Trailing multi-line blocks (sub-nodes that don't fit DtSubnodes pattern —
    # e.g. AD9081 adi,tx-dacs / adi,rx-adcs).  Each block is pre-indented by
    # the device; the first line gets ``prop_indent`` prepended.
    trailing = getattr(model, "trailing_blocks", None)
    if callable(trailing):
        for block in trailing(context or {}):
            block = block.rstrip("\n")
            if not block:
                continue
            first, _, rest = block.partition("\n")
            lines.append(f"{prop_indent}{first}")
            if rest:
                lines.append(rest)

    if trailing_block:
        lines.append(trailing_block.rstrip("\n"))

    lines.append(f"{indent}}};")
    return "\n".join(lines)


def _is_bool_type(annotation: Any) -> bool:
    """Return True if *annotation* is ``bool`` or ``bool | None``."""
    if annotation is bool:
        return True
    args = get_args(annotation)
    if args and any(a is bool for a in args):
        return True
    return False
