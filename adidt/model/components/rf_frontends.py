"""RF front-end component classes."""

from __future__ import annotations

from typing import Any

from ..board_model import ComponentModel
from ..contexts.rf_frontends import (
    build_adar1000_ctx,
    build_admv1013_ctx,
    build_admv1014_ctx,
    build_adrf6780_ctx,
)


class RfFrontendComponent(ComponentModel):
    """Base class for RF front-end components (LNAs, mixers, etc.).

    The default *role* is ``"rf_frontend"``.
    """

    @classmethod
    def admv1013(
        cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any
    ) -> RfFrontendComponent:
        """ADMV1013 microwave upconverter."""
        config = build_admv1013_ctx(cs=cs, **kwargs)
        return cls(
            role="rf_frontend",
            part="admv1013",
            template="admv1013.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def admv1014(
        cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any
    ) -> RfFrontendComponent:
        """ADMV1014 microwave downconverter."""
        config = build_admv1014_ctx(cs=cs, **kwargs)
        return cls(
            role="rf_frontend",
            part="admv1014",
            template="admv1014.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def adrf6780(
        cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any
    ) -> RfFrontendComponent:
        """ADRF6780 microwave upconverter."""
        config = build_adrf6780_ctx(cs=cs, **kwargs)
        return cls(
            role="rf_frontend",
            part="adrf6780",
            template="adrf6780.tmpl",
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config,
        )

    @classmethod
    def adar1000(
        cls, spi_bus: str = "spi0", cs: int = 0, **kwargs: Any
    ) -> RfFrontendComponent:
        """ADAR1000 X/Ku band beamformer."""
        config = build_adar1000_ctx(cs=cs, **kwargs)
        return cls(
            role="rf_frontend",
            part="adar1000",
            template="adar1000.tmpl",
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
    ) -> RfFrontendComponent:
        """Generic factory for template-only RF front-end devices."""
        return cls(
            role="rf_frontend",
            part=part,
            template=template,
            spi_bus=spi_bus,
            spi_cs=cs,
            config=config or {},
        )
