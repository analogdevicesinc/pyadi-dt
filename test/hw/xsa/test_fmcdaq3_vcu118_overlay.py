"""FMCDAQ3 + VCU118 runtime device-tree overlay hardware test.

Mirrors :mod:`test.hw.xsa.test_ad9081_zcu102_overlay` for the VCU118 +
FMCDAQ3 daughter card on the ``nuc`` labgrid place.  Same six-test
shape (unit, configfs, load, DMA, unload, reload), same configfs
lifecycle, same dmesg-delta error gating.

Differences from the AD9081 / ADRV9009 variants:

1. **Boot transport** — VCU118 runs a MicroBlaze soft CPU from the FPGA
   fabric; there is no PS, U-Boot, SD card, or TFTP path.  Labgrid
   drives the boot through :class:`BootFabric` + :class:`XilinxDeviceJTAG`
   on the ``nuc`` exporter, which loads the bitstream and a
   ``simpleImage.vcu118_fmcdaq3.strip`` (kernel + embedded DTB) over
   JTAG.  The overlay is layered on top of the embedded DTB at runtime
   via configfs — no DTB rebuild and no kernel-image fixture are
   required.  The companion full-DTB smoke test
   :mod:`test.hw.test_fmcdaq3_vcu118_hw` already validates that the
   embedded DTB probes AD9528 + AD9680 + AD9152 cleanly and that the
   AD9680 RX path delivers real samples; this test extends that
   coverage with the configfs apply / unapply / reapply lifecycle.

2. **Configfs gate** — Kuiper's MicroBlaze simpleImage is the most
   likely place we will find ``CONFIG_OF_OVERLAY``/``CONFIG_OF_CONFIGFS``
   missing.  The fixture probes
   ``/sys/kernel/config/device-tree/overlays`` and skips the
   lifecycle/DMA tests cleanly when absent;
   :func:`test_configfs_overlay_support` retains its strict-assert
   behavior so a configfs-less kernel is still an explicit failure of
   *that* test.

3. **XSA prerequisite** — the standard Kuiper boot-partition release
   does not include a ``vcu118_fmcdaq3`` project (it only ships Zynq
   family projects), so :func:`acquire_xsa` cannot download one.  The
   FMCDAQ3+VCU118 ``system_top.xsa`` from the local HDL/PetaLinux
   build must be committed to ``test/hw/xsa/system_top_fmcdaq3_vcu118.xsa``
   before the test can run; the ``pipeline_result`` fixture
   :func:`pytest.skip` s with a clear message until that file is
   present.

LG_ENV: ``test/hw/env/nuc.yaml``.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

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
    check_jesd_framing_plausibility,
    compile_dtso_to_dtbo,
    deploy_dtbo_via_shell,
    load_overlay,
    open_iio_context,
    overlay_is_loaded,
    shell_out,
    unload_overlay,
)

_HAS_LG = bool(os.environ.get("LG_COORDINATOR") or os.environ.get("LG_ENV"))
requires_lg = pytest.mark.skipif(
    not _HAS_LG,
    reason=(
        "set LG_COORDINATOR or LG_ENV for FMCDAQ3 VCU118 overlay hardware tests"
        " (see .env.example)"
    ),
)

OVERLAY_NAME = "fmcdaq3_vcu118_xsa"
DTBO_REMOTE_PATH = f"/tmp/{OVERLAY_NAME}.dtbo"
FDT_MAGIC = b"\xd0\x0d\xfe\xed"

DDS_TONE_HZ = 1_000_000
DDS_SCALE = 0.5
RX_BUFFER_SIZE = 2**14

# IIO device names the FMCDAQ3 base DTB exposes.  The clock chip is
# AD9528; the AD9680 RX frontend appears under several aliases
# depending on whether the DTB is Kuiper-built or sdtgen-built.
EXPECTED_IIO_NAMES_ALL = ("ad9528",)
EXPECTED_IIO_NAMES_ANY = (
    "axi-ad9680-hpc",
    "axi-ad9680-rx-hpc",
    "axi-ad9680-core-lpc",
    "ad_ip_jesd204_tpl_adc",
)


def _fmcdaq3_vcu118_cfg() -> dict[str, Any]:
    """FMCDAQ3+VCU118 XSA pipeline cfg.

    The profile JSON ``adidt/xsa/profiles/fmcdaq3_vcu118.json`` already
    supplies the full ``fmcdaq3_board`` defaults and the JESD framing
    (RX & TX both M=2 L=4 F=1 Np=16 S=1, the FMCDAQ3 reference HDL
    default).  We re-state the framing here only so
    :func:`check_jesd_framing_plausibility` can sanity-check it before
    the pipeline is run.
    """
    cfg: dict[str, Any] = {
        "fmcdaq3_board": {},
        "jesd": {
            "rx": {"F": 1, "K": 32, "M": 2, "L": 4, "Np": 16, "S": 1},
            "tx": {"F": 1, "K": 32, "M": 2, "L": 4, "Np": 16, "S": 1},
        },
    }
    framing_warnings = check_jesd_framing_plausibility(cfg["jesd"])
    assert not framing_warnings, (
        "JESD cfg is structurally inconsistent (will fail ILAS):\n  "
        + "\n  ".join(framing_warnings)
    )
    return cfg


@pytest.fixture(scope="module")
def pipeline_result(tmp_path_factory) -> dict:
    """Run :class:`XsaPipeline` once per module and return its output dict.

    The XSA must be committed to the repo at one of the paths checked
    below — :func:`acquire_xsa` cannot download a VCU118 / MicroBlaze
    XSA from the standard Kuiper boot-partition release because that
    release only ships Zynq family projects (``zynq*``, ``zynqmp*``,
    ``versal*``).  The lab's ``simpleImage.vcu118_fmcdaq3.strip`` on
    the ``nuc`` exporter is built from a separate HDL/PetaLinux flow
    whose XSA is not part of Kuiper's release tarball.

    Provide the XSA by copying the ``system_top.xsa`` from a local
    ``hdl/projects/fmcdaq3/vcu118`` build (or the lab's archive of
    that build) into ``test/hw/xsa/system_top_fmcdaq3_vcu118.xsa``.
    """
    candidates = (
        Path(__file__).parent / "system_top_fmcdaq3_vcu118.xsa",
        Path(__file__).parent / "ref_data" / "system_top_fmcdaq3_vcu118.xsa",
    )
    xsa_path = next((p for p in candidates if p.exists()), None)
    if xsa_path is None:
        pytest.skip(
            "FMCDAQ3+VCU118 XSA fixture missing — commit the system_top.xsa "
            f"from the FMCDAQ3 VCU118 HDL build to one of: "
            f"{', '.join(str(p) for p in candidates)}"
        )

    topology = XsaParser().parse(xsa_path)
    assert topology.jesd204_rx, "No JESD204 RX instances in XSA topology"
    assert topology.jesd204_tx, "No JESD204 TX instances in XSA topology"

    out_dir = tmp_path_factory.mktemp("overlay") / "out"
    return XsaPipeline().run(
        xsa_path=xsa_path,
        cfg=_fmcdaq3_vcu118_cfg(),
        output_dir=out_dir,
        profile="fmcdaq3_vcu118",
        sdtgen_timeout=300,
    )


@pytest.fixture(scope="module")
def overlay_dtbo(pipeline_result, tmp_path_factory) -> Path:
    """Compile the pipeline ``.dtso`` to ``.dtbo`` (module-scoped, once)."""
    overlay_src: Path = pipeline_result["overlay"]
    assert overlay_src.exists(), f"pipeline did not emit overlay DTSO: {overlay_src}"

    dtbo_dir = tmp_path_factory.mktemp("dtbo")
    dtbo = dtbo_dir / f"{OVERLAY_NAME}.dtbo"
    compile_dtso_to_dtbo(overlay_src, dtbo)

    assert dtbo.exists(), f"dtc -@ did not produce DTBO: {dtbo}"
    size = dtbo.stat().st_size
    assert size > 100, f"DTBO suspiciously small ({size} bytes): {dtbo}"
    magic = dtbo.read_bytes()[:4]
    assert magic == FDT_MAGIC, f"DTBO missing FDT magic (got {magic.hex()}): {dtbo}"
    return dtbo


@pytest.fixture(scope="module")
def booted_board(board, overlay_dtbo):
    """Drive ``BootFabric`` to shell, gate-skip on missing configfs, stage DTBO.

    No merged DTB compile or kernel image fixture: the simpleImage on
    the exporter already embeds the FMCDAQ3 base DTB.  The overlay is
    layered on top of that pre-probed tree at runtime via configfs.
    """
    board.transition("shell")
    shell = board.target.get_driver("ADIShellDriver")

    res = shell_out(
        shell,
        f"test -d {CONFIGFS_OVERLAYS} && echo OK || echo MISSING",
    )
    if "OK" not in res:
        pytest.skip(
            "MicroBlaze kernel lacks CONFIG_OF_OVERLAY / CONFIG_OF_CONFIGFS "
            "(simpleImage was not built with overlay support)"
        )

    deploy_dtbo_via_shell(shell, overlay_dtbo, DTBO_REMOTE_PATH)

    if overlay_is_loaded(shell, OVERLAY_NAME):
        unload_overlay(shell, OVERLAY_NAME)

    return board


def _shell(booted):
    return booted.target.get_driver("ADIShellDriver")


def _ensure_unloaded(shell) -> None:
    if overlay_is_loaded(shell, OVERLAY_NAME):
        unload_overlay(shell, OVERLAY_NAME)
        time.sleep(2.0)


def _apply_and_wait(shell) -> None:
    res = load_overlay(shell, OVERLAY_NAME, DTBO_REMOTE_PATH)
    assert "RC=0" in res, f"overlay load failed: {res}"
    # FMCDAQ3 has fewer probe stages than the Talise/Mykonos paths;
    # 5s is enough for AD9528 → AD9680 / AD9152 re-probe + JESD FSM
    # to walk SYNC → ILAS → DATA.
    time.sleep(5.0)


def _assert_iio_devices_present(ctx, *, context: str) -> None:
    found = {d.name for d in ctx.devices if d.name}
    suffix = f" ({context})" if context else ""
    for required in EXPECTED_IIO_NAMES_ALL:
        assert required in found, (
            f"IIO device {required!r} not present{suffix}. Devices: {sorted(found)}"
        )
    assert any(n in found for n in EXPECTED_IIO_NAMES_ANY), (
        f"AD9680 RX frontend not present{suffix}. "
        f"Expected one of {EXPECTED_IIO_NAMES_ANY}; "
        f"found: {sorted(found)}"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_overlay_generation_unit(pipeline_result, overlay_dtbo):
    """No-hardware check: the pipeline's DTSO is a valid overlay + compiles."""
    dtso: Path = pipeline_result["overlay"]
    src = dtso.read_text()
    assert "/plugin/;" in src, (
        f"Pipeline overlay missing /plugin/; directive — "
        f"dtc -@ will not treat it as an overlay: {dtso}"
    )
    assert "ad9680" in src.lower() or "ad9152" in src.lower() or "axi-jesd204" in src, (
        f"Pipeline overlay does not reference FMCDAQ3 / JESD nodes: {dtso}"
    )
    assert overlay_dtbo.exists() and overlay_dtbo.stat().st_size > 100


@requires_lg
@pytest.mark.lg_feature(["fmcdaq3", "vcu118"])
def test_configfs_overlay_support(board):
    """Target kernel must support runtime overlays via configfs.

    Bypasses the ``booted_board`` fixture (which would skip rather than
    fail on missing configfs) so a configfs-less simpleImage surfaces
    here as an explicit test failure.
    """
    board.transition("shell")
    shell = board.target.get_driver("ADIShellDriver")
    assert_configfs_overlay_support(shell)


@requires_lg
@pytest.mark.lg_feature(["fmcdaq3", "vcu118"])
def test_load_overlay(booted_board, tmp_path):
    """Apply the overlay; verify clean probe, IIO discovery, and JESD DATA."""
    shell = _shell(booted_board)
    _ensure_unloaded(shell)

    dmesg_baseline = int(shell_out(shell, "dmesg | wc -l").strip() or "0")

    _apply_and_wait(shell)

    dmesg_full = shell_out(shell, "dmesg")
    (tmp_path / "dmesg_after_load.log").write_text(dmesg_full)
    dmesg_new = "\n".join(dmesg_full.splitlines()[dmesg_baseline:])
    (tmp_path / "dmesg_overlay_only.log").write_text(dmesg_new)
    assert_no_kernel_faults(dmesg_new)
    assert_no_probe_errors(dmesg_new)

    ctx, _ = open_iio_context(shell)
    _assert_iio_devices_present(ctx, context="after overlay load")

    rx_status, tx_status = assert_jesd_links_data(shell, context="after overlay load")
    print(f"$ cat .../*.axi?jesd204?rx/status\n{rx_status}")
    print(f"$ cat .../*.axi?jesd204?tx/status\n{tx_status}")


@requires_lg
@pytest.mark.lg_feature(["fmcdaq3", "vcu118"])
def test_dma_loopback(booted_board):
    """Verify DMA RX data path on AD9680.

    Mandatory: :func:`assert_rx_capture_valid` confirms a non-zero,
    non-latched RX buffer arrives.  The companion smoke test
    :mod:`test.hw.test_fmcdaq3_vcu118_hw` already validates the same
    capture against the embedded base DTB; this run validates it after
    the overlay has been re-applied through configfs, exercising the
    overlay tear-down/re-apply path on the data layer.

    No DDS/SNR phase: FMCDAQ3 reference HDL does not have an internal
    DAC→ADC loopback, and the AD9680 ADC is the only buffered RX path
    in the design.  An external SMA tone is a lab-setup concern, not
    an overlay-lifecycle concern.
    """
    pytest.importorskip("adi")

    shell = _shell(booted_board)
    if not overlay_is_loaded(shell, OVERLAY_NAME):
        pytest.skip("overlay not loaded — test_load_overlay must run first")

    ctx, _ = open_iio_context(shell)
    assert_rx_capture_valid(
        ctx,
        EXPECTED_IIO_NAMES_ANY,
        n_samples=2**12,
        context="fmcdaq3 vcu118 overlay",
    )


@requires_lg
@pytest.mark.lg_feature(["fmcdaq3", "vcu118"])
def test_unload_overlay(booted_board):
    """Removing the configfs entry tears down without kernel faults."""
    shell = _shell(booted_board)
    if not overlay_is_loaded(shell, OVERLAY_NAME):
        _apply_and_wait(shell)

    res = unload_overlay(shell, OVERLAY_NAME)
    assert "RC=0" in res, f"overlay unload failed: {res}"
    time.sleep(2.0)

    assert not overlay_is_loaded(shell, OVERLAY_NAME), (
        "overlay configfs entry still present after rmdir"
    )

    dmesg_txt = shell_out(shell, "dmesg")
    assert_no_kernel_faults(dmesg_txt)


@requires_lg
@pytest.mark.lg_feature(["fmcdaq3", "vcu118"])
def test_reload_overlay(booted_board):
    """Load → unload → load cycle; re-verify devices + JESD link."""
    shell = _shell(booted_board)
    _ensure_unloaded(shell)

    _apply_and_wait(shell)
    ctx, _ = open_iio_context(shell)
    _assert_iio_devices_present(ctx, context="after overlay reload")
    assert_jesd_links_data(shell, context="after overlay reload")
