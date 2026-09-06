"""Rebuild the JESD topology around a runtime device-tree change.

The ADI JESD notifier refuses changes while its topology is registered.
All topology clients must be modules, and no capture may remain open.
Never force module removal or bypass the kernel's notifier.
"""

from __future__ import annotations

import re
import os
import shlex

from test.hw.hw_helpers import shell_out

_MODULE_ROOT = "/tmp/adidt-overlay-modules"


def stage_overlay_modules(shell) -> None:
    """Optionally fetch a matching module bundle into the target's /tmp.

    The archive contains lib/modules/<kernel-release>/ including depmod
    indexes. Embedded-rootfs boards can provide those files at boot instead.
    """
    url = os.environ.get("ADIDT_OVERLAY_MODULES_URL")
    digest = os.environ.get("ADIDT_OVERLAY_MODULES_SHA256")
    if not url and not digest:
        return
    assert url and digest and re.fullmatch(r"[a-fA-F0-9]{64}", digest), (
        "Set both ADIDT_OVERLAY_MODULES_URL and ADIDT_OVERLAY_MODULES_SHA256"
    )
    archive = f"{_MODULE_ROOT}/modules.tar.gz"
    result = shell_out(
        shell,
        f"mkdir -p {_MODULE_ROOT} && "
        f"wget -q -O {archive} {shlex.quote(url)} && "
        f"echo '{digest}  {archive}' | sha256sum -c - && "
        f"tar -xzf {archive} -C {_MODULE_ROOT}; echo MODULE_RC=$?",
    )
    assert "MODULE_RC=0" in result, f"Could not stage overlay modules: {result}"


def _check_modules(modules: tuple[str, ...]) -> None:
    assert modules and modules[0] == "jesd204", "JESD core must load first"
    assert len(set(modules)) == len(modules), "Duplicate overlay module"
    assert all(re.fullmatch(r"[a-zA-Z0-9_]+", name) for name in modules)


def _unbind_iio_consumers(shell) -> None:
    """Release runtime SPI module references held by the AXI IIO cores.

    Converter modules depend on symbols exported by cf_axi_adc, while bound
    ADC devices hold references to the converter module. Unbinding the AXI
    devices breaks that dependency cycle before normal module removal.
    """
    result = shell_out(
        shell,
        "if test -x /etc/init.d/S99iiod; then "
        "start-stop-daemon -K -q -o -p /var/run/iiod.pid; "
        "else systemctl stop iiod; fi; echo MODULE_RC=$?",
    )
    assert "MODULE_RC=0" in result, f"Could not stop IIO service: {result}"
    for driver in ("cf_axi_adc", "cf_axi_dds"):
        result = shell_out(
            shell,
            f"module_rc=0; for device in /sys/bus/platform/drivers/{driver}/*; do "
            'test -L "$device/driver" || continue; '
            f'echo "${{device##*/}}" > /sys/bus/platform/drivers/{driver}/unbind '
            '|| { module_rc=$?; break; }; done; echo "MODULE_RC=$module_rc"',
        )
        assert "MODULE_RC=0" in result, f"Could not unbind {driver}: {result}"


def stop_overlay_modules(shell, modules: tuple[str, ...]) -> None:
    """Unload clients in reverse load order, then require the core absent.

    A busy, built-in, or unlisted client is a failure, not a skipped test.
    The caller must not write/remove a configfs overlay after a failure.
    """
    _check_modules(modules)
    _unbind_iio_consumers(shell)
    for name in reversed(modules):
        result = shell_out(
            shell,
            f"if test -d /sys/module/{name}; then rmmod {name}; fi; echo MODULE_RC=$?",
        )
        assert "MODULE_RC=0" in result, (
            f"Cannot quiesce overlay driver {name}: {result}. "
            "Runtime JESD overlays require CONFIG_MODULE_UNLOAD=y and "
            "JESD204 plus every topology client built as modules. "
            "Close captures and stop other users before changing the tree."
        )
    result = shell_out(
        shell,
        "test ! -d /sys/module/jesd204 && test ! -d /sys/bus/jesd204 "
        "&& echo JESD_ABSENT",
    )
    assert "JESD_ABSENT" in result, "JESD topology is still registered"


def start_overlay_modules(shell, modules: tuple[str, ...]) -> None:
    """Register the updated tree before probing its clock and converters."""
    _check_modules(modules)
    for name in modules:
        root = (
            f"-d {_MODULE_ROOT} " if os.environ.get("ADIDT_OVERLAY_MODULES_URL") else ""
        )
        result = shell_out(shell, f"modprobe {root}{name}; echo MODULE_RC=$?")
        assert "MODULE_RC=0" in result, (
            f"Could not load overlay driver {name}: {result}. "
            "Install modules built for the running kernel and run depmod."
        )
    # On a modular boot iiod can exit before the IIO bus exists. Recreate
    # its context only after drivers have registered the overlay devices.
    result = shell_out(
        shell,
        "if test -x /etc/init.d/S99iiod; then /etc/init.d/S99iiod restart; "
        "else systemctl restart iiod; fi; echo MODULE_RC=$?",
    )
    assert "MODULE_RC=0" in result, f"Could not restart IIO service: {result}"
