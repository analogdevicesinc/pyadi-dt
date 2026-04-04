"""ADRV9008 FMC board class — receiver-only variant of ADRV9009.

The ADRV9008 uses the same transceiver architecture as ADRV9009 but
is RX-only (no TX path). Inherits all methods from :class:`adrv9009_fmc`.
"""

from .adrv9009_fmc import adrv9009_fmc


class adrv9008_fmc(adrv9009_fmc):
    """ADRV9008 FMC board — inherits ADRV9009 FMC (RX-only variant)."""

    PLATFORM_CONFIGS = {
        "zcu102": {**adrv9009_fmc.PLATFORM_CONFIGS["zcu102"]},
        "zc706": {**adrv9009_fmc.PLATFORM_CONFIGS["zc706"]},
    }
