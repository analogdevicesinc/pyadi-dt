"""Builder for designs described by a profile's ``design`` section.

Most HDL designs need no bespoke logic: their device tree is a fixed set of
PL cores plus the devices on the PS buses.  A declarative profile lists
those nodes once (seeded from the kernel reference tree) and this builder
renders them against the XSA at hand -- every PL node takes its address and
interrupt from the IP instance the XSA actually contains, so a profile
cannot silently describe hardware the bitstream does not have.
"""

from __future__ import annotations

from typing import Any

from ...exceptions import ProfileError
from ...parse.topology import AxiIpInstance, XsaTopology
from ...platforms import platform_info

# Key the pipeline stores the selected profile's ``design`` section under.
DESIGN_KEY = "declarative_design"


def _cells(value: int, count: int) -> str:
    """Format *value* as *count* 32-bit device-tree cells."""
    return " ".join(
        f"0x{(value >> (32 * shift)) & 0xFFFFFFFF:x}"
        for shift in range(count - 1, -1, -1)
    )


def _indent(lines: list[str], prefix: str) -> str:
    return "".join(f"{prefix}{line}\n" if line else "\n" for line in lines)


class DeclarativeBuilder:
    """Render the nodes a declarative profile describes."""

    def matches(self, topology: XsaTopology, cfg: dict[str, Any]) -> bool:
        """Return True when the selected profile carries a ``design`` section."""
        return isinstance(cfg.get(DESIGN_KEY), dict)

    def skips_generic_jesd(self) -> bool:
        """The profile describes every node, so nothing is rendered generically."""
        return True

    def skip_ip_types(self) -> set[str]:
        """No per-type skipping: generic rendering is bypassed altogether."""
        return set()

    def build_nodes(
        self,
        node_builder: Any,
        topology: XsaTopology,
        cfg: dict[str, Any],
        ps_clk_label: str,
        ps_clk_index: int | None,
        gpio_label: str,
    ) -> list[str]:
        """Return the PL nodes followed by the root and bus overlays."""
        built = self.build(topology, cfg[DESIGN_KEY])
        return [*built["design"], *built["overlays"]]

    def build(self, topology: XsaTopology, design: dict[str, Any]) -> dict[str, Any]:
        """Render *design* for *topology*.

        Returns:
            ``{"design": [...], "overlays": [...], "replaced": [...]}`` -- PL
            bus nodes, top-level ``&target { }`` blocks, and the names of the
            XSA instances whose generated stubs the PL nodes replace.

        Raises:
            ProfileError: When the profile names an IP instance the XSA does
                not contain.
        """
        addr_cells = platform_info(topology.inferred_platform()).addr_cells
        instances = {inst.name: inst for inst in topology.ip_instances}
        resolved: list[tuple[dict[str, Any], AxiIpInstance]] = []
        missing: list[str] = []
        for entry in design.get("pl", []):
            inst = self._resolve(entry, instances, topology)
            if inst is None:
                missing.append(
                    entry.get("instance") or f"{entry['node']}@{entry['address']:x}"
                )
            else:
                resolved.append((self._bind(entry, inst), inst))
        if missing:
            raise ProfileError(
                "the XSA lacks IP instances the profile describes: "
                + ", ".join(sorted(missing))
            )

        # The base tree refers to its stubs by instance name (``aliases``,
        # clock consumers), so the first node of each instance keeps that
        # name as a label once the stub is deleted.
        labelled: set[str] = set()
        pl_nodes = []
        for entry, inst in resolved:
            stub_label = inst.name.replace("-", "_")
            labels = list(entry.get("labels", []))
            if inst.name not in labelled and stub_label not in labels:
                labels.append(stub_label)
            labelled.add(inst.name)
            pl_nodes.append(
                self._pl_node({**entry, "labels": labels}, inst, addr_cells)
            )
        pl_nodes += [
            _indent(lines, "\t").rstrip("\n") for lines in design.get("bus", [])
        ]
        overlays: list[str] = []
        root_lines = design.get("root", [])
        if root_lines:
            overlays.append("&{/} {\n" + _indent(root_lines, "\t") + "};")
        for overlay in design.get("overlays", []):
            overlays.append(
                f"{overlay['target']} {{\n" + _indent(overlay["body"], "\t") + "};"
            )
        return {
            "design": pl_nodes,
            "overlays": overlays,
            "replaced": list(dict.fromkeys(inst.name for _, inst in resolved)),
        }

    @staticmethod
    def _resolve(
        entry: dict[str, Any],
        instances: dict[str, AxiIpInstance],
        topology: XsaTopology,
    ) -> AxiIpInstance | None:
        """Return the XSA instance *entry* describes.

        Entries seeded with an XSA name their instance.  Entries seeded from
        a reference tree alone only know an address, and are bound to
        whichever IP has that address in the XSA at hand.
        """
        if "instance" in entry:
            return instances.get(entry["instance"])
        address = entry["address"]
        for inst in topology.ip_instances:
            if inst.base_addr == address:
                return inst
        for inst in topology.ip_instances:
            if inst.base_addr <= address < inst.base_addr + inst.size:
                return inst
        return None

    @staticmethod
    def _bind(entry: dict[str, Any], inst: AxiIpInstance) -> dict[str, Any]:
        """Express an address-keyed entry relative to the instance it bound to."""
        if "instance" in entry:
            return entry
        shift = entry["address"] - inst.base_addr
        bound = dict(entry, offset=shift)
        if entry.get("reg"):
            bound["reg"] = [[offset + shift, size] for offset, size in entry["reg"]]
        return bound

    @staticmethod
    def _pl_node(entry: dict[str, Any], inst: AxiIpInstance, addr_cells: int) -> str:
        labels = "".join(f"{label}: " for label in entry.get("labels", []))
        body = list(entry.get("body", []))
        generated: list[str] = []
        if entry.get("reg"):
            pairs = ", ".join(
                f"<{_cells(inst.base_addr + offset, addr_cells)} "
                f"{_cells(size, addr_cells)}>"
                for offset, size in entry["reg"]
            )
            generated.append(f"reg = {pairs};")
        flags = entry.get("interrupt_flags")
        if flags is not None and inst.irq is not None:
            spi = "" if entry.get("interrupt_cells") == 2 else "0 "
            generated.append(f"interrupts = <{spi}{inst.irq} {flags}>;")
        # Keep ``compatible`` first, as device-tree style expects.
        split = 1 if body and body[0].startswith("compatible") else 0
        lines = [*body[:split], *generated, *body[split:]]
        return (
            f"\t{labels}{entry['node']}@{inst.base_addr + entry.get('offset', 0):x} {{\n"
            + _indent(lines, "\t\t")
            + "\t};"
        )
