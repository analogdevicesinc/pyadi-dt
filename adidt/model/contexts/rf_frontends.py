"""RF front-end context builders.

Provides context builders for ADMV1013, ADMV1014, ADRF6780, and ADAR1000
RF front-end devices.
"""

from __future__ import annotations


def build_admv1013_ctx(
    *,
    label: str = "admv1013_0",
    cs: int = 0,
    spi_max_hz: int = 1_000_000,
    clks_str: str | None = None,
    input_mode: str | None = None,
    quad_se_mode: str | None = None,
    detector_enable: bool = False,
) -> dict:
    """Build context dict for ``admv1013.tmpl``."""
    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "clks_str": clks_str,
        "input_mode": input_mode,
        "quad_se_mode": quad_se_mode,
        "detector_enable": detector_enable,
    }


def build_admv1014_ctx(
    *,
    label: str = "admv1014_0",
    cs: int = 0,
    spi_max_hz: int = 1_000_000,
    clks_str: str | None = None,
) -> dict:
    """Build context dict for ``admv1014.tmpl``."""
    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "clks_str": clks_str,
    }


def build_adrf6780_ctx(
    *,
    label: str = "adrf6780_0",
    cs: int = 0,
    spi_max_hz: int = 1_000_000,
    clks_str: str | None = None,
) -> dict:
    """Build context dict for ``adrf6780.tmpl``."""
    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "clks_str": clks_str,
    }


def build_adar1000_ctx(
    *,
    label: str = "adar1000_0",
    cs: int = 0,
    spi_max_hz: int = 10_000_000,
    clks_str: str | None = None,
) -> dict:
    """Build context dict for ``adar1000.tmpl``."""
    return {
        "label": label,
        "cs": cs,
        "spi_max_hz": spi_max_hz,
        "clks_str": clks_str,
    }
