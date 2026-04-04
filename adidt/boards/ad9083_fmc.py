"""AD9083 FMC board class — ADC-only MxFE variant.

The AD9083 uses a simplified MxFE architecture with ADC channels only
(no DAC). Uses the same clock chip (HMC7044) and JESD204 infrastructure
as AD9081 but with RX-only JESD links.

Inherits from :class:`ad9081_fmc` since the clock and JESD infrastructure
is shared.
"""

from .ad9081_fmc import ad9081_fmc


class ad9083_fmc(ad9081_fmc):
    """AD9083 FMC board — ADC-only MxFE, inherits AD9081 FMC."""

    PLATFORM_CONFIGS = {
        "zcu102": {**ad9081_fmc.PLATFORM_CONFIGS["zcu102"]},
    }
