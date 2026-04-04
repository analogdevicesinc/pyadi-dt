"""AD9082 FMC board class — variant of AD9081 with different JESD modes.

The AD9082 uses the same MxFE architecture as AD9081 but with different
default JESD204 configurations (typically M4/L8 instead of M8/L4).
Inherits all methods from :class:`ad9081_fmc`.
"""

from .ad9081_fmc import ad9081_fmc


class ad9082_fmc(ad9081_fmc):
    """AD9082 FMC board — inherits AD9081 FMC with M4/L8 defaults."""

    PLATFORM_CONFIGS = {
        "zcu102": {
            **ad9081_fmc.PLATFORM_CONFIGS["zcu102"],
        },
    }
