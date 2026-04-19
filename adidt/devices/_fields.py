"""Field markers for declarative device-tree rendering.

Most pydantic fields on a :class:`Device` become DT node properties
implicitly, based on the field type and alias:

- ``int``, ``list[int]``, ``str``, ``list[str]`` with ``Field(alias="adi,...")``
  → emitted as ``<alias> = <value>;``
- ``bool`` with ``Field(alias="adi,...")``
  → emitted as the bare ``<alias>;`` flag when ``True``; omitted when ``False``
- optional fields (default ``None``) are omitted when unset

Fields that do not map 1:1 to a DT property use an explicit marker via
``typing.Annotated``:

- :class:`DtSubnodes` — a ``dict[key, child_model]`` becomes a sequence
  of child DT nodes (e.g. HMC7044 channels).
- :class:`DtSkip` — exclude the field from rendering (e.g. ``label``,
  ``clock_output_names`` when pre-joined into another property).

Fields without an alias (the field's ``Field(alias=...)`` is unset) are
also skipped unless annotated with a marker.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DtSubnodes:
    """Annotate a ``dict[key, child_model]`` field as a list of sub-nodes.

    Attributes:
        node_name: Base node name — rendered as ``<node_name>@<key>``.
            Example: ``"channel"`` → ``channel@0 { ... };``.
        label_template: Python ``str.format`` template for the child
            node's DT label.  ``{parent}`` resolves to the parent device
            label; ``{key}`` resolves to the dict key.
            Example: ``"{parent}_c{key}"`` →  ``hmc7044_c0``.
    """

    node_name: str
    label_template: str = "{parent}_c{key}"


@dataclass(frozen=True)
class DtSkip:
    """Annotate a field to be excluded from DT rendering.

    Used for fields that only exist for Python-side orchestration
    (Ports, raw-channel escape hatches, pre-joined strings consumed
    by computed properties, etc.).
    """


@dataclass(frozen=True)
class DtBits64:
    """Emit ``<alias> = /bits/ 64 <value>;`` (64-bit cells) for this int field.

    DT uses ``/bits/ 64`` to carry values that don't fit in a 32-bit
    cell — typically sampling / converter frequencies at gigahertz
    scale.  Without this marker, an ``int`` field renders as a plain
    ``<value>`` which the compiler will truncate.
    """
