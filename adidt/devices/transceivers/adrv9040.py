"""ADRV9040 SPI transceiver binding from ADI Linux 22534a028813."""

from __future__ import annotations

from typing import Annotated, Any, ClassVar

from pydantic import Field

from .._dt_render import render_node
from .._fields import DtSkip
from ..converters.base import ConverterDevice


class ADRV9040(ConverterDevice):
    """ADRV9040 device with user-supplied ACE profile and firmware files.

    Sample-clock indices are RX=0, TX=1 and (when enabled) ORX=2.
    JESD framework link IDs are TX=0, RX=2 and ORX=3.
    """

    part: ClassVar[str] = "adrv9040"
    compatible: ClassVar[str] = "adi,adrv9040"
    template: ClassVar[str] = ""
    dt_header: ClassVar[dict[str, Any]] = {
        "#address-cells": 1,
        "#size-cells": 0,
        "#clock-cells": 1,
        "#jesd204-cells": 2,
        "jesd204-top-device": 0,
    }
    dt_flags: ClassVar[tuple[str, ...]] = ("jesd204-device",)

    label: str = "trx0_adrv904x"
    spi_max_hz: int = Field(25_000_000, gt=0, alias="spi-max-frequency")
    device_config_name: str = Field(
        "DeviceProfileTest.bin", min_length=1, alias="adi,device-config-name"
    )
    arm_firmware_name: str = Field(
        "ADRV9040_FW.bin", min_length=1, alias="adi,arm-firmware-name"
    )
    arm_dfe_firmware_name: str = Field(
        "ADRV9040_DFE_CALS_FW.bin", min_length=1, alias="adi,arm-dfe-firmware-name"
    )
    stream_firmware_name: str = Field(
        "stream_image.bin", min_length=1, alias="adi,stream-firmware-name"
    )
    rx_gaintable_names: list[str] = Field(
        default_factory=lambda: ["ADRV9040_RxGainTable.csv"],
        alias="adi,rx-gaintable-names",
    )
    rx_gaintable_channel_masks: list[int] = Field(
        default_factory=lambda: [255], alias="adi,rx-gaintable-channel-masks"
    )
    tx_attntable_names: list[str] | None = Field(None, alias="adi,tx-attntable-names")
    tx_attntable_channel_masks: list[int] | None = Field(
        None, alias="adi,tx-attntable-channel-masks"
    )
    observation: Annotated[bool, DtSkip()] = False
    reset_gpio: Annotated[int | None, DtSkip()] = 134
    interrupt_gpio: Annotated[int | None, DtSkip()] = 134
    sysref_req_gpio: Annotated[int | None, DtSkip()] = None
    ignore_jesd_errors: bool = Field(False, alias="jesd204-ignore-errors")

    def extra_dt_lines(self, context: dict | None = None) -> list[str]:
        """Render GPIO, clock and JESD phandles supplied by the board."""
        ctx = context or {}
        gpio = ctx.get("gpio_label", "gpio")
        lines = [
            'clock-output-names = "rx_sampl_clk", "tx_sampl_clk"'
            + (', "obs_sampl_clk";' if self.observation else ";"),
            "jesd204-link-ids = <0 2" + (" 3>;" if self.observation else ">;"),
        ]
        for prop, value in (
            ("reset-gpios", self.reset_gpio),
            ("sysref-req-gpios", self.sysref_req_gpio),
        ):
            if value is not None:
                lines.append(f"{prop} = <&{gpio} {value} 0>;")
        if self.interrupt_gpio is not None:
            lines += [
                f"interrupt-parent = <&{gpio}>;",
                f"interrupts = <{self.interrupt_gpio} 1>;",
            ]
        if ctx.get("dev_clk_ref"):
            lines += [f"clocks = <&{ctx['dev_clk_ref']}>;", 'clock-names = "dev_clk";']
        if ctx.get("jesd204_inputs"):
            lines.append(f"jesd204-inputs = {ctx['jesd204_inputs']};")
        return lines

    def render_dt(self, *, cs: int, context: dict | None = None) -> str:
        """Render the Linux PHY node at the given SPI chip-select."""
        return render_node(
            self,
            label=self.label,
            node_name=f"adrv904x-phy@{cs}",
            reg=cs,
            context=context,
        )

    def to_component_model(
        self, *, spi_bus: str, spi_cs: int, extra: dict[str, Any] | None = None
    ):
        """Adapt this device for the board composition renderer."""
        from adidt.model.board_model import ComponentModel

        return ComponentModel(
            role=self.role,
            part=self.part,
            spi_bus=spi_bus,
            spi_cs=spi_cs,
            rendered=self.render_dt(cs=spi_cs, context=extra),
        )
