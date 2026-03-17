"""Shared pytest fixtures for XSA hardware integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from test.hw.hw_helpers import build_kernel_image, require_hw_prereqs


@pytest.fixture(scope="module")
def board(strategy):
    """Verify tool prerequisites then transition the board to *powered_off*.

    Args:
        strategy: Labgrid strategy fixture injected by the test framework.

    Yields:
        The labgrid *strategy* object after the board has been transitioned to
        the ``powered_off`` state.
    """
    require_hw_prereqs()
    strategy.transition("powered_off")
    yield strategy


@pytest.fixture(scope="module")
def built_kernel_image_zynqmp() -> Path | None:
    """Build a Linux kernel image for ZynqMP platforms (e.g. ZCU102).

    Returns:
        Path to the built kernel image, or ``None`` when
        :data:`~test.hw.hw_helpers.DEFAULT_BUILD_KERNEL` is ``False``.
    """
    return build_kernel_image("zynqmp")


@pytest.fixture(scope="module")
def built_kernel_image_zynq() -> Path | None:
    """Build a Linux kernel image for Zynq-7000 platforms (e.g. ZC706).

    Returns:
        Path to the built kernel image, or ``None`` when
        :data:`~test.hw.hw_helpers.DEFAULT_BUILD_KERNEL` is ``False``.
    """
    return build_kernel_image("zynq")
