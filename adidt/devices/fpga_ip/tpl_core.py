"""AXI TPL core overlay model (``adi,axi-<part>-{rx,tx}-1.0``)."""

from __future__ import annotations

from typing import Annotated, Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from .._dt_render import render_node
from .._fields import DtSkip


class TplCore(BaseModel):
    """FPGA TPL (transport) core overlay node."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    delete_properties: ClassVar[tuple[str, ...]] = (
        "compatible",
        "clocks",
        "clock-names",
    )
    dt_header: ClassVar[dict[str, Any]] = {"#jesd204-cells": 2}
    dt_flags: ClassVar[tuple[str, ...]] = ("jesd204-device",)

    label: str
    compatible_str: str = Field(..., alias="compatible")

    # Optional axi-pl FIFO flag.
    pl_fifo_enable: bool = Field(False, alias="adi,axi-pl-fifo-enable")

    # Coupled / phandle context.
    direction: Annotated[str, DtSkip()] = "rx"
    dma_label: Annotated[str | None, DtSkip()] = None
    spibus_label: Annotated[str, DtSkip()] = ""
    jesd_label: Annotated[str, DtSkip()] = ""
    jesd_link_offset: Annotated[int, DtSkip()] = 0
    link_id: Annotated[int, DtSkip()] = 0
    sampl_clk_ref: Annotated[str | None, DtSkip()] = None
    sampl_clk_name: Annotated[str | None, DtSkip()] = None

    def extra_dt_lines(self, context: dict | None = None) -> list[str]:
        lines: list[str] = []
        if self.dma_label is not None:
            lines.append(f"dmas = <&{self.dma_label} 0>;")
            lines.append(f'dma-names = "{self.direction}";')
        if self.sampl_clk_ref is not None:
            lines.append(f"clocks = <&{self.sampl_clk_ref}>;")
            lines.append(f'clock-names = "{self.sampl_clk_name or "sampl_clk"}";')
        if self.spibus_label:
            lines.append(f"spibus-connected = <&{self.spibus_label}>;")
        lines.append(
            f"jesd204-inputs = <&{self.jesd_label} "
            f"{int(self.jesd_link_offset)} {int(self.link_id)}>;"
        )
        return lines

    def render(self) -> str:
        return render_node(
            self,
            label=self.label,
            overlay=True,
            indent="\t",
        )
