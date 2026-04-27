"""Live-board ``adidtc`` hardware tests for ADRV9009 + ZC706.

Mirrors :mod:`test.hw.test_cli_live_ad9081_zcu102_hw` for the
Zynq-7000 + TFTP-boot path.  Boots through
:mod:`test.hw.test_adrv9009_zc706_hw`'s SPEC, then exercises the
hardware-touching CLI commands against the live target.
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
from test.hw.test_adrv9009_zc706_hw import SPEC as XSA_SPEC


SPEC = dataclasses.replace(XSA_SPEC, out_label="adrv9009_cli_live")


@pytest.fixture(scope="module")
def booted(board, tmp_path_factory, request):
    """Boot the board once per module; expose ``(shell, ip)`` to all tests."""
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
    """``adidtc prop -cp adi,adrv9009 compatible`` reads the live ADRV9009 node."""
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
            "adi,adrv9009",
            "compatible",
        ],
    )
    assert "adi,adrv9009" in result.output, result.output


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
    """``adidtc sd-remote-copy --dry-run --show`` prints planned scp; no copy."""
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

    solver = tmp_path / "solved.json"
    solver.write_text(json.dumps({"out_dividers": [12, 12, 12, 12]}))

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
    """``adidtc sd-move <bogus> --dry-run --show`` runs without raising; SD untouched."""
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
        wait_for_ssh(ip, wait_for_down=True)

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
    (``devicetree.dtb`` on Zynq-7000).  In-target ``/tmp`` is
    tmpfs-backed and is wiped on reboot.
    """
    pytest.skip(
        "prop --reboot needs SFTP backup of SD devicetree.dtb; not yet implemented"
    )


@requires_lg
@pytest.mark.slow
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_jif_clock_with_reboot(booted):
    """Reserved for ``adidtc jif clock --reboot`` validation.

    Same constraint as :func:`test_prop_write_with_reboot`.
    """
    pytest.skip(
        "jif clock --reboot needs SFTP backup of SD devicetree.dtb; not yet implemented"
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
