"""Shared fixtures and test functions for the overlay-lifecycle suite.

Each board's ``test_*_overlay.py`` declares a
:class:`~test.hw.xsa._overlay_spec.BoardOverlayProfile` instance and
exposes it via a module-scoped ``overlay_spec`` fixture, then imports
the three fixtures (``pipeline_result``, ``overlay_dtbo``,
``booted_board``) and the six test functions defined below.  Pytest
collects ``test_*`` callables from the importing test module's
namespace, so the imported tests appear under their canonical names
in ``pytest --collect-only`` and per-file selection still works.

This module's name starts with ``_`` so pytest does not collect tests
directly from it; the canonical definition site is here, the
collection sites are the per-board files that import these names.
"""

from __future__ import annotations

import os
import shutil as _shutil
import time
from pathlib import Path

import pytest

from adidt.xsa.pipeline import XsaPipeline
from adidt.xsa.topology import XsaParser
from test.hw.hw_helpers import (
    CONFIGFS_OVERLAYS,
    assert_configfs_overlay_support,
    assert_jesd_links_data,
    assert_no_kernel_faults,
    assert_no_probe_errors,
    assert_rx_capture_valid,
    compile_dts_to_dtb,
    compile_dtso_to_dtbo,
    deploy_and_boot,
    deploy_dtbo_via_shell,
    load_overlay,
    open_iio_context,
    overlay_is_loaded,
    shell_out,
    stage_dtb_as_devicetree,
    unload_overlay,
)
from test.hw.xsa._overlay_fft import fft_loopback_check, prepare_pyadi_device


_HAS_LG = bool(os.environ.get("LG_COORDINATOR") or os.environ.get("LG_ENV"))
requires_lg = pytest.mark.skipif(
    not _HAS_LG,
    reason=(
        "set LG_COORDINATOR or LG_ENV for overlay hardware tests "
        "(see .env.example)"
    ),
)

_FDT_MAGIC = b"\xd0\x0d\xfe\xed"
_OVERLAY_TEARDOWN_SETTLE_S = 2.0


# ---------------------------------------------------------------------------
# Module-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pipeline_result(overlay_spec, tmp_path_factory) -> dict:
    """Run :class:`XsaPipeline` once per board module.

    Resolves the XSA via ``overlay_spec.xsa_resolver`` (which may
    ``pytest.skip`` if the fixture is unavailable), parses the topology,
    runs the board's optional ``topology_assert``, then returns the
    pipeline output dict.
    """
    spec = overlay_spec
    xsa_path = spec.xsa_resolver(tmp_path_factory.mktemp("xsa_dl"))
    topology = XsaParser().parse(xsa_path)
    spec.topology_assert(topology)
    out_dir = tmp_path_factory.mktemp("overlay") / "out"
    return XsaPipeline().run(
        xsa_path=xsa_path,
        cfg=spec.cfg_builder(),
        output_dir=out_dir,
        profile=spec.sdtgen_profile,
        sdtgen_timeout=spec.sdtgen_timeout,
    )


@pytest.fixture(scope="module")
def overlay_dtbo(overlay_spec, pipeline_result, tmp_path_factory) -> Path:
    """Compile the pipeline ``.dtso`` to ``.dtbo`` (module-scoped, once)."""
    overlay_src: Path = pipeline_result["overlay"]
    assert overlay_src.exists(), f"pipeline did not emit overlay DTSO: {overlay_src}"

    dtbo_dir = tmp_path_factory.mktemp("dtbo")
    dtbo = dtbo_dir / f"{overlay_spec.overlay_name}.dtbo"
    compile_dtso_to_dtbo(overlay_src, dtbo)

    assert dtbo.exists(), f"dtc -@ did not produce DTBO: {dtbo}"
    size = dtbo.stat().st_size
    assert size > 100, f"DTBO suspiciously small ({size} bytes): {dtbo}"
    magic = dtbo.read_bytes()[:4]
    assert magic == _FDT_MAGIC, f"DTBO missing FDT magic (got {magic.hex()}): {dtbo}"
    return dtbo


@pytest.fixture(scope="module")
def booted_board(
    request,
    overlay_spec,
    board,
    pipeline_result,
    overlay_dtbo,
    tmp_path_factory,
):
    """Bring the board up to a shell ready for overlay apply.

    Dispatches on ``overlay_spec.boot_mode``:

    * ``"tftp"`` — compile merged DTS, stage as ``devicetree.dtb``,
      ``deploy_and_boot`` with the kernel image fixture named in
      ``kernel_fixture_name``.
    * ``"sd"`` — same but stage as ``system.dtb`` for Kuiper's ZynqMP
      U-Boot.
    * ``"fabric_jtag"`` — no DTB rebuild, no kernel fixture; transition
      directly to ``shell`` and ``pytest.skip`` if the kernel lacks
      configfs overlay support (the simpleImage path on VCU118).

    All three paths then transfer the DTBO via the serial shell and
    ensure the configfs overlay slot is empty before yielding.
    """
    spec = overlay_spec

    if spec.boot_mode == "fabric_jtag":
        board.transition("shell")
        shell = board.target.get_driver("ADIShellDriver")
        res = shell_out(
            shell,
            f"test -d {CONFIGFS_OVERLAYS} && echo OK || echo MISSING",
        )
        if "OK" not in res:
            pytest.skip(
                "kernel lacks CONFIG_OF_OVERLAY / CONFIG_OF_CONFIGFS "
                "(simpleImage was not built with overlay support)"
            )
    elif spec.boot_mode in ("tftp", "sd"):
        kernel_image = (
            request.getfixturevalue(spec.kernel_fixture_name)
            if spec.kernel_fixture_name
            else None
        )
        out_dir = tmp_path_factory.mktemp("merged_boot")
        merged_dts = pipeline_result["merged"]
        dtb_raw = out_dir / f"{spec.overlay_name}.dtb"
        compile_dts_to_dtb(merged_dts, dtb_raw)

        if spec.boot_mode == "tftp":
            staged = stage_dtb_as_devicetree(dtb_raw, out_dir / "tftp_staging")
        else:
            staged_dir = out_dir / "sd_staging"
            staged_dir.mkdir(parents=True, exist_ok=True)
            staged = staged_dir / "system.dtb"
            _shutil.copyfile(dtb_raw, staged)

        shell = deploy_and_boot(board, staged, kernel_image)
    else:
        raise ValueError(f"unknown boot_mode: {spec.boot_mode!r}")

    deploy_dtbo_via_shell(shell, overlay_dtbo, _dtbo_remote_path(spec))
    if overlay_is_loaded(shell, spec.overlay_name):
        unload_overlay(shell, spec.overlay_name)
    return board


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dtbo_remote_path(spec) -> str:
    return f"/tmp/{spec.overlay_name}.dtbo"


def _shell(booted):
    return booted.target.get_driver("ADIShellDriver")


def _ensure_unloaded(shell, name: str) -> None:
    if overlay_is_loaded(shell, name):
        unload_overlay(shell, name)
        time.sleep(_OVERLAY_TEARDOWN_SETTLE_S)


def _apply_and_wait(shell, spec) -> None:
    res = load_overlay(shell, spec.overlay_name, _dtbo_remote_path(spec))
    assert "RC=0" in res, f"overlay load failed: {res}"
    time.sleep(spec.settle_after_apply_s)


def _assert_iio_devices_present(spec, ctx, *, context: str) -> None:
    found = {d.name for d in ctx.devices if d.name}
    suffix = f" ({context})" if context else ""
    for required in spec.iio_required_all:
        assert required in found, (
            f"IIO device {required!r} not present{suffix}. Devices: {sorted(found)}"
        )
    if spec.iio_required_any:
        assert any(n in found for n in spec.iio_required_any), (
            f"{spec.iio_frontend_label} not present{suffix}. "
            f"Expected one of {spec.iio_required_any}; "
            f"found: {sorted(found)}"
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_overlay_generation_unit(overlay_spec, pipeline_result, overlay_dtbo):
    """No-hardware check: the pipeline's DTSO is a valid overlay + compiles."""
    dtso: Path = pipeline_result["overlay"]
    src = dtso.read_text()
    assert "/plugin/;" in src, (
        f"Pipeline overlay missing /plugin/; directive — "
        f"dtc -@ will not treat it as an overlay: {dtso}"
    )
    src_lower = src.lower()
    for needle in overlay_spec.dtso_must_contain_all:
        assert needle.lower() in src_lower, (
            f"Pipeline overlay does not contain expected substring "
            f"{needle!r}: {dtso}"
        )
    if overlay_spec.dtso_must_contain_any:
        assert any(
            n.lower() in src_lower for n in overlay_spec.dtso_must_contain_any
        ), (
            f"Pipeline overlay does not contain any of "
            f"{overlay_spec.dtso_must_contain_any}: {dtso}"
        )
    assert overlay_dtbo.exists() and overlay_dtbo.stat().st_size > 100


@requires_lg
def test_configfs_overlay_support(overlay_spec, board, request):
    """Target kernel must support runtime overlays via configfs.

    For ``fabric_jtag`` boards this bypasses ``booted_board`` (which
    would skip rather than fail on missing configfs) so a configfs-less
    kernel surfaces here as an explicit failure.  For other boards, the
    fixture path is the normal one.
    """
    if overlay_spec.boot_mode == "fabric_jtag":
        board.transition("shell")
        shell = board.target.get_driver("ADIShellDriver")
    else:
        booted = request.getfixturevalue("booted_board")
        shell = _shell(booted)
    assert_configfs_overlay_support(shell)


@requires_lg
def test_load_overlay(overlay_spec, booted_board, tmp_path):
    """Apply the overlay; verify clean probe, IIO discovery, and JESD DATA."""
    spec = overlay_spec
    shell = _shell(booted_board)
    _ensure_unloaded(shell, spec.overlay_name)

    # dmesg before overlay-apply is the boot log — filter it out so we
    # only flag errors caused by the overlay itself.
    dmesg_baseline = int(shell_out(shell, "dmesg | wc -l").strip() or "0")

    _apply_and_wait(shell, spec)

    dmesg_full = shell_out(shell, "dmesg")
    (tmp_path / "dmesg_after_load.log").write_text(dmesg_full)
    dmesg_new = "\n".join(dmesg_full.splitlines()[dmesg_baseline:])
    (tmp_path / "dmesg_overlay_only.log").write_text(dmesg_new)
    assert_no_kernel_faults(dmesg_new)
    assert_no_probe_errors(spec.dmesg_filter(dmesg_new))

    ctx, _ = open_iio_context(shell)
    _assert_iio_devices_present(spec, ctx, context="after overlay load")

    rx_status, tx_status = assert_jesd_links_data(shell, context="after overlay load")
    print(f"$ cat .../*.axi?jesd204?rx/status\n{rx_status}")
    print(f"$ cat .../*.axi?jesd204?tx/status\n{tx_status}")


@requires_lg
def test_dma_loopback(overlay_spec, booted_board, tmp_path):
    """Verify the DMA RX data path; optionally check the FFT spectrum.

    Phase 1 — :func:`assert_rx_capture_valid` confirms a non-zero,
    non-latched RX buffer arrives.  Per-board hooks let the test push
    a Talise profile, disambiguate duplicate IIO names, and run extra
    diagnostics on capture failure.

    Phase 2 — when ``spec.fft_mode != "skip"``, drive a DDS tone and
    analyse the loopback spectrum (see :mod:`._overlay_fft`).
    """
    spec = overlay_spec
    if spec.fft_mode != "skip":
        pytest.importorskip("adi")

    shell = _shell(booted_board)
    if not overlay_is_loaded(shell, spec.overlay_name):
        pytest.skip("overlay not loaded — test_load_overlay must run first")

    if spec.pre_capture_hook is not None:
        did_something = spec.pre_capture_hook(shell, tmp_path)
        if did_something:
            assert_jesd_links_data(shell, context="after pre-capture hook")
        else:
            print(
                f"{spec.skip_reason_label}: pre-capture hook found nothing to "
                "do; proceeding with default state"
            )

    ctx, ip = open_iio_context(shell)

    if spec.capture_targets_resolver is not None:
        targets = tuple(spec.capture_targets_resolver(ctx))
    else:
        targets = spec.capture_target_names

    try:
        assert_rx_capture_valid(
            ctx,
            targets,
            n_samples=2**12,
            context=f"{spec.skip_reason_label} overlay",
        )
    except AssertionError:
        if spec.fft_failure_diagnostics is not None:
            try:
                spec.fft_failure_diagnostics(shell)
            except Exception as exc:  # noqa: BLE001 — diagnostics best-effort
                print(f"fft_failure_diagnostics raised: {exc}")
        raise

    if spec.fft_mode == "skip":
        return

    dev = prepare_pyadi_device(spec, ip)
    if dev is None:
        return

    sample_rate = int(dev.rx_sample_rate)
    fft_loopback_check(
        dev=dev,
        sample_rate=sample_rate,
        dds_tone_hz=spec.dds_tone_hz,
        dds_scale=spec.dds_scale,
        rx_buffer_size=spec.rx_buffer_size,
        mode=spec.fft_mode,
        label=spec.skip_reason_label,
    )


@requires_lg
def test_unload_overlay(overlay_spec, booted_board):
    """Removing the configfs entry tears down without kernel faults."""
    spec = overlay_spec
    shell = _shell(booted_board)
    if not overlay_is_loaded(shell, spec.overlay_name):
        # Could happen if test_load_overlay was deselected; apply + unload
        # rather than skipping so the unload path is always exercised.
        _apply_and_wait(shell, spec)

    res = unload_overlay(shell, spec.overlay_name)
    assert "RC=0" in res, f"overlay unload failed: {res}"
    time.sleep(_OVERLAY_TEARDOWN_SETTLE_S)

    assert not overlay_is_loaded(shell, spec.overlay_name), (
        "overlay configfs entry still present after rmdir"
    )

    dmesg_txt = shell_out(shell, "dmesg")
    assert_no_kernel_faults(dmesg_txt)


@requires_lg
def test_reload_overlay(overlay_spec, booted_board):
    """Load → unload → load cycle; re-verify devices + JESD link."""
    spec = overlay_spec
    shell = _shell(booted_board)
    _ensure_unloaded(shell, spec.overlay_name)

    _apply_and_wait(shell, spec)
    ctx, _ = open_iio_context(shell)
    _assert_iio_devices_present(spec, ctx, context="after overlay reload")
    assert_jesd_links_data(shell, context="after overlay reload")
