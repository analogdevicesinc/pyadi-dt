"""Transceiver (combined ADC + DAC) component classes."""

from __future__ import annotations

from typing import Any

from ..board_model import ComponentModel
from ..contexts.transceivers import (
    build_ad9081_mxfe_ctx,
    build_ad9082_ctx,
    build_ad9083_ctx,
    build_ad9084_ctx,
    build_adrv9009_device_ctx,
)
from .base import JesdDeviceMixin


class TransceiverComponent(JesdDeviceMixin, ComponentModel):
    """Base class for transceiver components.

    The default *role* is ``"transceiver"``.
    """

    @classmethod
    def ad9081(
        cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any
    ) -> TransceiverComponent:
        """AD9081 MxFE transceiver (combined ADC + DAC)."""
        config = build_ad9081_mxfe_ctx(cs=cs, **kwargs)
        return cls(
            role="transceiver",
            part="ad9081",
            template="ad9081_mxfe.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def ad9084(
        cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any
    ) -> TransceiverComponent:
        """AD9084 RX transceiver."""
        config = build_ad9084_ctx(cs=cs, **kwargs)
        return cls(
            role="transceiver",
            part="ad9084",
            template="ad9084.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def adrv9009(
        cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any
    ) -> TransceiverComponent:
        """ADRV9009 RF transceiver."""
        config = build_adrv9009_device_ctx(**kwargs)
        return cls(
            role="transceiver",
            part="adrv9009",
            template="adrv9009.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def ad9082(
        cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any
    ) -> TransceiverComponent:
        """AD9082 MxFE transceiver (combined ADC + DAC)."""
        config = build_ad9082_ctx(cs=cs, **kwargs)
        return cls(
            role="transceiver",
            part="ad9082",
            template="ad9081_mxfe.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def ad9083(
        cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any
    ) -> TransceiverComponent:
        """AD9083 ADC transceiver."""
        config = build_ad9083_ctx(cs=cs, **kwargs)
        return cls(
            role="transceiver",
            part="ad9083",
            template="ad9083.tmpl",
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
    ) -> TransceiverComponent:
        """Generic factory for template-only transceiver devices."""
        return cls(
            role="transceiver",
            part=part,
            template=template,
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config or {},
        )
