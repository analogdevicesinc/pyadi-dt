"""DTS property inspection + cross-path comparison helpers.

Most hardware-probe failures on the System-API path today look like
"System emits property X; XSA path (known to probe) emits Y".  That
diff is visible in the generated DTS *before* anything is flashed, so
a plain-text inspector that can pull a handful of kernel-critical
properties out of any DTS and diff them against a reference catches
the bug in unit tests rather than on hardware.

Two entry points:

``extract_props``
    Grep the emitted DTS text for a curated set of kernel-critical
    properties (``compatible``, ``adi,link-mode``,
    ``adi,converters-per-device``, HMC7044 channel dividers, …).
    Returns a ``{name: value}`` dict of first occurrences, with a
    channel-qualified key for HMC7044 channels.  Intentionally a
    text grep — sufficient for the properties the AD9081 /
    ad_ip_jesd204_tpl driver probes read.

``compare_properties``
    Compute the set difference between two inspectors' outputs and
    return a list of human-readable diffs.  No-op on keys only
    present in one side.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

__all__ = [
    "extract_props",
    "compare_properties",
    "KERNEL_CRITICAL_KEYS",
]


# Properties whose value actually feeds the AD9081 / jesd204 driver
# probe path.  Ordered roughly by where they appear in the DTS.
KERNEL_CRITICAL_KEYS: tuple[str, ...] = (
    # Top-level AD9081 dev_clk wiring.
    "ad9081:clocks",
    "ad9081:clock-names",
    # DAC (host-TX / jrx) framing.
    "tx-dacs:adi,dac-frequency-hz",
    "tx-dacs:adi,link-mode",
    "tx-dacs:adi,converters-per-device",
    "tx-dacs:adi,lanes-per-device",
    "tx-dacs:adi,octets-per-frame",
    "tx-dacs:adi,frames-per-multiframe",
    "tx-dacs:adi,bits-per-sample",
    "tx-dacs:adi,samples-per-converter-per-frame",
    # ADC (host-RX / jtx) framing.
    "rx-adcs:adi,adc-frequency-hz",
    "rx-adcs:adi,link-mode",
    "rx-adcs:adi,converters-per-device",
    "rx-adcs:adi,lanes-per-device",
    "rx-adcs:adi,octets-per-frame",
    "rx-adcs:adi,frames-per-multiframe",
    # HMC7044 channel dividers (full set; missing channels just
    # get filtered out by the compare).
    "channel@0:adi,divider",
    "channel@2:adi,divider",
    "channel@3:adi,divider",
    "channel@6:adi,divider",
    "channel@8:adi,divider",
    "channel@10:adi,divider",
    "channel@12:adi,divider",
    "channel@13:adi,divider",
)


# Matches a single property line like ``adi,link-mode = <9>;``,
# capturing the name (group 1) and the RHS (group 2, without trailing ;).
_PROP_RE = re.compile(r"^\s*([A-Za-z0-9,#_.-]+)\s*=\s*(.+?)\s*;\s*$")

# Matches the opening brace of a named DT node or anonymous node with
# reg@N addressing: ``label: node@addr {``, ``node {``, ``node@0 {``.
_NODE_RE = re.compile(
    r"^\s*(?:([A-Za-z0-9_]+):\s*)?([A-Za-z][A-Za-z0-9,#_-]*(?:@[0-9a-fA-F]+)?)\s*\{\s*$"
)


# When choosing a key prefix for a property, prefer one of these
# ancestors over the innermost node — they're the "grouping nodes" the
# tests care about (``tx-dacs:adi,link-mode`` is far more useful than
# ``link@0:adi,link-mode`` since a DTS can technically nest arbitrarily).
_GROUPING_ANCESTORS: tuple[str, ...] = (
    "channel@0",
    "channel@1",
    "channel@2",
    "channel@3",
    "channel@4",
    "channel@5",
    "channel@6",
    "channel@7",
    "channel@8",
    "channel@9",
    "channel@10",
    "channel@11",
    "channel@12",
    "channel@13",
    "adi,tx-dacs",
    "adi,rx-adcs",
    # Converter / transceiver top-level nodes.  ``@addr`` is stripped
    # in ``_choose_prefix`` so ``ad9081@0`` keys as ``ad9081``.
    "ad9081",
    "ad9084",
    "ad9371-phy",
    "ad9371",
    "adrv9009-phy",
    "adrv9009",
    # Clock distributor / synthesizer chips.
    "ad9523-1",
    "ad9528-1",
    "ad9528",
    "hmc7044",
    # FPGA-side JESD204 IP blocks + TPL cores.
    "axi-adxcvr",
    "axi-clkgen",
    "ad_ip_jesd204_tpl_adc",
    "ad_ip_jesd204_tpl_dac",
)

# Normalise ancestor names to the short form used as a key prefix.
_ANCESTOR_ALIAS: dict[str, str] = {
    "adi,tx-dacs": "tx-dacs",
    "adi,rx-adcs": "rx-adcs",
    "ad9528-1": "ad9528",
    "ad9371-phy": "ad9371",
    "adrv9009-phy": "adrv9009",
}


def _choose_prefix(stack: list[str]) -> str | None:
    """Pick the most specific 'interesting' ancestor from *stack*.

    Walk the stack innermost-first, return the first ancestor that
    appears in :data:`_GROUPING_ANCESTORS`, with ``@addr`` stripped
    off of ad9081/hmc7044-style nodes.
    """
    for node in reversed(stack):
        # Try the exact form first (channel@N, adi,tx-dacs).
        if node in _GROUPING_ANCESTORS:
            return _ANCESTOR_ALIAS.get(node, node)
        # Then the @addr-stripped form (ad9081@0 → ad9081).
        base = node.split("@", 1)[0]
        if base in _GROUPING_ANCESTORS:
            return _ANCESTOR_ALIAS.get(base, base)
    return None


def extract_props(dts_text: str) -> dict[str, str]:
    """Return ``{"<grouping-ancestor>:<prop>": "<rhs>"}`` for the DTS text.

    The grouping ancestor is the most specific enclosing node from
    :data:`_GROUPING_ANCESTORS` — so a property nested several levels
    deep inside ``adi,tx-dacs`` still gets keyed under ``tx-dacs:``
    rather than whatever the innermost node happens to be (e.g.
    ``link@0``).  First-occurrence wins; the base node's value is what
    the kernel sees at probe time before any ``&label`` overlays.

    The parser normalises multi-node-on-one-line patterns (common in
    merged DTS output: ``};		foo: bar@0 {``) by splitting
    those onto separate logical lines before the line-oriented match
    step runs.
    """
    node_stack: list[str] = []
    out: dict[str, str] = {}

    # Normalise multi-brace-per-line DTS shapes so the line-oriented
    # matchers below see one structural event per line:
    #   ``};		foo: bar@0 {``  →  ``};\n\tfoo: bar@0 {``
    normalised: list[str] = []
    for raw in dts_text.splitlines():
        # Split on ``};`` (keeping the match itself as a standalone line).
        parts = re.split(r"(\};)", raw)
        for part in parts:
            if part == "":
                continue
            if part == "};":
                normalised.append("};")
            else:
                normalised.append(part)

    for line in normalised:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == "};":
            if node_stack:
                node_stack.pop()
            continue
        node_match = _NODE_RE.match(line)
        if node_match:
            _label, name = node_match.groups()
            node_stack.append(name)
            continue
        prop_match = _PROP_RE.match(line)
        if prop_match:
            name, rhs = prop_match.groups()
            prefix = _choose_prefix(node_stack)
            if prefix is None:
                continue
            key = f"{prefix}:{name}"
            if key not in out:
                out[key] = rhs
    return out


def compare_properties(
    reference: dict[str, str],
    candidate: dict[str, str],
    keys: Iterable[str] = KERNEL_CRITICAL_KEYS,
) -> list[str]:
    """Compare two ``extract_props`` outputs.  Returns diff lines.

    - Keys present in both with different values → a ``"X: ref=... cand=..."`` line.
    - Keys in ``reference`` but missing from ``candidate`` → ``"X: missing in candidate"``.
    - Keys in ``candidate`` but missing from ``reference`` → not flagged
      (reference may be less verbose; tests use ``keys`` to pin what
      they actually care about).
    """
    diffs: list[str] = []
    for key in keys:
        if key not in reference:
            continue
        ref = reference[key]
        cand = candidate.get(key)
        if cand is None:
            diffs.append(f"{key}: missing in candidate (reference={ref})")
        elif cand != ref:
            diffs.append(f"{key}: reference={ref!r}  candidate={cand!r}")
    return diffs
