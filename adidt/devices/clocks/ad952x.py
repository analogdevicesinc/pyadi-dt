"""AD9523-1 / AD9528 clock generator device models (declarative)."""

from __future__ import annotations

from typing import Annotated, Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from .._dt_render import render_node
from .._fields import DtSkip, DtSubnodes
from ..base import ClockOutput
from .base import ClockDevice


_AD9523_OUTPUT_NAMES = [f"ad9523-1_out{i}" for i in range(14)]
_AD9528_OUTPUT_NAMES = [f"ad9528_out{i}" for i in range(14)]
_AD9528_1_OUTPUT_NAMES = [f"ad9528-1_out{i}" for i in range(14)]


class _GpioLine(BaseModel):
    """One GPIO phandle line used by AD952x clock chips."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    prop: str
    controller: str
    index: int


class AD9523Channel(BaseModel):
    """One output channel on an AD9523-1."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    dt_header: ClassVar[dict[str, Any]] = {
        "adi,driver-mode": 3,
        "adi,divider-phase": 1,
    }

    id: Annotated[int, DtSkip()]
    name: str | None = Field(None, alias="adi,extended-name")
    divider: int = Field(1, alias="adi,channel-divider")
    freq_str: Annotated[str | None, DtSkip()] = None
    # Parity fields that some downstream consumers read; not in DT.
    driver_mode: Annotated[int, DtSkip()] = 3
    is_sysref: Annotated[bool, DtSkip()] = False


class AD9528Channel(BaseModel):
    """One output channel on an AD9528 / AD9528-1."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    dt_header: ClassVar[dict[str, Any]] = {
        "adi,driver-mode": 3,
        "adi,divider-phase": 0,
    }

    id: Annotated[int, DtSkip()]
    name: str | None = Field(None, alias="adi,extended-name")
    divider: int = Field(1, alias="adi,channel-divider")
    signal_source: int | None = Field(None, alias="adi,signal-source")
    is_sysref: bool = Field(False, alias="adi,jesd204-sysref-chan")
    freq_str: Annotated[str | None, DtSkip()] = None
    driver_mode: Annotated[int, DtSkip()] = 3


class AD9528_1Channel(AD9528Channel):
    """AD9528-1 variant: ``adi,driver-mode = <0>``."""

    dt_header: ClassVar[dict[str, Any]] = {
        "adi,driver-mode": 0,
        "adi,divider-phase": 0,
    }


class _AD952xBase(ClockDevice):
    """Common machinery for AD9523/AD9528 style clock chips."""

    # Subclasses override:
    node_kind: ClassVar[str] = ""  # "ad9523-1" / "ad9528" / "ad9528-1"
    channel_label_fmt: ClassVar[str] = "{parent}_{cs}_c{key}"

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

    def _build_clock_outputs(self) -> list[ClockOutput]:
        """One handle per populated channel, ordered by id."""
        return [
            ClockOutput(
                self,
                index=ch.id,
                name=ch.name,
                divider=ch.divider,
                driver_mode=int(getattr(ch, "driver_mode", 3)),
                is_sysref=bool(getattr(ch, "is_sysref", False)),
            )
            for ch in sorted(self.channels.values(), key=lambda c: c.id)
        ]

    def extra_dt_lines(self, context: dict | None = None) -> list[str]:
        lines: list[str] = []
        for gl in self.gpio_lines:
            lines.append(f"{gl.prop} = <&{gl.controller} {int(gl.index)} 0>;")
        return lines

    # Both device families share these fields:
    gpio_lines: Annotated[list[_GpioLine], DtSkip()] = Field(default_factory=list)


class AD9523_1(_AD952xBase):
    """AD9523-1 clock distributor."""

    part: ClassVar[str] = "ad9523_1"
    template: ClassVar[str] = ""
    node_kind: ClassVar[str] = "ad9523-1"

    compatible: ClassVar[str] = "adi,ad9523-1"
    dt_header: ClassVar[dict[str, Any]] = {
        "#address-cells": 1,
        "#size-cells": 0,
        "#clock-cells": 1,
        "adi,pll2-charge-pump-current-nA": 413000,
        "adi,pll2-m1-freq": 1_000_000_000,
        "adi,rpole2": 0,
        "adi,rzero": 7,
        "adi,cpole1": 2,
    }
    dt_flags: ClassVar[tuple[str, ...]] = (
        "adi,spi-3wire-enable",
        "adi,pll1-bypass-enable",
        "adi,osc-in-diff-enable",
    )

    label: str = "ad9523"
    spi_max_hz: int = Field(10_000_000, alias="spi-max-frequency")
    vcxo_hz: int = Field(125_000_000, alias="adi,vcxo-freq")
    clock_output_names: list[str] = Field(
        default_factory=lambda: list(_AD9523_OUTPUT_NAMES),
        alias="clock-output-names",
    )
    channels: Annotated[
        dict[int, AD9523Channel],
        DtSubnodes(node_name="channel", label_template="ad9523_{cs}_c{key}"),
    ] = Field(default_factory=dict)


class AD9528(_AD952xBase):
    """AD9528 clock distributor / JESD204 SYSREF source."""

    part: ClassVar[str] = "ad9528"
    template: ClassVar[str] = ""
    node_kind: ClassVar[str] = "ad9528"

    compatible: ClassVar[str] = "adi,ad9528"
    dt_header: ClassVar[dict[str, Any]] = {
        "#address-cells": 1,
        "#size-cells": 0,
        "#clock-cells": 1,
        "#jesd204-cells": 2,
        "adi,pll2-m1-frequency": 1_233_333_333,
        "adi,pll2-charge-pump-current-nA": 35000,
    }
    dt_flags: ClassVar[tuple[str, ...]] = (
        "adi,spi-3wire-enable",
        "adi,pll1-bypass-enable",
        "adi,osc-in-diff-enable",
        "jesd204-device",
        "jesd204-sysref-provider",
    )

    label: str = "ad9528"
    spi_max_hz: int = Field(10_000_000, alias="spi-max-frequency")
    vcxo_hz: int = Field(122_880_000, alias="adi,vcxo-freq")
    clock_output_names: list[str] = Field(
        default_factory=lambda: list(_AD9528_OUTPUT_NAMES),
        alias="clock-output-names",
    )
    channels: Annotated[
        dict[int, AD9528Channel],
        DtSubnodes(node_name="channel", label_template="ad9528_{cs}_c{key}"),
    ] = Field(default_factory=dict)


class AD9528_1(_AD952xBase):
    """AD9528-1 clock distributor (ADRV9009 variant)."""

    part: ClassVar[str] = "ad9528_1"
    template: ClassVar[str] = ""
    node_kind: ClassVar[str] = "ad9528-1"

    compatible: ClassVar[str] = "adi,ad9528"
    dt_header: ClassVar[dict[str, Any]] = {
        "#address-cells": 1,
        "#size-cells": 0,
        "#clock-cells": 1,
        "adi,pll1-feedback-div": 4,
        "adi,pll1-charge-pump-current-nA": 5000,
        "adi,pll2-vco-div-m1": 3,
        "adi,pll2-n2-div": 10,
        "adi,pll2-r1-div": 1,
        "adi,pll2-charge-pump-current-nA": 805000,
        "adi,refa-r-div": 1,
        "adi,sysref-src": 2,
        "adi,sysref-pattern-mode": 1,
        "adi,sysref-k-div": 512,
        "adi,sysref-nshot-mode": 3,
        "adi,sysref-request-trigger-mode": 0,
        "adi,status-mon-pin0-function-select": 1,
        "adi,status-mon-pin1-function-select": 7,
    }
    dt_flags: ClassVar[tuple[str, ...]] = (
        "adi,refa-enable",
        "adi,refa-diff-rcv-enable",
        "adi,osc-in-cmos-neg-inp-enable",
        "adi,sysref-request-enable",
    )

    label: str = "ad9528"
    spi_max_hz: int = Field(10_000_000, alias="spi-max-frequency")
    vcxo_hz: int = Field(122_880_000, alias="adi,vcxo-freq")
    clock_output_names: list[str] = Field(
        default_factory=lambda: list(_AD9528_1_OUTPUT_NAMES),
        alias="clock-output-names",
    )
    channels: Annotated[
        dict[int, AD9528_1Channel],
        DtSubnodes(node_name="channel", label_template="ad9528_0_c{key}"),
    ] = Field(default_factory=dict)


__all__ = [
    "AD9523_1",
    "AD9523Channel",
    "AD9528",
    "AD9528_1",
    "AD9528Channel",
    "AD9528_1Channel",
]
