"""Reusable feature-driven model for JESD204 MxFE converters.

Part-specific models should declare a :class:`MxFEFeatures` value and only
provide unique mode tables, datapath fields, and DT sub-block renderers.  The
common SPI node, JESD side, clock, GPIO, link-id, and board-model behaviour is
implemented here so new MxFE parts do not copy an AD9081-shaped core.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, ClassVar

from pydantic import Field

from .._dt_render import render_node
from .._fields import DtSkip
from .base import ConverterDevice, ConverterSide


@dataclass(frozen=True)
class MxFEFeatures:
    """Static capabilities used by a generic MxFE device model.

    Attributes:
        part: Driver part name and default SPI node stem.
        compatible: DeviceTree compatible string.
        default_label: Default DeviceTree label.
        dt_flags: DeviceTree boolean flags required by the driver.
        gpio_properties: GPIO property names the part accepts.
    """

    part: str
    compatible: str
    default_label: str
    dt_flags: tuple[str, ...] = ("jesd204-device",)
    gpio_properties: tuple[str, ...] = ("reset-gpios",)
    clock_output_names: tuple[str, str] = ("rx_sampl_clk", "tx_sampl_clk")


class MxFEAdc(ConverterSide):
    """Reusable ADC-side MxFE state with optional cascaded decimation."""

    cddc_decimation: int = 1
    fddc_decimation: int = 1
    converter_clock: int | None = None

    def converter_clock_hz(self) -> int:
        """Return configured or derived ADC converter clock."""
        if self.converter_clock is not None:
            return int(self.converter_clock)
        return int(self.sample_rate) * int(self.cddc_decimation or 1) * int(self.fddc_decimation or 1)


class MxFEDac(ConverterSide):
    """Reusable DAC-side MxFE state with optional cascaded interpolation."""

    cduc_interpolation: int = 1
    fduc_interpolation: int = 1
    converter_clock: int | None = None

    def converter_clock_hz(self) -> int:
        """Return configured or derived DAC converter clock."""
        if self.converter_clock is not None:
            return int(self.converter_clock)
        return int(self.sample_rate) * int(self.cduc_interpolation or 1) * int(self.fduc_interpolation or 1)


class MxFEDevice(ConverterDevice):
    """Feature-driven base for converters with independent ADC and DAC sides."""

    FEATURES: ClassVar[MxFEFeatures]
    compatible: ClassVar[str]
    template: ClassVar[str] = ""
    dt_header: ClassVar[dict[str, Any]]
    dt_flags: ClassVar[tuple[str, ...]]

    label: str
    spi_max_hz: int = Field(5_000_000, alias="spi-max-frequency")
    adc: Annotated[MxFEAdc, DtSkip()] = Field(default_factory=MxFEAdc)
    dac: Annotated[MxFEDac, DtSkip()] = Field(default_factory=MxFEDac)
    gpio_values: Annotated[dict[str, int | None], DtSkip()] = Field(default_factory=dict)

    @classmethod
    def configure_features(cls, features: MxFEFeatures) -> None:
        """Apply a declarative feature set to a concrete compatibility adapter."""
        cls.FEATURES = features
        cls.part = features.part
        cls.compatible = features.compatible
        cls.dt_header = {
            "#clock-cells": 1,
            "clock-output-names": list(features.clock_output_names),
            "#jesd204-cells": 2,
            "jesd204-top-device": 0,
        }
        cls.dt_flags = features.dt_flags

    def set_jesd204_mode(self, mode: int, jesd_class: str) -> None:
        """Apply a JESD mode to both independently configurable sides."""
        self.adc.set_jesd204_mode(mode, jesd_class)
        self.dac.set_jesd204_mode(mode, jesd_class)

    @property
    def jesd204_settings(self) -> dict[str, Any]:
        """Return per-direction JESD settings consumed by :class:`System`."""
        return {"rx": self.adc.jesd204_settings, "tx": self.dac.jesd204_settings}

    def common_extra_dt_lines(self, context: dict | None = None) -> list[str]:
        """Render portable MxFE GPIO, clock, and JESD framework properties."""
        ctx = context or {}
        gpio_label = ctx.get("gpio_label", "gpio")
        lines = [
            f"{name} = <&{gpio_label} {int(value)} 0>;"
            for name, value in self.gpio_values.items()
            if name in self.FEATURES.gpio_properties and value is not None
        ]
        dev_clk_ref = ctx.get("dev_clk_ref")
        if dev_clk_ref:
            lines.extend((f"clocks = <&{dev_clk_ref}>;", 'clock-names = "dev_clk";'))
        rx_link_id = int(self.adc.jesd204_settings.link_id)
        tx_link_id = int(self.dac.jesd204_settings.link_id)
        lines.append(f"jesd204-link-ids = <{rx_link_id} {tx_link_id}>;")
        rx_core, tx_core = ctx.get("rx_core_label"), ctx.get("tx_core_label")
        if rx_core and tx_core:
            lines.append(f"jesd204-inputs = <&{rx_core} 0 {rx_link_id}>, <&{tx_core} 0 {tx_link_id}>;")
        return lines

    def render_dt(self, *, cs: int, context: dict | None = None) -> str:
        """Render the SPI child node using the declared feature set."""
        return render_node(self, label=self.label, node_name=f"{self.part}@{cs}", reg=cs, context=context)

    def to_component_model(self, *, spi_bus: str, spi_cs: int, extra: dict[str, Any] | None = None):
        """Export this MxFE through the common board-model component contract."""
        from adidt.model.board_model import ComponentModel

        return ComponentModel(role=self.role, part=self.part, spi_bus=spi_bus, spi_cs=spi_cs,
                              rendered=self.render_dt(cs=spi_cs, context=extra))


__all__ = ["MxFEAdc", "MxFEDac", "MxFEDevice", "MxFEFeatures"]
