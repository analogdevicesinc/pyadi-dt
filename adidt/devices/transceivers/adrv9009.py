"""ADRV9009 / ADRV9025 transceiver device model (declarative renderer).

Supports both the single-chip node and the FMComms8 dual-chip layout:
the builder instantiates two :class:`ADRV9009` objects with different
labels / chip-selects / clocks and calls :meth:`render_dt` on each.  The
shared JESD / profile context flows through the System-supplied
``context`` dict.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar

from pydantic import Field

from .._dt_render import render_node
from .._fields import DtSkip
from ..converters.base import ConverterDevice, Jesd204Settings


class ADRV9009(ConverterDevice):
    """ADRV9009 / ADRV9025 / ADRV937x wideband RF transceiver."""

    part: ClassVar[str] = "adrv9009"
    template: ClassVar[str] = ""

    # Variable compatible + node-name between variants: instance fields below.
    dt_header: ClassVar[dict[str, Any]] = {
        "#clock-cells": 1,
        "clock-output-names": ["rx_sampl_clk", "rx_os_sampl_clk", "tx_sampl_clk"],
        "#jesd204-cells": 2,
        "jesd204-top-device": 0,
    }
    dt_flags: ClassVar[tuple[str, ...]] = ("jesd204-device",)

    label: str = "trx0_adrv9009"
    node_name_base: Annotated[str, DtSkip()] = "adrv9009-phy"

    # ``compatible`` is per-instance (adrv9009 vs adrv9025 vs adrv9009-x2).
    compatible_strings: list[str] = Field(
        default_factory=lambda: ["adi,adrv9009", "adrv9009"],
        alias="compatible",
    )

    spi_max_hz: int = Field(25_000_000, alias="spi-max-frequency")

    jesd204_settings: Jesd204Settings = Field(default_factory=Jesd204Settings)

    # Coupled GPIO / phandle properties — rendered via extra_dt_lines.
    reset_gpio: Annotated[int | None, DtSkip()] = None
    sysref_req_gpio: Annotated[int | None, DtSkip()] = None

    # ---- Rendering ---------------------------------------------------

    def extra_dt_lines(self, context: dict | None = None) -> list[str]:
        ctx = context or {}
        lines: list[str] = []
        gpio_label = ctx.get("gpio_label", "gpio")

        # clocks / clock-names come from context (strings like
        # ``"<&hmc7044 0>, <&hmc7044 1>"`` and ``'"dev_clk", "fmc_clk", ...'``).
        clocks_value = ctx.get("clocks_value")
        clock_names_value = ctx.get("clock_names_value")
        if clocks_value:
            lines.append(f"clocks = {clocks_value};")
        if clock_names_value:
            lines.append(f"clock-names = {clock_names_value};")

        if self.reset_gpio is not None:
            lines.append(f"reset-gpios = <&{gpio_label} {int(self.reset_gpio)} 0>;")
        if self.sysref_req_gpio is not None:
            lines.append(
                f"sysref-req-gpios = <&{gpio_label} {int(self.sysref_req_gpio)} 0>;"
            )

        link_ids = ctx.get("link_ids")
        if link_ids:
            lines.append(f"jesd204-link-ids = <{link_ids}>;")
        jesd_inputs = ctx.get("jesd204_inputs")
        if jesd_inputs:
            lines.append(f"jesd204-inputs = {jesd_inputs};")

        return lines

    def trailing_blocks(self, context: dict | None = None) -> list[str]:
        """Return the per-profile adi,* lines as a single raw block."""
        ctx = context or {}
        props = ctx.get("profile_props") or []
        if not props:
            return []
        # Each prop is a complete DT statement; join into one block so the
        # renderer drops them all between the last field and ``};``.
        lines = list(props)
        first, rest = lines[0], lines[1:]
        if rest:
            indented_rest = "\n".join(f"\t\t\t{line}" for line in rest)
            return [f"{first}\n{indented_rest}"]
        return [first]

    def render_dt(self, *, cs: int, context: dict | None = None) -> str:
        """Render this device as a DT node string."""
        return render_node(
            self,
            label=self.label,
            node_name=f"{self.node_name_base}@{cs}",
            reg=cs,
            context=context,
        )

    def to_component_model(
        self, *, spi_bus: str, spi_cs: int, extra: dict[str, Any] | None = None
    ):
        from adidt.model.board_model import ComponentModel

        return ComponentModel(
            role=self.role,
            part=self.part,
            spi_bus=spi_bus,
            spi_cs=spi_cs,
            rendered=self.render_dt(cs=spi_cs, context=extra),
        )
