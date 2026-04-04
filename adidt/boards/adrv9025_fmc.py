"""ADRV9025 FMC board class — variant of ADRV9009 with wider bandwidth.

The ADRV9025 uses the same transceiver architecture as ADRV9009 but
supports wider bandwidth and more channels. Inherits all methods from
:class:`adrv9009_fmc`.
"""

from .adrv9009_fmc import adrv9009_fmc


class adrv9025_fmc(adrv9009_fmc):
    """ADRV9025 FMC board — inherits ADRV9009 FMC."""

    PLATFORM_CONFIGS = {
        "zcu102": {
            **adrv9009_fmc.PLATFORM_CONFIGS["zcu102"],
        },
    }
