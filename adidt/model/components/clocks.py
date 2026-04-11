"""Clock chip component classes."""

from __future__ import annotations

from typing import Any

from ..board_model import ComponentModel
from ..contexts.clocks import (
    build_adf4382_ctx,
    build_ad9523_1_ctx,
    build_ad9528_ctx,
    build_hmc7044_ctx,
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
