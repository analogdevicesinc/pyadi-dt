"""Eval-board composites (pre-wired multi-device FMCs).

Each eval-board class composes one or more device models (a clock chip,
a converter, etc.) and pre-populates the schematic-level wiring: which
clock outputs feed which converter inputs, which GPIOs drive resets and
SYSREF requests.  Users customize the remaining degrees of freedom
(sample rates, decimations, JESD modes) on the exposed sub-devices.
"""

from .ad9081_fmc import ad9081_fmc
from .ad9084_fmc import ad9084_fmc
from .adrv937x_fmc import adrv937x_fmc
from .base import EvalBoard

__all__ = ["EvalBoard", "ad9081_fmc", "ad9084_fmc", "adrv937x_fmc"]
