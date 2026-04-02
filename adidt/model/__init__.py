"""Unified board model for DTS generation.

Both the manual board-class workflow and the XSA pipeline produce a
:class:`BoardModel`, which a :class:`BoardModelRenderer` renders to DTS
using the shared per-component Jinja2 templates.
"""

from .board_model import BoardModel, ComponentModel, FpgaConfig, JesdLinkModel

__all__ = [
    "BoardModel",
    "ComponentModel",
    "FpgaConfig",
    "JesdLinkModel",
]
