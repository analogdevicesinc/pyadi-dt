"""Shared pytest fixtures for XSA hardware integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from test.hw.hw_helpers import build_kernel_image, require_hw_prereqs


@pytest.fixture(scope="module")
def board(strategy):
    """Verify tool prerequisites then transition the board to *powered_off*."""
    require_hw_prereqs()
    strategy.transition("powered_off")
    yield strategy


@pytest.fixture(scope="module")
def built_kernel_image_zynqmp() -> Path | None:
    """Build a Linux kernel image for ZynqMP platforms (e.g. ZCU102)."""
    return build_kernel_image("zynqmp")


@pytest.fixture(scope="module")
def built_kernel_image_zynq() -> Path | None:
    """Build a Linux kernel image for Zynq-7000 platforms (e.g. ZC706)."""
    return build_kernel_image("zynq")
