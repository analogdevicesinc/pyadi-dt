"""Typed hardware device models.

This package is the greenfield home of the device-centric modeling layer
that maps 1:1 to device-tree nodes.  Each ``Device`` subclass is a pydantic
model whose fields mirror the DT properties the device renders.  Devices
compose via :class:`Port` objects (SPI, clock outputs, GT lanes) that the
:class:`adidt.system.System` wires together.

The legacy ``adidt.model.components`` / ``adidt.boards`` layers remain
functional; this package feeds the same
:class:`adidt.model.renderer.BoardModelRenderer` by producing
:class:`adidt.model.board_model.ComponentModel` instances.
"""

from .base import ClockOutput, Device, GtLane, Pin, Port, SpiPort

__all__ = ["ClockOutput", "Device", "GtLane", "Pin", "Port", "SpiPort"]
