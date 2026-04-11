"""ADC and DAC component classes."""

from __future__ import annotations

from typing import Any

from ..board_model import ComponentModel
from ..contexts.converters import (
    build_ad9144_ctx,
    build_ad9152_ctx,
    build_ad9172_device_ctx,
    build_ad9680_ctx,
)
from .base import JesdDeviceMixin


class AdcComponent(JesdDeviceMixin, ComponentModel):
    """Base class for ADC components.

    The default *role* is ``"adc"``.
    """

    @classmethod
    def ad9680(cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any) -> AdcComponent:
        """AD9680 dual-channel ADC."""
        config = build_ad9680_ctx(cs=cs, **kwargs)
        return cls(
            role="adc",
            part="ad9680",
            template="ad9680.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def from_config(
        cls,
        part: str,
        template: str,
        spi_bus: str = "spi0",
        cs: int = 0,
        *,
        config: dict[str, Any] | None = None,
    ) -> AdcComponent:
        """Generic factory for template-only ADC devices."""
        return cls(
            role="adc",
            part=part,
            template=template,
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config or {},
        )


class DacComponent(JesdDeviceMixin, ComponentModel):
    """Base class for DAC components.

    The default *role* is ``"dac"``.
    """

    @classmethod
    def ad9144(cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any) -> DacComponent:
        """AD9144 quad-channel DAC."""
        config = build_ad9144_ctx(cs=cs, **kwargs)
        return cls(
            role="dac",
            part="ad9144",
            template="ad9144.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def ad9152(cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any) -> DacComponent:
        """AD9152 dual-channel DAC."""
        config = build_ad9152_ctx(cs=cs, **kwargs)
        return cls(
            role="dac",
            part="ad9152",
            template="ad9152.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def ad9172(cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any) -> DacComponent:
        """AD9172 RF DAC."""
        config = build_ad9172_device_ctx(cs=cs, **kwargs)
        return cls(
            role="dac",
            part="ad9172",
            template="ad9172.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def from_config(
        cls,
        part: str,
        template: str,
        spi_bus: str = "spi0",
        cs: int = 0,
        *,
        config: dict[str, Any] | None = None,
    ) -> DacComponent:
        """Generic factory for template-only DAC devices."""
        return cls(
            role="dac",
            part=part,
            template=template,
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config or {},
        )
