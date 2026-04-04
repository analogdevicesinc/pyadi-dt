"""ADRV937x FMC board class — wideband transceiver variant.

The ADRV937x family uses the same XSA builder infrastructure as ADRV9009.
Inherits all methods from :class:`adrv9009_fmc`.
"""

from .adrv9009_fmc import adrv9009_fmc


class adrv937x_fmc(adrv9009_fmc):
    """ADRV937x FMC board — inherits ADRV9009 FMC."""

    PLATFORM_CONFIGS = {
        "zcu102": {**adrv9009_fmc.PLATFORM_CONFIGS["zcu102"]},
        "zc706": {**adrv9009_fmc.PLATFORM_CONFIGS["zc706"]},
    }
