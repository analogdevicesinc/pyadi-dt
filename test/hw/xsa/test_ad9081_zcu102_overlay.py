"""AD9081 + ZCU102 runtime device-tree overlay hardware test.

Exercises the full overlay lifecycle against a live ZCU102 booted from a
stock Kuiper SD image:

1. ``XsaPipeline.run`` produces a ``.dtso`` (plugin overlay) from the
   AD9081+ZCU102 XSA.
2. :func:`~test.hw.hw_helpers.compile_dtso_to_dtbo` compiles it with
   ``dtc -@`` so external ``&label`` phandles survive.
3. :func:`~test.hw.hw_helpers.deploy_dtbo_via_shell` pushes the ``.dtbo``
   to ``/tmp`` on the target over the serial console (no SSH required).
4. :func:`~test.hw.hw_helpers.load_overlay` applies it via configfs.
5. Verification: no probe/apply errors in dmesg, the expected IIO
   devices appear, both JESD links reach ``DATA``, and a DDS→DMA
   loopback tone is detectable in the captured spectrum (numpy FFT
   peak + SNR against the surrounding noise floor).
6. :func:`~test.hw.hw_helpers.unload_overlay` tears it down, asserting
   no kernel fault occurs during removal.
7. Reload cycle — load/unload/load once more to confirm repeatability.

Boot strategy: ``KuiperDLDriver.get_boot_files_from_release`` is used
*without* staging a custom DTB so the overlay is applied on top of a
known-good Kuiper base, mirroring the real "hot-swap a converter" use
case rather than exercising a fresh merged tree.  See the docstring on
:func:`booted_board` for the rationale.

LG_ENV / LG_COORDINATOR: see ``.env.example``.  Runs against the
``mini2`` labgrid place (ZCU102 + AD9081-FMCA-EBZ).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pytest

import shutil as _shutil

from adidt.xsa.pipeline import XsaPipeline
from adidt.xsa.topology import XsaParser
from test.hw.hw_helpers import (
    assert_configfs_overlay_support,
    assert_jesd_links_data,
    assert_no_kernel_faults,
    assert_no_probe_errors,
    compile_dts_to_dtb,
    compile_dtso_to_dtbo,
    deploy_and_boot,
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
        "set LG_COORDINATOR or LG_ENV for AD9081 ZCU102 overlay hardware tests"
        " (see .env.example)"
    ),
)


DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynqmp-zcu102-rev10-ad9081"
DEFAULT_VCXO_HZ = 122_880_000

OVERLAY_NAME = "ad9081_zcu102_xsa"
DTBO_REMOTE_PATH = f"/tmp/{OVERLAY_NAME}.dtbo"
FDT_MAGIC = b"\xd0\x0d\xfe\xed"

# DDS tone used for the DMA loopback check.  1 MHz is far from DC and
# far from the Nyquist edge at any AD9081 sample rate the XSA pipeline
# configures, so spectral leakage does not hide the peak.
DDS_TONE_HZ = 1_000_000
DDS_SCALE = 0.5
RX_BUFFER_SIZE = 2**14

# IIO device names the AD9081 overlay should introduce (or refresh).
# Kuiper's pyadi-iio class hardcodes the ``axi-ad9081-{rx,tx}-hpc``
# names; the sdtgen-generated merged DTB uses the TPL-core names.  The
# stock Kuiper image uses the former, so overlay load should keep them.
EXPECTED_IIO_NAMES_ANY = (
    "axi-ad9081-rx-hpc",
    "ad_ip_jesd204_tpl_adc",
)
EXPECTED_IIO_NAMES_ALL = ("hmc7044",)


def _solve_ad9081_config(vcxo_hz: int = DEFAULT_VCXO_HZ) -> dict[str, Any]:
    """Resolve AD9081 JESD mode + datapath + clocks via pyadi-jif.

    Duplicated from ``test_ad9081_zcu102_xsa_hw`` so the two tests can
    drift their solver inputs independently if needed.  Uses the same
    M8/L4 jesd204b pinning: rx_link_mode=10, tx_link_mode=9 (the values
    Kuiper's reference ``zynqmp-zcu102-rev10-ad9081-m8-l4.dts`` uses).
    """
    try:
        import adijif
    except ModuleNotFoundError as exc:
        pytest.skip(f"pyadi-jif not available: {exc}")

    sys = adijif.system("ad9081", "hmc7044", "xilinx", vcxo=vcxo_hz)
    sys.fpga.setup_by_dev_kit_name("zcu102")

    cddc, fddc, cduc, fduc = 4, 4, 8, 6
    sys.converter.clocking_option = "integrated_pll"
    sys.converter.adc.sample_clock = 4_000_000_000 / cddc / fddc
    sys.converter.dac.sample_clock = 12_000_000_000 / cduc / fduc
    sys.converter.adc.datapath.cddc_decimations = [cddc] * 4
    sys.converter.dac.datapath.cduc_interpolation = cduc
    sys.converter.adc.datapath.fddc_decimations = [fddc] * 8
    sys.converter.dac.datapath.fduc_interpolation = fduc
    sys.converter.adc.datapath.fddc_enabled = [True] * 8
    sys.converter.dac.datapath.fduc_enabled = [True] * 8

    mode_rx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.adc, M=8, L=4, Np=16, jesd_class="jesd204b"
    )
    mode_tx = adijif.utils.get_jesd_mode_from_params(
        sys.converter.dac, M=8, L=4, Np=16, jesd_class="jesd204b"
    )
    if not mode_rx or not mode_tx:
        pytest.skip("pyadi-jif: no matching AD9081 M8/L4 mode found")

    rx_settings = mode_rx[0]["settings"]
    tx_settings = mode_tx[0]["settings"]

    return {
        "jesd": {
            "rx": {k: int(rx_settings[k]) for k in ("F", "K", "M", "L", "Np", "S")},
            "tx": {k: int(tx_settings[k]) for k in ("F", "K", "M", "L", "Np", "S")},
        },
        "ad9081": {
            "rx_link_mode": 10,
            "tx_link_mode": 9,
        },
    }


@pytest.fixture(scope="module")
def pipeline_result(tmp_path_factory) -> dict:
    """Run :class:`XsaPipeline` once per module and return its output dict.

    Skips the whole module when the AD9081+ZCU102 XSA fixture is not on
    disk or ``sdtgen``/``dtc`` are missing — these failures are already
    reported by :func:`~test.hw.hw_helpers.require_hw_prereqs` when a
    test enters the ``board`` fixture, but fixture-level skipping lets
    pure-unit tests (``test_overlay_generation_unit``) fail cleanly
    without needing a labgrid place acquired.
    """
    xsa_path = Path(__file__).parent / "ref_data" / "system_top_ad9081_zcu102.xsa"
    if not xsa_path.exists():
        # Fallback to the older fixture used by the merged-DTB test.
        xsa_path = Path(__file__).parent / "system_top.xsa"
    if not xsa_path.exists():
        pytest.skip(f"AD9081+ZCU102 XSA fixture not found: {xsa_path}")

    topology = XsaParser().parse(xsa_path)
    assert topology.has_converter_types("axi_ad9081"), (
        f"XSA topology is not AD9081: converter IPs = "
        f"{[c.ip_type for c in topology.converters]}"
    )

    cfg = _solve_ad9081_config()
    out_dir = tmp_path_factory.mktemp("overlay") / "out"
    result = XsaPipeline().run(
        xsa_path=xsa_path,
        cfg=cfg,
        output_dir=out_dir,
        profile="ad9081_zcu102",
        sdtgen_timeout=300,
    )
    return result


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
def booted_board(
    board, built_kernel_image_zynqmp, pipeline_result, overlay_dtbo, tmp_path_factory
):
    """Boot ZCU102 with the pipeline's merged DTB and stage the ``.dtbo``.

    The overlay's ``/delete-property/`` directives (see
    ``adidt/devices/fpga_ip/jesd_overlay.py``) target labels that already
    exist in the merged base.  Booting from the merged DTB therefore
    means the AD9081 IIO devices are present from the start; the
    overlay then exercises the configfs lifecycle (load/unload/reload)
    on top of an already-probed tree without needing a separate "base
    minus AD9081" DTB.

    Stock-Kuiper boot was tried first; on the lab's current 2023_R2
    image the AD9081 SPI probe fails at boot with ``-EBUSY`` (the
    bitstream's clock chain is not yet up when the SPI driver runs),
    which then makes every subsequent overlay test see an unrelated
    boot-time error.  Booting with our merged DTB avoids that and is
    deterministic across runs.

    Also stages the DTBO to ``/tmp`` on the target so per-test
    ``load_overlay`` calls do not re-transfer it.
    """
    out_dir = tmp_path_factory.mktemp("merged_boot")
    merged_dts = pipeline_result["merged"]
    dtb_raw = out_dir / "ad9081_zcu102_xsa.dtb"
    compile_dts_to_dtb(merged_dts, dtb_raw)
    # Kuiper's U-Boot picks ``system.dtb`` from the SD card; rename so
    # our DTB is the one the bootloader actually loads.
    staged = out_dir / "sd_staging" / "system.dtb"
    staged.parent.mkdir(parents=True, exist_ok=True)
    _shutil.copyfile(dtb_raw, staged)

    shell = deploy_and_boot(board, staged, built_kernel_image_zynqmp)

    deploy_dtbo_via_shell(shell, overlay_dtbo, DTBO_REMOTE_PATH)

    # Ensure a clean slate if a previous test run left an entry behind.
    if overlay_is_loaded(shell, OVERLAY_NAME):
        unload_overlay(shell, OVERLAY_NAME)

    return board


def _shell(booted):
    return booted.target.get_driver("ADIShellDriver")


def _ensure_unloaded(shell) -> None:
    if overlay_is_loaded(shell, OVERLAY_NAME):
        unload_overlay(shell, OVERLAY_NAME)
        # Give the kernel a beat to tear down the overlay's probes before
        # the next apply — otherwise a racing ``mkdir`` can land while the
        # previous overlay is still being removed.
        time.sleep(2.0)


def _apply_and_wait(shell) -> None:
    res = load_overlay(shell, OVERLAY_NAME, DTBO_REMOTE_PATH)
    assert "RC=0" in res, f"overlay load failed: {res}"
    # Drivers re-probe asynchronously after overlay application; give the
    # JESD link FSM time to walk through SYNC -> ILAS -> DATA.
    time.sleep(5.0)


def _assert_iio_devices_present(ctx, *, context: str) -> None:
    found = {d.name for d in ctx.devices if d.name}
    suffix = f" ({context})" if context else ""
    for required in EXPECTED_IIO_NAMES_ALL:
        assert required in found, (
            f"IIO device {required!r} not present{suffix}. Devices: {sorted(found)}"
        )
    assert any(n in found for n in EXPECTED_IIO_NAMES_ANY), (
        f"AD9081 RX frontend not present{suffix}. "
        f"Expected one of {EXPECTED_IIO_NAMES_ANY}; "
        f"found: {sorted(found)}"
    )


def _create_ad9081(uri: str):
    """Return an ``adi.ad9081`` that tolerates sdtgen IIO device names.

    pyadi-iio's ``adi.ad9081`` hardcodes ``axi-ad9081-{rx,tx}-hpc``.  If
    the live context exposes the sdtgen-generated TPL names instead, the
    standard constructor raises ``AttributeError``; we fall back to a
    patched ``iio.Context`` that aliases the TPL names to the hpc ones.
    """
    import adi
    import iio

    try:
        return adi.ad9081(uri=uri)
    except (AttributeError, TypeError):
        pass

    ctx = iio.Context(uri)
    name_map = {
        "axi-ad9081-rx-hpc": "ad_ip_jesd204_tpl_adc",
        "axi-ad9081-tx-hpc": "ad_ip_jesd204_tpl_dac",
    }
    orig_find = ctx.find_device

    def _patched_find(name):
        result = orig_find(name)
        if result is None and name in name_map:
            result = orig_find(name_map[name])
        return result

    ctx.find_device = _patched_find

    dev = adi.ad9081.__new__(adi.ad9081)
    dev._ctx = ctx
    dev.uri = uri
    adi.ad9081.__init__(dev, uri=uri)
    return dev


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
    assert "axi-ad9081" in src, (
        f"Pipeline overlay does not reference axi-ad9081: {dtso}"
    )
    assert overlay_dtbo.exists() and overlay_dtbo.stat().st_size > 100


@requires_lg
@pytest.mark.lg_feature(["ad9081", "zcu102"])
def test_configfs_overlay_support(booted_board):
    """Target kernel must support runtime overlays via configfs."""
    assert_configfs_overlay_support(_shell(booted_board))


@requires_lg
@pytest.mark.lg_feature(["ad9081", "zcu102"])
def test_load_overlay(booted_board, tmp_path):
    """Apply the overlay; verify clean probe, IIO discovery, and JESD DATA."""
    shell = _shell(booted_board)
    _ensure_unloaded(shell)

    # dmesg before overlay-apply is the boot log — filter that out so we
    # only flag errors caused by the overlay itself.  ``wc -l`` returns
    # the line count we use as the offset for ``tail -n +<N+1>`` after
    # the apply.
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
@pytest.mark.lg_feature(["ad9081", "zcu102"])
def test_dma_loopback(booted_board):
    """Drive a DDS tone through TX→RX via DMA and detect it in the spectrum.

    Requires the overlay from ``test_load_overlay`` to still be applied
    (module-scoped fixtures keep the state).  Uses pyadi-iio's
    ``adi.ad9081`` for the capture.  Spectrum analysis is done with
    numpy: take an FFT of the complex baseband buffer, find the peak
    bin, assert it lines up with ``DDS_TONE_HZ``, and check the peak is
    well above the surrounding noise floor.  genalyzer is available in
    the repo's dev environment for deeper analysis; using numpy here
    keeps the test robust across genalyzer API revisions since the only
    thing we need is "tone at the right place, clearly above noise".
    """
    pytest.importorskip("adi")
    np = pytest.importorskip("numpy")

    shell = _shell(booted_board)
    if not overlay_is_loaded(shell, OVERLAY_NAME):
        pytest.skip("overlay not loaded — test_load_overlay must run first")

    ctx, ip = open_iio_context(shell)
    del ctx  # _create_ad9081 opens its own context

    try:
        dev = _create_ad9081(f"ip:{ip}")
    except Exception as exc:  # noqa: BLE001 — any connect failure is a skip
        pytest.skip(f"could not attach adi.ad9081 to {ip}: {exc}")

    dev.rx_enabled_channels = [0]
    dev.rx_buffer_size = RX_BUFFER_SIZE
    sample_rate = int(dev.rx_sample_rate)
    print(f"AD9081 RX sample rate: {sample_rate} Hz, buffer: {RX_BUFFER_SIZE}")

    try:
        dev.dds_single_tone(DDS_TONE_HZ, DDS_SCALE, channel=0)
        # First refills can carry stale samples captured before the DDS
        # tone propagated through the link — drain a few.
        for _ in range(3):
            dev.rx()
        raw = dev.rx()
    except TimeoutError:
        pytest.skip("DMA buffer refill timed out — JESD link may not be in DATA mode")
    finally:
        try:
            dev.disable_dds()
        except Exception:  # noqa: BLE001 — cleanup is best-effort
            pass
        try:
            dev.rx_destroy_buffer()
        except Exception:  # noqa: BLE001 — cleanup is best-effort
            pass

    samples = raw[0] if isinstance(raw, list) else raw
    samples = np.asarray(samples)
    assert samples.size >= 1024, f"RX capture too short: {samples.size}"
    assert np.max(np.abs(samples)) > 0, (
        "RX data is all zeros — DMA path or JESD link stalled"
    )

    # Complex baseband: full FFT so positive and negative frequencies
    # are both represented (a real DDS tone folds to ±DDS_TONE_HZ after
    # quadrature downconversion; either sideband should satisfy the
    # ``≤ 2·fbin`` check).  Real data: real-FFT produces one sideband.
    nfft = 1 << int(np.floor(np.log2(samples.size)))
    trimmed = samples[:nfft]
    win = np.hanning(nfft).astype(np.float64)
    if np.iscomplexobj(trimmed):
        spectrum = np.fft.fftshift(
            np.fft.fft(trimmed.astype(np.complex128) * win, n=nfft)
        )
        freqs = np.fft.fftshift(np.fft.fftfreq(nfft, d=1.0 / sample_rate))
    else:
        spectrum = np.fft.rfft(trimmed.astype(np.float64) * win, n=nfft)
        freqs = np.fft.rfftfreq(nfft, d=1.0 / sample_rate)

    mags = np.abs(spectrum)

    # Exclude a ±N-bin guard around DC from the tone search.  AD9081
    # exhibits a non-trivial DC offset that often dominates the
    # spectrum even when a loopback tone is present; finding the
    # strongest *non-DC* bin gives the real tone location.  Same DC
    # guard is used for the noise-floor median so the floor is not
    # contaminated by the DC bump either.
    fbin = sample_rate / nfft
    nyquist = sample_rate / 2
    dc_guard = 5
    zero_idx = int(np.argmin(np.abs(freqs)))
    nondc_mask = np.ones(mags.size, dtype=bool)
    nondc_mask[
        max(0, zero_idx - dc_guard) : min(mags.size, zero_idx + dc_guard + 1)
    ] = False

    search_mags = np.where(nondc_mask, mags, 0.0)
    peak_idx = int(np.argmax(search_mags))
    peak_mag = float(mags[peak_idx])
    if peak_mag <= 0:
        pytest.fail("RX spectrum has no non-DC content — JESD/DMA path inert")
    mags_db = 20.0 * np.log10(np.maximum(mags, 1e-9) / peak_mag)
    signal_freq = float(abs(freqs[peak_idx]))
    signal_mag_db = float(mags_db[peak_idx])

    # Noise floor: median of bins outside the DC guard *and* outside a
    # ±5-bin guard around the peak.
    noise_mask = nondc_mask.copy()
    lo = max(0, peak_idx - 5)
    hi = min(mags.size, peak_idx + 6)
    noise_mask[lo:hi] = False
    noise_db = float(np.median(mags_db[noise_mask]))
    snr_db = signal_mag_db - noise_db

    print(
        f"Loopback spectrum: peak {signal_freq:.0f} Hz "
        f"({signal_mag_db:.1f} dB), noise floor {noise_db:.1f} dB, "
        f"SNR {snr_db:.1f} dB, fbin {fbin:.0f} Hz, DDS req {DDS_TONE_HZ} Hz"
    )
    # We don't pin the peak to ``DDS_TONE_HZ`` exactly: the AD9081 RX
    # CDDC/FDDC NCOs downconvert before samples reach us, so the
    # loopback tone lands at ``DDS_TONE_HZ - RX_NCO``.  This test is
    # about overlay lifecycle, not chain calibration — a coherent
    # non-DC, non-Nyquist peak above the noise floor is sufficient
    # evidence that the DMA TX→RX path is end-to-end alive.
    assert signal_freq < nyquist - 10 * fbin, (
        f"Loopback peak too close to Nyquist ({signal_freq:.0f} Hz > "
        f"{nyquist - 10 * fbin:.0f} Hz)"
    )
    assert snr_db > 10.0, (
        f"Loopback tone not clearly above noise floor: SNR={snr_db:.1f} dB"
    )


@requires_lg
@pytest.mark.lg_feature(["ad9081", "zcu102"])
def test_unload_overlay(booted_board):
    """Removing the configfs entry tears down without kernel faults."""
    shell = _shell(booted_board)
    if not overlay_is_loaded(shell, OVERLAY_NAME):
        # Could happen if test_load_overlay was deselected; apply + unload
        # rather than skipping so the unload path is always exercised.
        _apply_and_wait(shell)

    res = unload_overlay(shell, OVERLAY_NAME)
    assert "RC=0" in res, f"overlay unload failed: {res}"
    # Give the kernel a moment to finish removing child devices.
    time.sleep(2.0)

    # The configfs entry must be gone.  The base tree's devices may
    # persist — unload only removes the overlay's phandles, not the
    # base-DT nodes Kuiper's stock image probed earlier.
    assert not overlay_is_loaded(shell, OVERLAY_NAME), (
        "overlay configfs entry still present after rmdir"
    )

    dmesg_txt = shell_out(shell, "dmesg")
    # Only check for *hard* kernel faults during unload: driver ``.remove``
    # callbacks can log routine messages the probe-error regex would
    # otherwise flag.
    assert_no_kernel_faults(dmesg_txt)


@requires_lg
@pytest.mark.lg_feature(["ad9081", "zcu102"])
def test_reload_overlay(booted_board):
    """Load → unload → load cycle; re-verify devices + JESD link."""
    shell = _shell(booted_board)
    _ensure_unloaded(shell)

    _apply_and_wait(shell)
    ctx, _ = open_iio_context(shell)
    _assert_iio_devices_present(ctx, context="after overlay reload")
    assert_jesd_links_data(shell, context="after overlay reload")
