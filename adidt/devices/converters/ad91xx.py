"""AD9144 / AD9152 DAC device models (declarative)."""

from __future__ import annotations

from typing import Annotated, Any, ClassVar

from pydantic import Field

from .._dt_render import render_node
from .._fields import DtSkip
from .base import ConverterDevice


class _AD91xxBase(ConverterDevice):
    """Shared rendering for AD9144 / AD9152."""

    node_kind: ClassVar[str] = ""

    label: str = "dac0"
    spi_max_hz: int = Field(1_000_000, alias="spi-max-frequency")
    jesd204_top_device: int = Field(1, alias="jesd204-top-device")
    subclass: int = Field(1, alias="adi,subclass")
    interpolation: int = Field(1, alias="adi,interpolation")

    clk_ref: Annotated[str | None, DtSkip()] = None

    def extra_dt_lines(self, context: dict | None = None) -> list[str]:
        ctx = context or {}
        lines: list[str] = []
        clk_ref = self.clk_ref or ctx.get("clk_ref")
        if clk_ref:
            lines.append(f"clocks = <&{clk_ref}>;")
            lines.append('clock-names = "dac_clk";')

        link_ids = ctx.get("jesd204_link_ids", "0")
        lines.append(f"jesd204-link-ids = <{link_ids}>;")
        jesd_inputs = ctx.get("jesd204_inputs")
        if jesd_inputs:
            lines.append(f"jesd204-inputs = <&{jesd_inputs}>;")

        for gl in ctx.get("gpio_lines") or []:
            lines.append(f"{gl['prop']} = <&{gl['controller']} {int(gl['index'])} 0>;")
        return lines

    def render_dt(self, *, cs: int, context: dict | None = None) -> str:
        return render_node(
            self,
            label=self.label,
            node_name=f"{self.node_kind}@{cs}",
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


class AD9144(_AD91xxBase):
    """AD9144 quad DAC."""

    part: ClassVar[str] = "ad9144"
    template: ClassVar[str] = ""
    node_kind: ClassVar[str] = "ad9144"

    compatible: ClassVar[str] = "adi,ad9144"
    dt_header: ClassVar[dict[str, Any]] = {
        "#address-cells": 1,
        "#size-cells": 0,
        "#jesd204-cells": 2,
    }
    dt_flags: ClassVar[tuple[str, ...]] = ("jesd204-device",)

    label: str = "dac0_ad9144"


class AD9152(_AD91xxBase):
    """AD9152 dual DAC."""

    part: ClassVar[str] = "ad9152"
    template: ClassVar[str] = ""
    node_kind: ClassVar[str] = "ad9152"

    compatible: ClassVar[str] = "adi,ad9152"
    dt_header: ClassVar[dict[str, Any]] = {
        "#address-cells": 1,
        "#size-cells": 0,
        "#jesd204-cells": 2,
    }
    dt_flags: ClassVar[tuple[str, ...]] = (
        "spi-cpol",
        "spi-cpha",
        "adi,spi-3wire-enable",
        "jesd204-device",
    )

    label: str = "dac0_ad9152"
    jesd_link_mode: int = Field(4, alias="adi,jesd-link-mode")
