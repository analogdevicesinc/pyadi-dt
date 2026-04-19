"""AD9172 wideband DAC device model (declarative renderer)."""

from __future__ import annotations

from typing import Annotated, Any, ClassVar

from pydantic import Field

from .._dt_render import render_node
from .._fields import DtSkip
from .base import ConverterDevice


class AD9172(ConverterDevice):
    """AD9172 wideband RF DAC."""

    part: ClassVar[str] = "ad9172"
    template: ClassVar[str] = ""

    compatible: ClassVar[str] = "adi,ad9172"
    dt_header: ClassVar[dict[str, Any]] = {
        "#address-cells": 1,
        "#size-cells": 0,
        "#jesd204-cells": 2,
        "jesd204-top-device": 0,
        "adi,jesd-subclass": 1,
        "adi,scrambling": 1,
        "adi,sysref-mode": 2,
    }
    dt_flags: ClassVar[tuple[str, ...]] = (
        "adi,syncoutb-signal-type-lvds-enable",
        "jesd204-device",
    )

    label: str = "dac0_ad9172"

    # Flat aliased properties.
    spi_max_hz: int = Field(1_000_000, alias="spi-max-frequency")
    dac_rate_khz: int = Field(..., alias="adi,dac-rate-khz")
    jesd_link_mode: int = Field(..., alias="adi,jesd-link-mode")
    dac_interpolation: int = Field(..., alias="adi,dac-interpolation")
    channel_interpolation: int = Field(..., alias="adi,channel-interpolation")
    clock_output_divider: int = Field(..., alias="adi,clock-output-divider")
    jesd_link_ids: list[int] = Field(
        default_factory=lambda: [0], alias="jesd204-link-ids"
    )

    # Coupled phandle properties (System / XSA-supplied context).
    clk_ref: Annotated[str | None, DtSkip()] = None

    def extra_dt_lines(self, context: dict | None = None) -> list[str]:
        ctx = context or {}
        lines: list[str] = []
        clk_ref = self.clk_ref or ctx.get("clk_ref")
        if clk_ref:
            lines.append(f"clocks = <&{clk_ref}>;")
            lines.append('clock-names = "dac_clk";')
        jesd_inputs = ctx.get("jesd204_inputs")
        if jesd_inputs:
            lines.append(f"jesd204-inputs = <&{jesd_inputs}>;")
        return lines

    def render_dt(self, *, cs: int, context: dict | None = None) -> str:
        return render_node(
            self,
            label=self.label,
            node_name=f"ad9172@{cs}",
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
