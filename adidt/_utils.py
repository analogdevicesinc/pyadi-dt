"""Small formatting and coercion utilities used across XSA builders and devices."""

from __future__ import annotations

from typing import Any


def fmt_hz(hz: int) -> str:
    """Format *hz* as a human-readable frequency string (e.g. ``"245.76 MHz"``)."""
    if hz >= 1_000_000_000:
        s = f"{hz / 1_000_000_000:.6f}".rstrip("0").rstrip(".")
        return f"{s} GHz"
    if hz >= 1_000_000:
        s = f"{hz / 1_000_000:.6f}".rstrip("0").rstrip(".")
        return f"{s} MHz"
    if hz >= 1_000:
        s = f"{hz / 1_000:.3f}".rstrip("0").rstrip(".")
        return f"{s} kHz"
    return f"{hz} Hz"


def fmt_gpi_gpo(controls: list) -> str:
    """Format a list of int/hex values as a space-separated ``0xNN`` cells string."""
    return " ".join(f"0x{int(v):02x}" for v in controls)


def coerce_board_int(value: Any, key_path: str) -> int:
    """Convert *value* to int; raise ``ValueError`` with *key_path* context on failure."""
    if isinstance(value, bool):
        raise ValueError(f"{key_path} must be an integer, got {value!r}")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key_path} must be an integer, got {value!r}") from exc
