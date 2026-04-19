"""AXI JESD204 RX/TX overlay model (``axi-jesd204-{rx,tx}-1.0``)."""

from __future__ import annotations

from typing import Annotated, Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from .._dt_render import render_node
from .._fields import DtSkip


class Jesd204Overlay(BaseModel):
    """FPGA AXI JESD204 link overlay node."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    delete_properties: ClassVar[tuple[str, ...]] = (
        "compatible",
        "clocks",
        "clock-names",
        "#clock-cells",
        "adi,octets-per-frame",
        "adi,frames-per-multiframe",
    )
    dt_header: ClassVar[dict[str, Any]] = {
        "#clock-cells": 0,
        "#jesd204-cells": 2,
    }
    dt_flags: ClassVar[tuple[str, ...]] = ("jesd204-device",)

    label: str

    # ``compatible`` is variable by direction (rx / tx); emit via instance field.
    compatible_str: str = Field(..., alias="compatible")

    # Aliased scalar / optional props.
    f: int = Field(..., alias="adi,octets-per-frame")
    k: int = Field(..., alias="adi,frames-per-multiframe")
    converter_resolution: int | None = Field(None, alias="adi,converter-resolution")
    bits_per_sample: int | None = Field(None, alias="adi,bits-per-sample")
    converters_per_device: int | None = Field(None, alias="adi,converters-per-device")
    control_bits_per_sample: int | None = Field(
        None, alias="adi,control-bits-per-sample"
    )

    # Coupled / context-driven properties (rendered via extra_dt_lines).
    direction: Annotated[str, DtSkip()] = "rx"
    clocks_str: Annotated[str, DtSkip()] = ""
    clock_names_str: Annotated[str, DtSkip()] = ""
    clock_output_name: Annotated[str | None, DtSkip()] = None
    jesd204_inputs: Annotated[str, DtSkip()] = ""

    def extra_dt_lines(self, context: dict | None = None) -> list[str]:
        lines: list[str] = []
        if self.clocks_str:
            lines.append(f"clocks = {self.clocks_str};")
        if self.clock_names_str:
            lines.append(f"clock-names = {self.clock_names_str};")
        if self.clock_output_name:
            lines.append(f'clock-output-names = "{self.clock_output_name}";')
        if self.jesd204_inputs:
            lines.append(f"jesd204-inputs = <&{self.jesd204_inputs}>;")
        return lines

    def render(self) -> str:
        return render_node(
            self,
            label=self.label,
            overlay=True,
            indent="\t",
        )
