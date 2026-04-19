"""AD9084 wideband RF MxFE device model (declarative renderer)."""

from __future__ import annotations

from typing import Annotated, Any, ClassVar

from pydantic import Field

from .._dt_render import render_node
from .._fields import DtSkip
from .base import ConverterDevice, ConverterSide


_AD9084_RX_MODE_TABLE: dict[tuple[int, str] | int, dict[str, int]] = {
    (1, "jesd204c"): {"M": 2, "L": 1, "F": 4, "K": 32, "Np": 16, "S": 1},
    (18, "jesd204c"): {"M": 4, "L": 8, "F": 1, "K": 32, "Np": 16, "S": 1},
}

_AD9084_TX_MODE_TABLE: dict[tuple[int, str] | int, dict[str, int]] = {
    (1, "jesd204c"): {"M": 2, "L": 1, "F": 4, "K": 32, "Np": 16, "S": 1},
    (17, "jesd204c"): {"M": 4, "L": 8, "F": 2, "K": 32, "Np": 16, "S": 1},
}


class AD9084Adc(ConverterSide):
    """AD9084 RX (ADC) configuration."""

    MODE_TABLE: ClassVar[dict] = _AD9084_RX_MODE_TABLE

    cddc_decimation: int = 1
    fddc_decimation: int = 1


class AD9084Dac(ConverterSide):
    """AD9084 TX (DAC) configuration."""

    MODE_TABLE: ClassVar[dict] = _AD9084_TX_MODE_TABLE

    cduc_interpolation: int = 1
    fduc_interpolation: int = 1


class AD9084(ConverterDevice):
    """AD9084 wideband RF MxFE."""

    part: ClassVar[str] = "ad9084"
    template: ClassVar[str] = ""

    compatible: ClassVar[str] = "adi,ad9084"
    dt_header: ClassVar[dict[str, Any]] = {
        "#clock-cells": 1,
        "clock-output-names": ["rx_sampl_clk", "tx_sampl_clk"],
        "#jesd204-cells": 2,
        "jesd204-top-device": 0,
    }
    dt_flags: ClassVar[tuple[str, ...]] = ("jesd204-device", "jesd204-ignore-errors")

    label: str = "ad9084"

    # --- Flat aliased properties ---------------------------------------
    spi_max_hz: int = Field(5_000_000, alias="spi-max-frequency")
    firmware_name: str | None = Field(None, alias="adi,device-profile-fw-name")
    subclass: int | None = Field(1, alias="adi,subclass")
    side_b_separate_tpl: bool = Field(False, alias="adi,side-b-use-seperate-tpl-en")
    hsci_auto_linkup: bool = Field(False, alias="adi,hsci-auto-linkup-mode-en")

    # --- Properties with cells-style raw strings (no auto-format) -------
    # These render as ``<alias> = <{value}>;`` with the value spliced inside
    # ``<>`` verbatim (e.g. ``"7 4"``); coupled emission via extra_dt_lines.
    dev_clk_scales: Annotated[str | None, DtSkip()] = None
    jrx0_physical_lane_mapping: Annotated[str | None, DtSkip()] = None
    jtx0_logical_lane_mapping: Annotated[str | None, DtSkip()] = None
    jrx1_physical_lane_mapping: Annotated[str | None, DtSkip()] = None
    jtx1_logical_lane_mapping: Annotated[str | None, DtSkip()] = None

    # --- Coupled properties (gpio_label / phandle references) ----------
    reset_gpio: Annotated[int | None, DtSkip()] = None
    hsci_label: Annotated[str | None, DtSkip()] = None

    # --- Python-only state ---------------------------------------------
    adc: Annotated[AD9084Adc, DtSkip()] = Field(default_factory=AD9084Adc)
    dac: Annotated[AD9084Dac, DtSkip()] = Field(default_factory=AD9084Dac)

    # ---- API ----------------------------------------------------------

    def set_jesd204_mode(self, mode: int, jesd_class: str) -> None:
        self.adc.set_jesd204_mode(mode, jesd_class)
        self.dac.set_jesd204_mode(mode, jesd_class)

    @property
    def jesd204_settings(self) -> dict[str, Any]:
        return {"rx": self.adc.jesd204_settings, "tx": self.dac.jesd204_settings}

    # ---- Rendering ----------------------------------------------------

    def extra_dt_lines(self, context: dict | None = None) -> list[str]:
        ctx = context or {}
        lines: list[str] = []

        if self.reset_gpio is not None:
            gpio_label = ctx.get("gpio_label", "gpio")
            lines.append(f"reset-gpios = <&{gpio_label} {int(self.reset_gpio)} 0>;")

        dev_clk_ref = ctx.get("dev_clk_ref")
        if dev_clk_ref:
            lines.append(f"clocks = <&{dev_clk_ref}>;")
            lines.append('clock-names = "dev_clk";')

        if self.dev_clk_scales is not None:
            lines.append(f"dev_clk-clock-scales = <{self.dev_clk_scales}>;")

        if self.hsci_label is not None:
            lines.append(f"adi,axi-hsci-connected = <&{self.hsci_label}>;")

        for name, value in (
            ("adi,jrx0-physical-lane-mapping", self.jrx0_physical_lane_mapping),
            ("adi,jtx0-logical-lane-mapping", self.jtx0_logical_lane_mapping),
            ("adi,jrx1-physical-lane-mapping", self.jrx1_physical_lane_mapping),
            ("adi,jtx1-logical-lane-mapping", self.jtx1_logical_lane_mapping),
        ):
            if value is not None:
                lines.append(f"{name} = <{value}>;")

        link_ids = ctx.get("link_ids")
        if link_ids is None:
            link_ids = (
                f"{int(self.adc.jesd204_settings.link_id)} "
                f"{int(self.dac.jesd204_settings.link_id)}"
            )
        lines.append(f"jesd204-link-ids = <{link_ids}>;")

        jesd204_inputs = ctx.get("jesd204_inputs")
        if jesd204_inputs:
            lines.append(f"jesd204-inputs = {jesd204_inputs};")

        return lines

    def render_dt(self, *, cs: int, context: dict | None = None) -> str:
        """Render this device as a DT node string."""
        return render_node(
            self,
            label=self.label,
            node_name=f"ad9084@{cs}",
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
