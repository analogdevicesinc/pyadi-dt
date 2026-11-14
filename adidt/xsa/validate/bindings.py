"""Check that a generated tree binds the same ADI drivers as a reference tree."""

from __future__ import annotations

from collections import Counter

from ..declarative.dts_source import DtsNode, DtsTree


def _enabled(node: DtsNode) -> bool:
    status = node.properties.get("status")
    return status is None or status.value is None or "disabled" not in status.value


def adi_bindings(tree: DtsTree) -> Counter[str]:
    """Return how many enabled nodes bind each ``adi,*`` compatible in *tree*.

    Only a node's first (most specific) compatible is counted: that is the
    one that says which device the node describes.
    """
    counts: Counter[str] = Counter()
    for node in tree.root.walk():
        compatible = node.compatible()
        if compatible and compatible[0].startswith("adi,") and _enabled(node):
            counts[compatible[0]] += 1
    return counts


def missing_bindings(reference: DtsTree, generated: DtsTree) -> dict[str, int]:
    """Return ``{compatible: shortfall}`` for bindings *generated* lacks.

    A design is covered when every ADI device the reference tree describes
    is described at least as many times in the generated tree.
    """
    have = adi_bindings(generated)
    return {
        compatible: count - have[compatible]
        for compatible, count in sorted(adi_bindings(reference).items())
        if have[compatible] < count
    }
