"""Render a :class:`BoardModel` to DTS node strings.

Every component and JESD-link carries a pre-rendered DT string produced
by the declarative device classes in :mod:`adidt.devices`.  This
renderer is a thin assembler that groups those strings by SPI bus and
JESD-link direction — no Jinja2 involved.
"""

from __future__ import annotations

from collections import defaultdict

from .board_model import BoardModel, JesdLinkModel


class BoardModelRenderer:
    """Renders a :class:`BoardModel` into DTS node strings.

    The output dict has the same shape that
    :meth:`~adidt.xsa.node_builder.NodeBuilder.build` returns::

        {"clkgens": [...], "jesd204_rx": [...], "jesd204_tx": [...], "converters": [...]}

    This allows the existing :class:`~adidt.xsa.merger.DtsMerger` to consume
    the output without changes.
    """

    def render(self, model: BoardModel) -> dict[str, list[str]]:
        """Render *model* to DTS node strings (overlay mode).

        Args:
            model: The board model to render.

        Returns:
            Dict with keys ``clkgens``, ``jesd204_rx``, ``jesd204_tx``,
            ``converters``, each mapping to a list of DTS node strings.
        """
        result: dict[str, list[str]] = {
            "clkgens": [],
            "jesd204_rx": [],
            "jesd204_tx": [],
            "converters": [],
        }

        # Group components by SPI bus, wrap in &spi_bus overlay.
        spi_groups: dict[str, list[str]] = defaultdict(list)
        for comp in model.components:
            if comp.rendered is None:
                continue  # declarative devices always pre-render
            spi_groups[comp.spi_bus].append(comp.rendered)

        for bus_label, children in spi_groups.items():
            children_str = "".join(children)
            result["converters"].append(self._wrap_spi_bus(bus_label, children_str))

        # JESD-link IP overlays (DMA, TPL core, JESD framing, ADXCVR).
        for link in model.jesd_links:
            if link.dma_label is not None:
                result["converters"].append(self._render_dma_overlay(link))
            if link.tpl_core_rendered is not None:
                result["converters"].append(link.tpl_core_rendered)
            key = f"jesd204_{link.direction}"
            if link.jesd_overlay_rendered is not None:
                result[key].append(link.jesd_overlay_rendered)
            if link.xcvr_rendered is not None:
                result["converters"].append(link.xcvr_rendered)

        # Append extra raw nodes (e.g., fixed clocks, HSCI overlays).
        result["converters"].extend(model.extra_nodes)
        return result

    @staticmethod
    def _wrap_spi_bus(label: str, children: str) -> str:
        """Wrap pre-rendered child node strings in an ``&label`` overlay."""
        if not children.endswith("\n"):
            children += "\n"
        return (
            f"\t&{label} {{\n"
            '\t\tstatus = "okay";\n'
            "\t\t#address-cells = <1>;\n"
            "\t\t#size-cells = <0>;\n"
            f"{children}"
            "\t};"
        )

    @staticmethod
    def _render_dma_overlay(link: JesdLinkModel) -> str:
        """Render an AXI DMA compatible-override overlay node."""
        lines = [
            f"\t&{link.dma_label} {{",
            "\t\t/delete-property/ compatible;",
            '\t\tcompatible = "adi,axi-dmac-1.00.a";',
            "\t\t#dma-cells = <1>;",
            "\t\t#clock-cells = <0>;",
        ]
        if link.dma_clocks_str:
            lines.append(f"\t\tclocks = {link.dma_clocks_str};")
        if link.dma_interrupts_str:
            lines.append("\t\t/delete-property/ interrupts;")
            lines.append(f"\t\tinterrupts = {link.dma_interrupts_str};")
        lines.append("\t};")
        return "\n".join(lines)
