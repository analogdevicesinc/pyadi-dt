"""ADF4382 microwave wideband synthesizer device model (declarative)."""

from __future__ import annotations

from typing import Annotated, Any, ClassVar

from pydantic import Field

from .._dt_render import render_node
from .._fields import DtBits64, DtSkip
from .base import ClockDevice


class ADF4382(ClockDevice):
    """ADF4382 wideband frequency synthesizer."""

    part: ClassVar[str] = "adf4382"
    template: ClassVar[str] = ""

    compatible: ClassVar[str] = "adi,adf4382"
    dt_header: ClassVar[dict[str, Any]] = {
        "#clock-cells": 1,
        "#io-channel-cells": 1,
    }

    label: str = "adf4382"
    spi_max_hz: int = Field(1_000_000, alias="spi-max-frequency")
    spi_3wire: bool = Field(False, alias="adi,spi-3wire-enable")
    power_up_frequency: Annotated[int | None, DtBits64()] = Field(
        None, alias="adi,power-up-frequency"
    )
    charge_pump_microamp: int | None = Field(None, alias="adi,charge-pump-microamp")
    output_power: int | None = Field(None, alias="adi,output-power-value")

    # Coupled / verbatim values.
    clks_str: Annotated[str | None, DtSkip()] = None
    clock_output_names_str: Annotated[str | None, DtSkip()] = None
    compatible_id: Annotated[str, DtSkip()] = "adf4382"

    def extra_dt_lines(self, context: dict | None = None) -> list[str]:
        lines: list[str] = []
        if self.clks_str:
            lines.append(f"clocks = {self.clks_str};")
            lines.append('clock-names = "ref_clk";')
        if self.clock_output_names_str:
            lines.append(f"clock-output-names = {self.clock_output_names_str};")
        # The template emits a ``label = "..."`` property at the end.
        lines.append(f'label = "{self.label}";')
        return lines

    def render_dt(self, *, cs: int, context: dict | None = None) -> str:
        return render_node(
            self,
            label=self.label,
            node_name=f"{self.compatible_id}@{cs}",
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
