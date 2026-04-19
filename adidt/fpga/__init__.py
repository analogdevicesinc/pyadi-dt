"""FPGA board models.

An :class:`FpgaBoard` represents the FPGA side of a design: platform
constants (addr cells, PS clock, GPIO controller), a list of SPI masters
that can be wired to peripherals via :meth:`System.connect_spi`, and a
list of GT lanes available for JESD204 links.
"""

from .base import FpgaBoard, SpiMaster
from .vpk180 import vpk180
from .zcu102 import zcu102

__all__ = ["FpgaBoard", "SpiMaster", "vpk180", "zcu102"]
