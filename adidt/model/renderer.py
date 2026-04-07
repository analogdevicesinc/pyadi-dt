"""Render a :class:`BoardModel` to DTS node strings using per-component templates."""

from __future__ import annotations

import os
from collections import defaultdict
from functools import lru_cache
from typing import Any

from jinja2 import Environment, FileSystemLoader

from .board_model import BoardModel, JesdLinkModel


@lru_cache(maxsize=1)
def _template_dir() -> str:
    """Return the XSA template directory path (cached)."""
    return os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "..", "templates", "xsa"
    )


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
        env = self._make_env(model)
        result: dict[str, list[str]] = {
            "clkgens": [],
            "jesd204_rx": [],
            "jesd204_tx": [],
            "converters": [],
        }

        # Group components by SPI bus, render each, wrap in &spi_bus overlay
        spi_groups: dict[str, list[str]] = defaultdict(list)
        for comp in model.components:
            rendered = env.get_template(comp.template).render(comp.config)
            spi_groups[comp.spi_bus].append(rendered)

        for bus_label, children in spi_groups.items():
            children_str = "".join(children)
            result["converters"].append(self._wrap_spi_bus(bus_label, children_str))

        # Render JESD links: DMA overlays, TPL cores, JESD overlays, ADXCVR
        for link in model.jesd_links:
            # DMA overlay (skip when dma_label is None)
            if link.dma_label is not None:
                result["converters"].append(self._render_dma_overlay(link))
            # TPL core (skip when config is empty — builder handles it externally)
            if link.tpl_core_config:
                result["converters"].append(
                    env.get_template("tpl_core.tmpl").render(link.tpl_core_config)
                )
            # JESD204 overlay
            if link.jesd_overlay_config:
                key = f"jesd204_{link.direction}"
                result[key].append(
                    env.get_template("jesd204_overlay.tmpl").render(
                        link.jesd_overlay_config
                    )
                )
            # ADXCVR (skip when config is empty — builder handles it externally)
            if link.xcvr_config:
                result["converters"].append(
                    env.get_template("adxcvr.tmpl").render(link.xcvr_config)
                )

        # Append extra raw nodes (e.g., fixed clocks, HSCI overlays)
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
        lines.append("\t};")
        return "\n".join(lines)

    @staticmethod
    def _make_env(model: BoardModel) -> Environment:
        """Create a Jinja2 environment with model-specific reg formatting."""
        env = Environment(loader=FileSystemLoader(_template_dir()))
        # Register reg-formatting globals matching NodeBuilder._make_jinja_env
        cells = model.fpga_config.addr_cells if model.fpga_config else 2

        def _reg_addr(addr: int) -> str:
            return f"0x{addr:08x}" if cells == 1 else f"0x0 0x{addr:08x}"

        def _reg_size(size: int) -> str:
            return f"0x{size:x}" if cells == 1 else f"0x0 0x{size:x}"

        env.globals["reg_addr"] = _reg_addr  # ty: ignore[invalid-assignment]
        env.globals["reg_size"] = _reg_size  # ty: ignore[invalid-assignment]
        return env
