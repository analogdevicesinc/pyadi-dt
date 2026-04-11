"""Clock chip component classes."""

from __future__ import annotations

from typing import Any

from ..board_model import ComponentModel
from ..contexts.clocks import (
    build_ad9545_ctx,
    build_adf4030_ctx,
    build_adf4350_ctx,
    build_adf4371_ctx,
    build_adf4377_ctx,
    build_adf4382_ctx,
    build_ad9523_1_ctx,
    build_ad9528_ctx,
    build_hmc7044_ctx,
    build_ltc6952_ctx,
    build_ltc6953_ctx,
)


class ClockComponent(ComponentModel):
    """Base class for clock distribution / generation components.

    The default *role* is ``"clock"``.
    """

    @classmethod
    def hmc7044(cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any) -> ClockComponent:
        """HMC7044 14-channel clock distributor."""
        config = build_hmc7044_ctx(cs=cs, **kwargs)
        return cls(
            role="clock",
            part="hmc7044",
            template="hmc7044.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def ad9523_1(cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any) -> ClockComponent:
        """AD9523-1 clock generator."""
        config = build_ad9523_1_ctx(cs=cs, **kwargs)
        return cls(
            role="clock",
            part="ad9523_1",
            template="ad9523_1.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def ad9528(cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any) -> ClockComponent:
        """AD9528 clock generator."""
        config = build_ad9528_ctx(cs=cs, **kwargs)
        return cls(
            role="clock",
            part="ad9528",
            template="ad9528.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def adf4382(cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any) -> ClockComponent:
        """ADF4382 microwave wideband synthesizer."""
        config = build_adf4382_ctx(cs=cs, **kwargs)
        return cls(
            role="clock",
            part="adf4382",
            template="adf4382.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def ad9545(cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any) -> ClockComponent:
        """AD9545 network clock generator."""
        config = build_ad9545_ctx(cs=cs, **kwargs)
        return cls(
            role="clock",
            part="ad9545",
            template="ad9545.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def ltc6952(cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any) -> ClockComponent:
        """LTC6952 ultralow jitter clock distributor."""
        config = build_ltc6952_ctx(cs=cs, **kwargs)
        return cls(
            role="clock",
            part="ltc6952",
            template="ltc6952.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def ltc6953(cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any) -> ClockComponent:
        """LTC6953 clock distribution device."""
        config = build_ltc6953_ctx(cs=cs, **kwargs)
        return cls(
            role="clock",
            part="ltc6953",
            template="ltc6953.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def adf4371(cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any) -> ClockComponent:
        """ADF4371 wideband synthesizer."""
        config = build_adf4371_ctx(cs=cs, **kwargs)
        return cls(
            role="clock",
            part="adf4371",
            template="adf4371.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def adf4377(cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any) -> ClockComponent:
        """ADF4377 microwave synthesizer."""
        config = build_adf4377_ctx(cs=cs, **kwargs)
        return cls(
            role="clock",
            part="adf4377",
            template="adf4377.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def adf4350(cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any) -> ClockComponent:
        """ADF4350 wideband synthesizer."""
        config = build_adf4350_ctx(cs=cs, **kwargs)
        return cls(
            role="clock",
            part="adf4350",
            template="adf4350.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def adf4030(cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any) -> ClockComponent:
        """ADF4030 precision synchronizer."""
        config = build_adf4030_ctx(cs=cs, **kwargs)
        return cls(
            role="clock",
            part="adf4030",
            template="adf4030.tmpl",
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
    ) -> ClockComponent:
        """Generic factory for template-only clock devices."""
        return cls(
            role="clock",
            part=part,
            template=template,
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config or {},
        )
