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
def board(strategy, request):
    """Verify tool prerequisites then transition the board to *powered_off*.

    Works identically in coordinator and direct modes — the ``strategy``
    fixture is provided by the labgrid pytest plugin in both cases (the
    plugin reads ``LG_COORDINATOR`` and ``LG_ENV`` from the environment,
    which ``pytest-dotenv`` loads from ``.env``).

    On teardown the board is returned to the ``powered_off`` state so
    lab hardware is never left running between test modules or CI
    runs.  Even if a test fails mid-transition and the strategy is in
    a broken state, we fall back to calling ``power.off()`` directly
    on the bound ``PowerProtocol`` driver.

    Args:
        strategy: Labgrid strategy fixture injected by the labgrid
            pytest plugin.

    Yields:
        The labgrid *strategy* object after the board has been
        transitioned to the ``powered_off`` state.
    """
    require_hw_prereqs()
    strategy.transition("powered_off")
    kernel_resource = None
    original_kernel = None
    kernel_overridden = False
    jtag_hosts = []
    try:
        host = os.environ.get("ADIDT_JTAG_HOST")
        if host:
            jtag = getattr(strategy, "jtag", None)
            if jtag is None:
                pytest.fail("ADIDT_JTAG_HOST requires a JTAG strategy")
            strategy.target.activate(jtag)
            for name in ("xilinxdevicejtag", "xilinxvivado"):
                resource = getattr(jtag, name)
                jtag_hosts.append((resource, resource.host))
                resource.host = host
        kernel_variable = "ADIDT_FABRIC_KERNEL_IMAGE"
        if request.node.path.name.endswith("_overlay.py") and os.environ.get(
            "ADIDT_OVERLAY_FABRIC_KERNEL_IMAGE"
        ):
            kernel_variable = "ADIDT_OVERLAY_FABRIC_KERNEL_IMAGE"
        kernel = os.environ.get(kernel_variable)
        if kernel:
            jtag = getattr(strategy, "jtag", None)
            if jtag is not None:
                # Populate remote resource parameters before overriding them.
                strategy.target.activate(jtag)
            kernel_resource = getattr(jtag, "xilinxdevicejtag", None)
            if kernel_resource is None or not hasattr(kernel_resource, "kernel_path"):
                pytest.fail(f"{kernel_variable} requires a fabric JTAG resource")
            if not Path(kernel).is_absolute():
                pytest.fail(f"{kernel_variable} must be an absolute exporter path")
            original_kernel = kernel_resource.kernel_path
            kernel_resource.kernel_path = kernel
            kernel_overridden = True
        yield strategy
    finally:
        _teardown_power_off(strategy)
        if kernel_overridden:
            kernel_resource.kernel_path = original_kernel
        for resource, host in jtag_hosts:
            resource.host = host


def _teardown_power_off(strategy) -> None:
    """Best-effort power-down of *strategy*'s board at test-module exit.

    Tries the strategy's ``powered_off`` transition first (which runs
    strategy-specific cleanup — sdmux back to host, serial detach,
    etc.); if the state machine is broken from a prior failure, falls
    back to driving the ``PowerProtocol`` binding directly.  Leaving
    lab hardware energised between runs is worse than a noisy
    teardown, so we swallow any exceptions from the fallback path
    after logging.
    """
    import logging

    logger = logging.getLogger(__name__)
    try:
        strategy.transition("powered_off")
        logger.info("Board transitioned to powered_off at test teardown.")
        return
    except Exception as exc:
        logger.warning("Strategy transition to powered_off failed at teardown: %s", exc)
    try:
        power = getattr(strategy, "power", None)
        if power is None:
            return
        strategy.target.activate(power)
        power.off()
        logger.info("Board powered off directly via PowerProtocol at teardown.")
    except Exception as exc:
        logger.error("Fallback power.off() also failed at teardown: %s", exc)


@pytest.fixture(scope="session")
def built_kernel_image_zynqmp() -> Path | None:
    """Build (or fetch from cache) a Linux kernel image for ZynqMP platforms.

    Session-scoped so the image is shared across all ZCU102 hw tests in
    a single pytest run; results are also cached across runs by
    :func:`~test.hw.hw_helpers.build_kernel_image`.

    Returns:
        Path to the built kernel image, or ``None`` when
        :data:`~test.hw.hw_helpers.DEFAULT_BUILD_KERNEL` is ``False``.
    """
    return build_kernel_image("zynqmp")


@pytest.fixture(scope="session")
def built_kernel_image_zynq() -> Path | None:
    """Build (or fetch from cache) a Linux kernel image for Zynq-7000 platforms.

    Session-scoped so the image is shared across all ZC706 hw tests in
    a single pytest run; results are also cached across runs by
    :func:`~test.hw.hw_helpers.build_kernel_image`.

    Returns:
        Path to the built kernel image, or ``None`` when
        :data:`~test.hw.hw_helpers.DEFAULT_BUILD_KERNEL` is ``False``.
    """
    return build_kernel_image("zynq")
