"""AD9680 14-bit dual-channel ADC device model (declarative)."""

from __future__ import annotations

from typing import Annotated, Any, ClassVar

from pydantic import Field

from .._dt_render import render_node
from .._fields import DtBits64, DtSkip
from .base import ConverterDevice


class AD9680(ConverterDevice):
    """AD9680 14-bit ADC."""

    part: ClassVar[str] = "ad9680"
    template: ClassVar[str] = ""

    compatible: ClassVar[str] = "adi,ad9680"
    dt_header: ClassVar[dict[str, Any]] = {
        "#address-cells": 1,
        "#size-cells": 0,
        "#jesd204-cells": 2,
        "adi,converter-resolution": 14,
        "adi,control-bits-per-sample": 2,
        "adi,subclass": 1,
        "adi,input-clock-divider-ratio": 1,
    }
    dt_flags: ClassVar[tuple[str, ...]] = ("jesd204-device",)

    label: str = "adc0_ad9680"

    # Flat aliased properties.
    spi_max_hz: int = Field(1_000_000, alias="spi-max-frequency")
    jesd204_top_device: int = Field(0, alias="jesd204-top-device")
    m: int = Field(2, alias="adi,converters-per-device")
    l: int = Field(4, alias="adi,lanes-per-device")
    f: int = Field(1, alias="adi,octets-per-frame")
    k: int = Field(32, alias="adi,frames-per-multiframe")
    np: int = Field(16, alias="adi,bits-per-sample")
    sampling_frequency_hz: Annotated[int, DtBits64()] = Field(
        ..., alias="adi,sampling-frequency"
    )

    # Optional SPI-3-wire flag flips a bundle of properties.
    use_spi_3wire: Annotated[bool, DtSkip()] = False

    # SYSREF defaults emitted only when not in 3-wire mode.
    # These are fixed when emitted; surface via extra_dt_lines.
    clks_str: Annotated[str | None, DtSkip()] = None
    clk_names_str: Annotated[str | None, DtSkip()] = None

    def extra_dt_lines(self, context: dict | None = None) -> list[str]:
        ctx = context or {}
        lines: list[str] = []
        clks = self.clks_str or ctx.get("clks_str")
        clk_names = self.clk_names_str or ctx.get("clk_names_str")
        if clks:
            lines.append(f"clocks = {clks};")
        if clk_names:
            lines.append(f"clock-names = {clk_names};")

        link_ids = ctx.get("jesd204_link_ids", "0")
        lines.append(f"jesd204-link-ids = <{link_ids}>;")
        jesd_inputs = ctx.get("jesd204_inputs")
        if jesd_inputs:
            lines.append(f"jesd204-inputs = <&{jesd_inputs}>;")

        if self.use_spi_3wire:
            lines.append("spi-cpol;")
            lines.append("spi-cpha;")
            lines.append("adi,spi-3wire-enable;")
        else:
            lines.append("adi,sysref-lmfc-offset = <0>;")
            lines.append("adi,sysref-pos-window-skew = <0>;")
            lines.append("adi,sysref-neg-window-skew = <0>;")
            lines.append("adi,sysref-mode = <1>;")
            lines.append("adi,sysref-nshot-ignore-count = <0>;")

        for gl in ctx.get("gpio_lines") or []:
            lines.append(f"{gl['prop']} = <&{gl['controller']} {int(gl['index'])} 0>;")

        return lines

    def render_dt(self, *, cs: int, context: dict | None = None) -> str:
        return render_node(
            self,
            label=self.label,
            node_name=f"ad9680@{cs}",
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
