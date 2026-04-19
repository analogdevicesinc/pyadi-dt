"""Shared pytest fixtures for hardware integration tests.

Supports two connection modes:

1. **Coordinator mode** — ``LG_COORDINATOR`` is set.  The labgrid pytest
   plugin connects to the coordinator; an env YAML (``LG_ENV`` /
   ``--lg-env``) with ``RemotePlace`` resources defines which place to
   acquire.  Three exporter sub-modes are determined by additional env
   vars (see ``.env.example``).

2. **Direct mode** — only ``LG_ENV`` is set.  The labgrid pytest plugin
   loads the environment YAML directly (serial / USB / network
   resources).  This is the legacy path used by Jenkins.

The ``board`` fixture abstracts the difference — downstream test code
(``deploy_and_boot``, ``collect_dmesg``, etc.) is identical in both modes.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from test.hw.hw_helpers import build_kernel_image, require_hw_prereqs


def _hw_mode() -> str | None:
    """Return the active hardware connection mode, or ``None`` if disabled."""
    if os.environ.get("LG_COORDINATOR"):
        return "coordinator"
    if os.environ.get("LG_ENV"):
        return "direct"
    return None


@pytest.fixture(scope="module")
def board(strategy):
    """Verify tool prerequisites then transition the board to *powered_off*.

    Works identically in coordinator and direct modes — the ``strategy``
    fixture is provided by the labgrid pytest plugin in both cases (the
    plugin reads ``LG_COORDINATOR`` and ``LG_ENV`` from the environment,
    which ``pytest-dotenv`` loads from ``.env``).

    Args:
        strategy: Labgrid strategy fixture injected by the labgrid
            pytest plugin.

    Yields:
        The labgrid *strategy* object after the board has been
        transitioned to the ``powered_off`` state.
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
