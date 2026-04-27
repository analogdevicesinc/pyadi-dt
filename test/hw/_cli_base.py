"""Shared helpers for ``adidtc`` CLI hardware tests.

The CLI hw tests under ``test/hw/test_cli_*_hw.py`` exercise the same
``adidtc`` entry points a user would run.  They reuse the standard
labgrid+:class:`BoardSystemProfile` boot path from
:mod:`test.hw._system_base`, then drive the CLI in-process with
:class:`click.testing.CliRunner` so exit codes and ``click.echo``
output are easy to assert against.

Two pieces of glue are provided here:

* :func:`run_adidtc` / :func:`run_adidtc_jif` — invoke the top-level
  ``adidtc`` group (or the ``jif`` subgroup registered out-of-band at
  :func:`adidt.cli.jif.register`) and assert the exit code.
* :func:`discover_board_ipv4` / :func:`wait_for_ssh` /
  :func:`sd_marker_cleanup` — utilities for exercising commands that
  talk to the booted board over SSH.  ``discover_board_ipv4`` mirrors
  the ``ip = str(ip_addresses[0].ip).split('/')[0]`` pattern from
  :func:`test.hw.hw_helpers.open_iio_context` so the CLI sees the same
  reachable IP as the IIO probe path.
"""

from __future__ import annotations

import contextlib
import time
from pathlib import Path
from typing import Iterator

from click.testing import CliRunner, Result

from adidt.cli.main import cli as adidtc_cli


# Default Kuiper rootfs credentials.  Mirror :class:`adidt.dt.dt`'s
# hardcoded defaults at adidt/dt.py:33-35 so the CLI's own --username /
# --password defaults do not need to be overridden in tests.
KUIPER_USER = "root"
KUIPER_PASSWORD = "analog"


def run_adidtc(
    args: list[str],
    *,
    expect_exit: int = 0,
    catch_exceptions: bool = False,
) -> Result:
    """Invoke ``adidtc`` with *args* via :class:`CliRunner`; assert exit code.

    Args:
        args: Argument vector passed to the top-level ``adidtc`` group
            (without the leading ``adidtc``).
        expect_exit: Expected ``result.exit_code``.  Mismatches raise
            ``AssertionError`` with the captured output for triage.
        catch_exceptions: Forwarded to :meth:`CliRunner.invoke`.  Off by
            default so tracebacks surface during test development; set
            ``True`` when verifying CLI-level error handling.

    Returns:
        The :class:`click.testing.Result` for further assertions on
        ``result.output``.
    """
    runner = CliRunner()
    result = runner.invoke(adidtc_cli, args, catch_exceptions=catch_exceptions)
    if result.exit_code != expect_exit:
        raise AssertionError(
            f"adidtc {' '.join(args)!s} exited {result.exit_code}, "
            f"expected {expect_exit}.\n--- output ---\n{result.output}"
        )
    return result


def run_adidtc_jif(
    args: list[str],
    *,
    expect_exit: int = 0,
    catch_exceptions: bool = False,
) -> Result:
    """Invoke the ``adidtc jif`` subgroup; thin wrapper around :func:`run_adidtc`.

    The ``jif`` group is registered on the top-level ``cli`` at module
    import time via ``_jif.register(cli)`` (see ``adidt/cli/main.py``),
    so a single :class:`CliRunner` against ``cli`` reaches it — but this
    wrapper makes the call site read like ``adidtc jif clock ...``.
    """
    return run_adidtc(
        ["jif", *args], expect_exit=expect_exit, catch_exceptions=catch_exceptions
    )


def discover_board_ipv4(shell) -> str:
    """Return the first usable IPv4 reported by *shell*.

    Wraps :meth:`ADIShellDriver.get_ip_addresses` (already used by
    :func:`test.hw.hw_helpers.open_iio_context`).  The CLI's ``--ip``
    option needs a bare address; this strips any trailing ``/<prefix>``
    that labgrid hands back from ``ip addr show``.
    """
    addresses = shell.get_ip_addresses()
    assert addresses, "ADIShellDriver could not report a board IP address"
    return str(addresses[0].ip).split("/")[0]


def wait_for_ssh(
    ip: str,
    *,
    user: str = KUIPER_USER,
    password: str = KUIPER_PASSWORD,
    timeout: float = 180.0,
    poll_interval: float = 2.0,
) -> None:
    """Block until SSH login succeeds against *ip* or *timeout* elapses.

    Used after CLI commands that issue ``--reboot``: the labgrid serial
    shell becomes stale, so subsequent verification has to ride on a
    fresh :class:`fabric.Connection`.  Failure raises
    ``TimeoutError`` with the last underlying exception's message so
    the test report points at the actual SSH error.
    """
    from fabric import Connection

    deadline = time.monotonic() + timeout
    last_exc: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with Connection(
                f"{user}@{ip}:22",
                connect_kwargs={"password": password},
            ) as c:
                c.run("uname -r", hide=True, warn=False)
            return
        except Exception as exc:  # noqa: BLE001 — any connect failure → keep polling
            last_exc = exc
            time.sleep(poll_interval)
    raise TimeoutError(
        f"SSH to {user}@{ip} did not succeed within {timeout:.0f}s; "
        f"last error: {last_exc!r}"
    )


@contextlib.contextmanager
def sd_marker_cleanup(
    ip: str,
    marker_basenames: list[str],
    *,
    user: str = KUIPER_USER,
    password: str = KUIPER_PASSWORD,
) -> Iterator[None]:
    """Ensure named files at the SD root are removed on context exit.

    Use to wrap tests that *create* a new file on the board's SD card
    (e.g. ``sd-remote-copy`` of a marker file) so the cleanup happens
    even if the test body raises.  The cleanup mounts
    ``/dev/mmcblk0p1`` (the convention :meth:`adidt.dt.dt._handle_sd_mount`
    follows), removes each named file from the SD root, and unmounts.

    Note: this helper does NOT back up pre-existing files.  Tests that
    mutate stock boot artifacts (``system.dtb``, ``BOOT.BIN``) need
    SFTP-based backup-to-local-disk because in-target ``/tmp`` is
    tmpfs-backed and gets wiped on reboot.  Such tests are out of
    scope for the initial CLI hw test set.
    """
    from fabric import Connection

    mount_dir = "/tmp/adidt_cli_test_sd_mount"

    try:
        yield
    finally:
        with Connection(f"{user}@{ip}:22", connect_kwargs={"password": password}) as c:
            c.run(f"mkdir -p {mount_dir}", hide=True, warn=True)
            c.run(f"umount {mount_dir}", hide=True, warn=True)
            c.run("umount /dev/mmcblk0p1", hide=True, warn=True)
            mount_res = c.run(f"mount /dev/mmcblk0p1 {mount_dir}", hide=True, warn=True)
            if mount_res.return_code != 0:
                return
            try:
                for name in marker_basenames:
                    c.run(
                        f"rm -f {mount_dir}/{Path(name).name}",
                        hide=True,
                        warn=True,
                    )
            finally:
                c.run(f"umount {mount_dir}", hide=True, warn=True)
