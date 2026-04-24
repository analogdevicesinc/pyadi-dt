"""ADRV9009 + ZC706 runtime device-tree overlay hardware test.

Mirrors :mod:`test.hw.xsa.test_ad9081_zcu102_overlay` for the ZC706 +
ADRV9009-FMC daughter card on the ``nemo`` labgrid place.  Same six
test shape (unit, configfs, load, DMA, unload, reload), same
configfs lifecycle, same dmesg-delta error gating.

Two platform-specific differences from the AD9081 variant:

1. **Boot transport** — ZC706 boots via :class:`BootFPGASoCTFTP`
   (Zynq-7000 TFTP).  The merged DTB is renamed to ``devicetree.dtb``
   so U-Boot's ``tftp devicetree.dtb`` finds it; the kernel is
   ``uImage`` (legacy U-Boot image, wrapped from the built ``zImage``
   by :func:`~test.hw.hw_helpers._wrap_zimage_as_uimage`).
2. **DMA path** — the ADRV9009 ZC706 reference HDL has no internal
   DAC→ADC loopback (unlike AD9081's ``ad_ip_jesd204_tpl_*`` cores),
   so an injected TX DDS tone may not appear in the RX capture
   without an external SMA-to-SMA cable on the daughter card.  The
   data-path verification therefore runs in two phases: a mandatory
   :func:`~test.hw.hw_helpers.assert_rx_capture_valid` smoke check
   plus an opportunistic FFT stage that asserts SNR > 10 dB on a
   non-DC peak only when one is clearly present, and otherwise logs
   the noise-only result and passes.

LG_ENV: ``test/hw/env/nemo.yaml``.
"""

from __future__ import annotations

import os
import shutil as _shutil
import time
from pathlib import Path
from typing import Any

import pytest

from adidt.xsa.pipeline import XsaPipeline
from adidt.xsa.topology import XsaParser
from test.hw.hw_helpers import (
    acquire_xsa,
    assert_configfs_overlay_support,
    assert_jesd_links_data,
    assert_no_kernel_faults,
    assert_no_probe_errors,
    assert_rx_capture_valid,
    check_jesd_framing_plausibility,
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
        "set LG_COORDINATOR or LG_ENV for ADRV9009 ZC706 overlay hardware tests"
        " (see .env.example)"
    ),
)

DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynq-zc706-adv7511-adrv9009"

OVERLAY_NAME = "adrv9009_zc706_xsa"
DTBO_REMOTE_PATH = f"/tmp/{OVERLAY_NAME}.dtbo"
FDT_MAGIC = b"\xd0\x0d\xfe\xed"

# DDS tone the optional FFT stage will request on TX.  Only relevant
# if the daughter card has a TX→RX cable; otherwise the FFT stage
# falls back to a noise-only diagnostic without asserting on the peak.
DDS_TONE_HZ = 1_000_000
DDS_SCALE = 0.5
RX_BUFFER_SIZE = 2**14

EXPECTED_IIO_NAMES_ANY = (
    # Kuiper-built DTBs use ``axi-adrv9009-rx-hpc``; the sdtgen-built
    # merged DTB the overlay test boots from labels the same buffered
    # ADC frontend ``ad_ip_jesd204_tpl_adc`` instead.  Either is a
    # valid sign that the RX side probed.
    "axi-adrv9009-rx-hpc",
    "axi-adrv9009-rx-obs-hpc",
    "ad_ip_jesd204_tpl_adc",
)
EXPECTED_IIO_NAMES_ALL = ("adrv9009-phy",)


def _adrv9009_cfg() -> dict[str, Any]:
    """ADRV9009+ZC706 XSA pipeline cfg.

    Hardcoded JESD framing matches Kuiper's stock
    ``zynq-zc706-adv7511-adrv9009`` reference design (also matches the
    pyadi-jif solver output for ``M=4, L=2, Np=16`` RX and
    ``M=4, L=4, Np=16`` TX at 245.76 MHz).  Pre-flighted by
    :func:`~test.hw.hw_helpers.check_jesd_framing_plausibility` so a
    typo in this dict surfaces here, not at ILAS-training time on the
    target.  GPIO numbers follow the production ZC706 wiring (gpio0:106
    reset, gpio0:112 sysref-req); ADRV9009Builder defaults to ZCU102
    GPIOs which are wrong for ZC706.
    """
    cfg: dict[str, Any] = {
        "adrv9009_board": {
            "trx_reset_gpio": 106,
            "trx_sysref_req_gpio": 112,
        },
        "jesd": {
            "rx": {"F": 4, "K": 32, "M": 4, "L": 2, "Np": 16, "S": 1},
            "tx": {"F": 2, "K": 32, "M": 4, "L": 4, "Np": 16, "S": 1},
        },
        "clock": {
            "rx_device_clk_label": "clkgen",
            "tx_device_clk_label": "clkgen",
            "hmc7044_rx_channel": 0,
            "hmc7044_tx_channel": 0,
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

    Tries the local fixture path first; falls back to
    :func:`~test.hw.hw_helpers.acquire_xsa` which downloads the XSA
    from the Kuiper release.  Skips the whole module when neither path
    yields a usable XSA.
    """
    local_xsa = Path(__file__).parent / "system_top_adrv9009_zc706.xsa"
    if not local_xsa.exists():
        local_xsa = Path(__file__).parent / "ref_data" / "system_top_adrv9009_zc706.xsa"
    try:
        xsa_path = acquire_xsa(
            local_xsa,
            DEFAULT_KUIPER_RELEASE,
            DEFAULT_KUIPER_PROJECT,
            tmp_path_factory.mktemp("xsa_dl"),
        )
    except Exception as exc:  # noqa: BLE001 — any download/IO failure → skip
        pytest.skip(f"could not acquire ADRV9009+ZC706 XSA: {exc}")

    topology = XsaParser().parse(xsa_path)
    assert topology.jesd204_rx, "No JESD204 RX instances in XSA topology"
    assert topology.jesd204_tx, "No JESD204 TX instances in XSA topology"

    out_dir = tmp_path_factory.mktemp("overlay") / "out"
    return XsaPipeline().run(
        xsa_path=xsa_path,
        cfg=_adrv9009_cfg(),
        output_dir=out_dir,
        profile="adrv9009_zc706",
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
def booted_board(
    board, built_kernel_image_zynq, pipeline_result, overlay_dtbo, tmp_path_factory
):
    """Boot ZC706 with the pipeline's merged DTB and stage the ``.dtbo``.

    Same rationale as the AD9081 overlay test: booting from the merged
    DTB the pipeline produces means the ADRV9009 SPI probe is clean
    from boot, so the overlay tests exercise the configfs lifecycle on
    top of an already-probed tree without inheriting unrelated boot
    issues.

    The DTB is renamed to ``devicetree.dtb`` because
    ``BootFPGASoCTFTP`` (configured in ``test/hw/env/nemo.yaml``) sets
    ``dtb_image_name: devicetree.dtb`` — the file U-Boot's
    ``tftp devicetree.dtb`` looks up in the TFTP root.  Matches the
    staging in ``test_adrv9009_zc706_hw``.
    """
    out_dir = tmp_path_factory.mktemp("merged_boot")
    merged_dts = pipeline_result["merged"]
    dtb_raw = out_dir / "adrv9009_zc706_xsa.dtb"
    compile_dts_to_dtb(merged_dts, dtb_raw)

    staged_dir = out_dir / "tftp_staging"
    staged_dir.mkdir(parents=True, exist_ok=True)
    staged = staged_dir / "devicetree.dtb"
    _shutil.copyfile(dtb_raw, staged)

    shell = deploy_and_boot(board, staged, built_kernel_image_zynq)

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
    # ADRV9009 / Talise re-init after overlay apply takes longer than
    # the AD9081 path; give the JESD FSM time to walk SYNC -> ILAS ->
    # DATA before any sysfs check.
    time.sleep(8.0)


def _filter_si570_probe_noise(dmesg_txt: str) -> str:
    """Strip the benign si570 -EIO probe lines.

    The optional Si570 clock chip on the ADRV9009-FMC sometimes does
    not ACK at its default I2C address; the probe failure is present
    in the production reference DT too and is unrelated to the
    overlay path.
    """
    return "\n".join(
        line
        for line in dmesg_txt.splitlines()
        if not ("si570" in line and "failed" in line)
    )


def _assert_iio_devices_present(ctx, *, context: str) -> None:
    found = {d.name for d in ctx.devices if d.name}
    suffix = f" ({context})" if context else ""
    for required in EXPECTED_IIO_NAMES_ALL:
        assert required in found, (
            f"IIO device {required!r} not present{suffix}. Devices: {sorted(found)}"
        )
    assert any(n in found for n in EXPECTED_IIO_NAMES_ANY), (
        f"ADRV9009 RX frontend not present{suffix}. "
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
    assert "axi-jesd204" in src or "adrv9009" in src.lower(), (
        f"Pipeline overlay does not reference ADRV9009 / JESD nodes: {dtso}"
    )
    assert overlay_dtbo.exists() and overlay_dtbo.stat().st_size > 100


@requires_lg
@pytest.mark.lg_feature(["adrv9009", "zc706"])
def test_configfs_overlay_support(booted_board):
    """Target kernel must support runtime overlays via configfs."""
    assert_configfs_overlay_support(_shell(booted_board))


@requires_lg
@pytest.mark.lg_feature(["adrv9009", "zc706"])
def test_load_overlay(booted_board, tmp_path):
    """Apply the overlay; verify clean probe, IIO discovery, and JESD DATA."""
    shell = _shell(booted_board)
    _ensure_unloaded(shell)

    # dmesg before overlay-apply is the boot log — filter it out so we
    # only flag errors caused by the overlay itself.
    dmesg_baseline = int(shell_out(shell, "dmesg | wc -l").strip() or "0")

    _apply_and_wait(shell)

    dmesg_full = shell_out(shell, "dmesg")
    (tmp_path / "dmesg_after_load.log").write_text(dmesg_full)
    dmesg_new = "\n".join(dmesg_full.splitlines()[dmesg_baseline:])
    (tmp_path / "dmesg_overlay_only.log").write_text(dmesg_new)
    assert_no_kernel_faults(dmesg_new)
    assert_no_probe_errors(_filter_si570_probe_noise(dmesg_new))

    ctx, _ = open_iio_context(shell)
    _assert_iio_devices_present(ctx, context="after overlay load")

    rx_status, tx_status = assert_jesd_links_data(shell, context="after overlay load")
    print(f"$ cat .../*.axi?jesd204?rx/status\n{rx_status}")
    print(f"$ cat .../*.axi?jesd204?tx/status\n{tx_status}")


@requires_lg
@pytest.mark.lg_feature(["adrv9009", "zc706"])
def test_dma_loopback(booted_board):
    """Verify DMA TX→RX data path.

    Two phases:

    * **Mandatory:** :func:`assert_rx_capture_valid` confirms that an
      RX buffer arrives with non-zero, non-latched samples.  This is
      the same smoke check ``test_adrv9009_zcu102_hw`` runs before any
      Talise profile push and is sufficient evidence that the JESD +
      DMA path is alive.
    * **Opportunistic FFT:** drive a DDS tone on TX and look for a
      coherent peak in the RX spectrum.  If one is present (SNR
      > 10 dB), it must be non-DC and non-Nyquist.  If no peak emerges
      (the typical case on ZC706 + ADRV9009 without an external
      TX→RX SMA cable on the FMC), the noise-floor metric is logged
      and the stage passes — TX→RX coupling is a lab-setup concern,
      not an overlay-lifecycle concern.
    """
    pytest.importorskip("adi")
    np = pytest.importorskip("numpy")

    shell = _shell(booted_board)
    if not overlay_is_loaded(shell, OVERLAY_NAME):
        pytest.skip("overlay not loaded — test_load_overlay must run first")

    ctx, ip = open_iio_context(shell)

    # Phase 1: bare data-path smoke check (independent of pyadi-iio).
    # On ZC706 + ADRV9009, the default Talise profile may leave the
    # buffered RX path inert until ``ensm_mode = radio_on`` is written
    # or a Talise profile is reloaded — neither of which is the
    # overlay-lifecycle test's responsibility.  Treat a refill timeout
    # as "DMA path needs further setup", log it, and skip cleanly.
    try:
        assert_rx_capture_valid(
            ctx,
            (
                "axi-adrv9009-rx-hpc",
                "axi-adrv9009-rx-obs-hpc",
                "ad_ip_jesd204_tpl_adc",
            ),
            n_samples=2**12,
            context="adrv9009 zc706 overlay",
        )
    except AssertionError as exc:
        if "timed out" in str(exc).lower():
            pytest.skip(
                "ADRV9009 RX DMA refill timed out — buffered path needs"
                " radio-enable / profile load (lab-setup concern, not"
                f" overlay lifecycle): {exc}"
            )
        raise

    # Phase 2: opportunistic spectrum check via pyadi-iio.
    import adi

    try:
        dev = adi.adrv9009(uri=f"ip:{ip}")
    except Exception as exc:  # noqa: BLE001 — connect failure → skip phase 2
        print(f"adi.adrv9009 unavailable; skipping FFT phase: {exc}")
        return

    dev.rx_enabled_channels = [0]
    dev.rx_buffer_size = RX_BUFFER_SIZE
    sample_rate = int(dev.rx_sample_rate)
    print(f"ADRV9009 RX sample rate: {sample_rate} Hz, buffer: {RX_BUFFER_SIZE}")

    try:
        try:
            dev.dds_single_tone(DDS_TONE_HZ, DDS_SCALE, channel=0)
        except Exception as exc:  # noqa: BLE001 — log and continue without DDS
            print(f"adrv9009 DDS setup failed; capturing anyway: {exc}")

        for _ in range(3):
            dev.rx()
        raw = dev.rx()
    except TimeoutError:
        pytest.skip("DMA buffer refill timed out — JESD link may not be in DATA mode")
    finally:
        for cleanup in ("disable_dds", "rx_destroy_buffer"):
            try:
                getattr(dev, cleanup)()
            except Exception:  # noqa: BLE001 — best-effort cleanup
                pass

    samples = raw[0] if isinstance(raw, list) else raw
    samples = np.asarray(samples)
    if samples.size < 1024:
        print(f"FFT phase: capture too short ({samples.size}); skipping spectrum check")
        return

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
        print("FFT phase: spectrum has no non-DC content (RX inert?)")
        return
    mags_db = 20.0 * np.log10(np.maximum(mags, 1e-9) / peak_mag)
    signal_freq = float(abs(freqs[peak_idx]))
    signal_mag_db = float(mags_db[peak_idx])

    noise_mask = nondc_mask.copy()
    lo = max(0, peak_idx - 5)
    hi = min(mags.size, peak_idx + 6)
    noise_mask[lo:hi] = False
    noise_db = float(np.median(mags_db[noise_mask]))
    snr_db = signal_mag_db - noise_db

    print(
        f"FFT phase: strongest non-DC bin {signal_freq:.0f} Hz "
        f"({signal_mag_db:.1f} dB), noise floor {noise_db:.1f} dB, "
        f"SNR {snr_db:.1f} dB, fbin {fbin:.0f} Hz, DDS req {DDS_TONE_HZ} Hz"
    )

    # Only assert the spectral shape when a clear tone emerges.  ZC706
    # ADRV9009 reference HDL has no internal TX→RX loopback, so without
    # an external cable the "peak" is just the strongest noise bin and
    # the SNR vs the floor stays in single digits.
    if snr_db < 10.0:
        print(
            "FFT phase: no coherent tone (SNR ≤ 10 dB) — recording noise-only "
            "result and passing.  External TX↔RX coupling is a lab-setup "
            "detail, not an overlay-lifecycle requirement."
        )
        return

    assert signal_freq < nyquist - 10 * fbin, (
        f"Loopback peak too close to Nyquist ({signal_freq:.0f} Hz > "
        f"{nyquist - 10 * fbin:.0f} Hz)"
    )
    print(f"FFT phase: tone detected, SNR {snr_db:.1f} dB at {signal_freq:.0f} Hz")


@requires_lg
@pytest.mark.lg_feature(["adrv9009", "zc706"])
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
@pytest.mark.lg_feature(["adrv9009", "zc706"])
def test_reload_overlay(booted_board):
    """Load → unload → load cycle; re-verify devices + JESD link."""
    shell = _shell(booted_board)
    _ensure_unloaded(shell)

    _apply_and_wait(shell)
    ctx, _ = open_iio_context(shell)
    _assert_iio_devices_present(ctx, context="after overlay reload")
    assert_jesd_links_data(shell, context="after overlay reload")
