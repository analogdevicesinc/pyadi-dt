"""AXI ADXCVR overlay model (``axi-adxcvr-1.0``)."""

from __future__ import annotations

from typing import Annotated, Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from .._dt_render import render_node
from .._fields import DtSkip


class Adxcvr(BaseModel):
    """FPGA ADXCVR IP overlay node."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    compatible: ClassVar[str] = "adi,axi-adxcvr-1.0"
    delete_properties: ClassVar[tuple[str, ...]] = (
        "compatible",
        "clocks",
        "clock-names",
        "#clock-cells",
        "clock-output-names",
        "adi,sys-clk-select",
        "adi,out-clk-select",
    )
    dt_header: ClassVar[dict[str, Any]] = {
        "#clock-cells": 1,
        "#jesd204-cells": 2,
    }
    dt_flags: ClassVar[tuple[str, ...]] = ("jesd204-device",)

    label: str

    # Aliased scalar properties.
    sys_clk_select: int = Field(..., alias="adi,sys-clk-select")
    out_clk_select: int = Field(..., alias="adi,out-clk-select")
    use_lpm_enable: bool = Field(False, alias="adi,use-lpm-enable")

    # Coupled / context-driven properties (rendered via extra_dt_lines).
    clk_ref: Annotated[str, DtSkip()] = ""
    use_div40: Annotated[bool, DtSkip()] = False
    div40_clk_ref: Annotated[str | None, DtSkip()] = None
    clock_output_names_str: Annotated[str, DtSkip()] = ""
    jesd204_inputs: Annotated[str | None, DtSkip()] = None
    jesd_l: Annotated[int | None, DtSkip()] = None
    jesd_m: Annotated[int | None, DtSkip()] = None
    jesd_s: Annotated[int | None, DtSkip()] = None

    def extra_dt_lines(self, context: dict | None = None) -> list[str]:
        lines: list[str] = []
        if self.use_div40:
            div_ref = self.div40_clk_ref or self.clk_ref
            lines.append(f"clocks = <&{self.clk_ref}>, <&{div_ref}>;")
            lines.append('clock-names = "conv", "div40";')
        else:
            lines.append(f"clocks = <&{self.clk_ref}>;")
            lines.append('clock-names = "conv";')
        if self.clock_output_names_str:
            lines.append(f"clock-output-names = {self.clock_output_names_str};")
        if self.use_div40 and self.jesd_l is not None:
            lines.append(f"adi,jesd-l = <{int(self.jesd_l)}>;")
            lines.append(f"adi,jesd-m = <{int(self.jesd_m)}>;")
            lines.append(f"adi,jesd-s = <{int(self.jesd_s)}>;")
        if self.jesd204_inputs:
            lines.append(f"jesd204-inputs = <&{self.jesd204_inputs}>;")
        return lines

    def render(self) -> str:
        """Render this overlay as a DT string."""
        return render_node(
            self,
            label=self.label,
            overlay=True,
            indent="\t",
        )
