"""Base class for eval-board (FMC) composites."""

from __future__ import annotations

from typing import Iterable

from ..devices.base import Device


class EvalBoard:
    """Base class for eval-board composites.

    Subclasses set ``clock``, ``converter`` (or similar) attributes to
    pre-configured :class:`Device` instances and assign named-alias
    properties to selected :class:`ClockOutput` handles.

    Attributes:
        reference_frequency: Input reference frequency (Hz) provided by
            the host system to the eval board's primary clock.  Setters
            may propagate this to the clock device.
    """

    reference_frequency: int = 0

    def devices(self) -> Iterable[Device]:
        """Yield every :class:`Device` that belongs to this eval board.

        Default implementation returns any attribute whose value is a
        :class:`Device`.  Subclasses may override to enforce an order.
        """
        seen: set[int] = set()
        for name in dir(self):
            if name.startswith("_"):
                continue
            try:
                value = getattr(self, name)
            except AttributeError:
                continue
            if isinstance(value, Device) and id(value) not in seen:
                seen.add(id(value))
                yield value
