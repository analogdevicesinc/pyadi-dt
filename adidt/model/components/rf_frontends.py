"""RF front-end component classes."""

from __future__ import annotations

from typing import Any

from ..board_model import ComponentModel


class RfFrontendComponent(ComponentModel):
    """Base class for RF front-end components (LNAs, mixers, etc.).

    The default *role* is ``"rf_frontend"``.  No device-specific factories
    are defined yet; use :meth:`from_config` for template-only creation.
    """

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
