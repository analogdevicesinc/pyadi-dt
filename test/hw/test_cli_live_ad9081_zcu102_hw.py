"""Live-board ``adidtc`` hardware tests for AD9081 + ZCU102.

Boots the AD9081+ZCU102 board through the standard XSA-pipeline path
(see :mod:`test.hw.test_ad9081_zcu102_xsa_hw`) once per module, then
exercises the hardware-touching CLI commands against the live target.

Test ordering matters: read-only and ``--dry-run`` tests come first
while the labgrid serial shell is still valid; reboot variants come
last because they invalidate the labgrid shell handle (subsequent
verification has to ride on a fresh :mod:`fabric` SSH session).
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from fabric import Connection

from test.hw._cli_base import (
    KUIPER_PASSWORD,
    KUIPER_USER,
    discover_board_ipv4,
    run_adidtc,
    sd_marker_cleanup,
    wait_for_ssh,
)
from test.hw._system_base import requires_lg, run_xsa_boot_and_verify
from test.hw.test_ad9081_zcu102_xsa_hw import SPEC as XSA_SPEC


# Reuse the boot SPEC verbatim but override out_label so dmesg logs do
# not collide with the python-API XSA test.
SPEC = dataclasses.replace(XSA_SPEC, out_label="ad9081_cli_live")


@pytest.fixture(scope="module")
def booted(board, tmp_path_factory, request):
    """Boot the board once per module; expose ``(shell, ip)`` to all tests.

    Reuses :func:`run_xsa_boot_and_verify` so the same boot/probe
    invariants the standard hw tests assert apply here too.  IP
    discovery mirrors the pattern used by
    :func:`test.hw.hw_helpers.open_iio_context`.
    """
    tmp_path = tmp_path_factory.mktemp("cli_live")
    shell, _ctx, _dmesg = run_xsa_boot_and_verify(
        SPEC, board=board, request=request, tmp_path=tmp_path
    )
    ip = discover_board_ipv4(shell)
    print(f"booted board, SSH IP: {ip}")
    yield shell, ip


# ---------------------------------------------------------------------------
# Read-only tests
# ---------------------------------------------------------------------------


@requires_lg
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_prop_read_compatible(booted):
    """``adidtc prop -cp adi,ad9081 compatible`` reads the live AD9081 node."""
    _shell, ip = booted
    result = run_adidtc(
        [
            "-c",
            "remote_sysfs",
            "-i",
            ip,
            "-u",
            KUIPER_USER,
            "-w",
            KUIPER_PASSWORD,
            "prop",
            "-cp",
            "adi,ad9081",
            "compatible",
        ],
    )
    assert "adi,ad9081" in result.output, result.output


@requires_lg
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_props_read_amba(booted):
    """``adidtc props amba`` lists nodes under amba on the live board."""
    _shell, ip = booted
    result = run_adidtc(
        [
            "-c",
            "remote_sysfs",
            "-i",
            ip,
            "-u",
            KUIPER_USER,
            "-w",
            KUIPER_PASSWORD,
            "props",
            "amba",
        ],
    )
    assert result.output.strip(), "props produced no output"


# ---------------------------------------------------------------------------
# --dry-run tests
# ---------------------------------------------------------------------------


@requires_lg
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_sd_remote_copy_dry_run(booted, tmp_path: Path):
    """``adidtc sd-remote-copy --dry-run --show`` prints the planned scp; no copy."""
    _shell, ip = booted
    marker = tmp_path / "cli_dryrun_marker.txt"
    marker.write_text("dryrun")

    result = run_adidtc(
        [
            "-c",
            "remote_sd",
            "-i",
            ip,
            "-u",
            KUIPER_USER,
            "-w",
            KUIPER_PASSWORD,
            "sd-remote-copy",
            str(marker),
            "--dry-run",
            "--show",
        ],
    )
    assert "scp" in result.output, result.output
    assert marker.name in result.output

    # Confirm via SFTP that the marker did NOT land on the SD root.
    with Connection(
        f"{KUIPER_USER}@{ip}:22", connect_kwargs={"password": KUIPER_PASSWORD}
    ) as c:
        mount = "/tmp/adidt_cli_dryrun_check"
        c.run(f"mkdir -p {mount}", hide=True)
        c.run(f"umount {mount}", hide=True, warn=True)
        c.run("umount /dev/mmcblk0p1", hide=True, warn=True)
        c.run(f"mount /dev/mmcblk0p1 {mount}", hide=True)
        try:
            present = c.run(
                f"test -f {mount}/{marker.name}", hide=True, warn=True
            ).return_code
        finally:
            c.run(f"umount {mount}", hide=True, warn=True)
        assert present != 0, f"--dry-run unexpectedly copied {marker.name} to SD"


@requires_lg
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_jif_clock_dry_run(booted, tmp_path: Path):
    """``adidtc jif clock --dry-run`` prints planned dividers, writes nothing."""
    _shell, ip = booted

    # A minimal solver-style JSON; the exact divider values are
    # irrelevant under --dry-run because update_current_dt is skipped.
    solver = tmp_path / "solved.json"
    solver.write_text(json.dumps({"out_dividers": [12, 12, 12, 12]}))

    # jif is registered as a sub-group on the top-level cli; global
    # options (-c/-i/-u/-w) must come before "jif", not after.
    result = run_adidtc(
        [
            "-c",
            "remote_sd",
            "-i",
            ip,
            "-u",
            KUIPER_USER,
            "-w",
            KUIPER_PASSWORD,
            "jif",
            "clock",
            "-f",
            str(solver),
            "--dry-run",
        ],
    )
    assert "dry-run: no changes written." in result.output, result.output


@requires_lg
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_sd_move_dry_run(booted):
    """``adidtc sd-move <bogus> --dry-run --show`` runs without raising; SD untouched.

    On stock Kuiper images the AD9081+ZCU102 SD card carries reference
    designs that are listed by :meth:`adidt.sd.sd.update_existing_boot_files`
    when invoked.  A bogus design name causes the helper to print the
    available list and return cleanly (exit 0); ``--dry-run`` keeps
    the SD untouched either way.
    """
    _shell, ip = booted
    result = run_adidtc(
        [
            "-c",
            "remote_sd",
            "-i",
            ip,
            "-u",
            KUIPER_USER,
            "-w",
            KUIPER_PASSWORD,
            "sd-move",
            "definitely-not-a-real-design",
            "--dry-run",
            "--show",
        ],
    )
    # Either we got the "design not found" listing or no-op success; in
    # both cases exit 0 and no SD mutation.
    assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# Reboot tests (slow; invalidate the labgrid serial shell)
# ---------------------------------------------------------------------------


@requires_lg
@pytest.mark.slow
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_sd_remote_copy_with_reboot(booted, tmp_path: Path):
    """``sd-remote-copy --reboot`` lands the file and the board returns to SSH."""
    _shell, ip = booted
    marker = tmp_path / "adidt_cli_marker.txt"
    marker.write_text("hello from the cli hw test")

    with sd_marker_cleanup(ip, [marker.name]):
        run_adidtc(
            [
                "-c",
                "remote_sd",
                "-i",
                ip,
                "-u",
                KUIPER_USER,
                "-w",
                KUIPER_PASSWORD,
                "sd-remote-copy",
                str(marker),
                "--reboot",
            ],
        )
        wait_for_ssh(ip)

        with Connection(
            f"{KUIPER_USER}@{ip}:22",
            connect_kwargs={"password": KUIPER_PASSWORD},
        ) as c:
            mount = "/tmp/adidt_cli_reboot_check"
            c.run(f"mkdir -p {mount}", hide=True)
            c.run(f"umount {mount}", hide=True, warn=True)
            c.run("umount /dev/mmcblk0p1", hide=True, warn=True)
            c.run(f"mount /dev/mmcblk0p1 {mount}", hide=True)
            try:
                landed = c.run(
                    f"test -f {mount}/{marker.name}", hide=True, warn=True
                ).return_code
                contents = c.run(
                    f"cat {mount}/{marker.name}", hide=True, warn=True
                ).stdout
            finally:
                c.run(f"umount {mount}", hide=True, warn=True)
            assert landed == 0, f"marker {marker.name} not present on SD post-reboot"
            assert "hello from the cli hw test" in contents


@requires_lg
@pytest.mark.slow
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_prop_write_with_reboot(booted):
    """Reserved for ``adidtc prop --reboot`` validation.

    Skipped pending an SFTP-based backup helper for stock SD artifacts
    (``system.dtb``).  The current ``sd_marker_cleanup`` only handles
    test-created files; mutating ``system.dtb`` requires saving the
    original to local disk before reboot (in-target ``/tmp`` is
    tmpfs-backed and is wiped on reboot).
    """
    pytest.skip("prop --reboot needs SFTP backup of SD system.dtb; not yet implemented")


@requires_lg
@pytest.mark.slow
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_jif_clock_with_reboot(booted):
    """Reserved for ``adidtc jif clock --reboot`` validation.

    Same constraint as :func:`test_prop_write_with_reboot`: the jif
    write path mutates ``system.dtb`` on the SD card, which would
    require an SFTP-based backup helper to be safely reversible.
    """
    pytest.skip(
        "jif clock --reboot needs SFTP backup of SD system.dtb; not yet implemented"
    )


@requires_lg
@pytest.mark.slow
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_sd_move_with_reboot(booted):
    """Reserved for ``adidtc sd-move --reboot`` validation.

    Skipped because a meaningful test requires the SD to carry at
    least two reference designs and a reliable way to restore the
    original active design afterwards.  Lab-image-dependent.
    """
    pytest.skip("sd-move --reboot requires multi-design SD layout + safe restore")
