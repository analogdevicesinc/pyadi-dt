"""Unified board model shared by the XSA pipeline and the declarative device API.

Both paths produce a :class:`BoardModel`; a :class:`BoardModelRenderer`
assembles it to DTS by concatenating pre-rendered component and JESD
link strings.
"""

from .board_model import BoardModel, ComponentModel, FpgaConfig, JesdLinkModel

__all__ = [
    "BoardModel",
    "ComponentModel",
    "FpgaConfig",
    "JesdLinkModel",
]
