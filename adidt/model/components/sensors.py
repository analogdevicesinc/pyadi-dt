"""Sensor component classes (IMU, accelerometer, precision ADC)."""

from __future__ import annotations

from typing import Any

from ..board_model import ComponentModel
from ..contexts.sensors import (
    build_ad7124_ctx,
    build_adis16495_ctx,
    build_adxl345_ctx,
)


class SensorComponent(ComponentModel):
    """Base class for simple SPI sensor components."""

    @classmethod
    def adis16495(cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any) -> SensorComponent:
        """ADIS16495 6-DOF IMU."""
        config = build_adis16495_ctx(cs=cs, **kwargs)
        return cls(
            role="imu",
            part="adis16495",
            template="adis16495.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def adxl345(cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any) -> SensorComponent:
        """ADXL345 3-axis accelerometer."""
        config = build_adxl345_ctx(cs=cs, **kwargs)
        return cls(
            role="accelerometer",
            part="adxl345",
            template="adxl345.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def ad7124(cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any) -> SensorComponent:
        """AD7124 24-bit precision ADC."""
        config = build_ad7124_ctx(cs=cs, **kwargs)
        return cls(
            role="adc",
            part="ad7124",
            template="ad7124.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def from_config(
        cls,
        part: str,
        template: str,
        role: str,
        spi_bus: str = "spi0",
        cs: int = 0,
        *,
        config: dict[str, Any] | None = None,
    ) -> SensorComponent:
        """Generic factory for template-only sensor devices."""
        return cls(
            role=role,
            part=part,
            template=template,
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config or {},
        )
