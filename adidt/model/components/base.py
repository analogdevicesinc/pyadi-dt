"""Shared validation for JESD204 devices."""

from __future__ import annotations

JESD_PARAM_NAMES = ("F", "K", "M", "L", "Np", "S")
JESD_SUBCLASS_MAP = {"jesd204a": 0, "jesd204b": 1, "jesd204c": 2}


class JesdDeviceMixin:
    """Mixin providing JESD204 parameter validation."""

    @staticmethod
    def validate_jesd_params(params: dict[str, int], direction: str = "") -> None:
        """Validate JESD204 framing parameters.

        Args:
            params: Dict of JESD parameter names to values.
            direction: Optional direction label (e.g. ``"rx"``, ``"tx"``)
                used in error messages.

        Raises:
            ValueError: If any parameter is not a positive integer.
        """
        prefix = f"{direction} " if direction else ""
        for name in JESD_PARAM_NAMES:
            if name in params:
                val = params[name]
                if not isinstance(val, int) or val < 1:
                    raise ValueError(
                        f"{prefix}JESD parameter {name} must be a positive integer, got {val!r}"
                    )

    @staticmethod
    def map_jesd_subclass(name: str) -> int:
        """Map a JESD subclass name to its numeric value.

        Args:
            name: One of ``"jesd204a"``, ``"jesd204b"``, ``"jesd204c"``.

        Returns:
            Numeric subclass value (0, 1, or 2).

        Raises:
            ValueError: If *name* is not a recognised subclass.
        """
        if name not in JESD_SUBCLASS_MAP:
            raise ValueError(f"Unknown JESD subclass: {name!r}")
        return JESD_SUBCLASS_MAP[name]
