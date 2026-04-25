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
2. **DMA path** — the default post-boot Talise state on ZC706 +
   ADRV9009 leaves buffered RX inert.  The DMA test pushes a
   canonical iio-oscilloscope ``DC245p76`` Talise profile via
   ``adrv9009-phy.profile_config`` first; that re-inits the radio
   to ``radio_on`` without changing the JESD lane rate.  The
   ADRV9009 ZC706 reference HDL has no internal DAC→ADC loopback
   (unlike AD9081's ``ad_ip_jesd204_tpl_*`` cores), so a TX DDS tone
   may not appear in the RX capture without an external SMA-to-SMA
   cable on the daughter card.  The FFT stage asserts SNR > 10 dB
   on a non-DC peak only when one is clearly present and otherwise
   logs the noise-only result and passes.

LG_ENV: ``test/hw/env/nemo.yaml``.
"""

from __future__ import annotations

import base64
import os
import shutil as _shutil
import time
import urllib.request
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

# Smallest of the canonical Talise filter profiles iio-oscilloscope
# ships.  All four use ``deviceClock=245.76 MHz`` (matches our cfg's
# 245.76 MHz device clock), so pushing this profile re-initialises the
# Talise radio to a state where buffered RX is enabled without
# changing the JESD lane rate.  ``test_adrv9009_zcu102_hw`` uses the
# same source URL.
TALISE_PROFILE_URL = (
    "https://raw.githubusercontent.com/analogdevicesinc/iio-oscilloscope/"
    "main/filters/adrv9009/"
    "Tx_BW100_IR122p88_Rx_BW100_OR122p88_ORx_BW100_OR122p88_DC245p76.txt"
)

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


def _load_talise_profile(shell, cache_dir: Path) -> bool:
    """Push a Talise filter profile to ``adrv9009-phy.profile_config``.

    On ZC706 + ADRV9009 the default post-boot Talise state leaves the
    buffered RX path inert (unlike ZCU102 where the default profile
    is RX-capable).  Pushing any profile triggers a Talise re-init
    that brings the radio up to ``radio_on``, after which DMA
    capture works.  Returns ``True`` if the profile was applied,
    ``False`` if the sysfs ``profile_config`` node could not be
    located (e.g. driver build without debugfs support).
    """
    profile_sysfs = shell_out(
        shell,
        "find /sys/kernel/debug/iio /sys/bus/iio/devices "
        "-name profile_config 2>/dev/null | head -1",
    ).strip()
    if not profile_sysfs:
        profile_sysfs = shell_out(
            shell,
            "find /sys -name profile_config 2>/dev/null | head -1",
        ).strip()
    if not profile_sysfs:
        return False

    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / "talise_default.txt"
    if cached.exists() and cached.stat().st_size > 0:
        body = cached.read_text()
    else:
        with urllib.request.urlopen(TALISE_PROFILE_URL, timeout=30) as resp:  # noqa: S310
            body = resp.read().decode("utf-8")
        cached.write_text(body)
    if not body.lstrip().startswith("<profile "):
        raise AssertionError(
            "Talise profile fetch returned non-XML content"
            f" (first 80 chars: {body[:80]!r})"
        )

    b64 = base64.b64encode(body.encode()).decode()
    shell_out(shell, f"printf '%s' '{b64}' | base64 -d > /tmp/talise.txt")
    size_on_target = shell_out(shell, "stat -c%s /tmp/talise.txt").strip()
    assert size_on_target == str(len(body.encode())), (
        f"Talise profile partial push: target has {size_on_target},"
        f" expected {len(body.encode())}"
    )
    shell_out(shell, f"cat /tmp/talise.txt > {profile_sysfs}")
    # Talise re-init re-runs the JESD bring-up sequence; give the FSM
    # time to relock both links before any sysfs check.
    time.sleep(3.0)

    # Profile push leaves the radio in ``calibrated`` (ENSM state 6) on
    # ZC706 builds — we need ``radio_on`` (state 7) before the buffered
    # RX path will deliver samples through DMA.  ensm_mode is exposed
    # at the adrv9009-phy IIO device level (sibling to profile_config).
    phy_dir = profile_sysfs.rsplit("/", 1)[0]
    shell_out(shell, f"echo radio_on > {phy_dir}/ensm_mode")
    time.sleep(1.0)
    return True


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
def test_dma_loopback(booted_board, tmp_path):
    """Verify DMA TX→RX data path.

    Setup: push a single Talise filter profile to wake the radio.
    The default post-boot Talise state on ZC706 + ADRV9009 leaves
    buffered RX inert; pushing any DC-245.76 MHz profile re-inits
    the chip into ``radio_on`` without changing the JESD lane rate.

    Two verification phases:

    * **Mandatory:** :func:`assert_rx_capture_valid` confirms that an
      RX buffer arrives with non-zero, non-latched samples.  Same
      smoke check ``test_adrv9009_zcu102_hw`` runs.
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

    profile_loaded = _load_talise_profile(shell, tmp_path / "talise_cache")
    if profile_loaded:
        # Talise re-init walks JESD through SYNC → ILAS → DATA again.
        assert_jesd_links_data(shell, context="after Talise profile push")
    else:
        print(
            "Talise profile_config sysfs not found — proceeding with"
            " default post-boot Talise state"
        )

    ctx, ip = open_iio_context(shell)

    # Phase 1: bare data-path smoke check.
    #
    # Both the RX TPL (``...@44a00000``) and the OBS TPL
    # (``...@44a08000``) probe to libiio with the same of_node
    # name ``ad_ip_jesd204_tpl_adc`` — their unit-names are
    # identical in the sdtgen-built DTB.  ``find_device`` returns
    # whichever probed first (typically OBS via ``ad_adc.c``,
    # before cf_axi_adc binds the RX TPL).  Talise's ``radio_on``
    # streams framer-A (RX); framer-B (OBS) stays gated, so a
    # refill on the OBS device returns all zeros even though the
    # OBS DMA fires its done IRQ.  Prefer the RX TPL by reg
    # address so we exercise the path ``radio_on`` actually
    # enables.
    rx_tpl_dev = None
    for d in ctx.devices:
        if d.name != "ad_ip_jesd204_tpl_adc":
            continue
        try:
            of_node = d.attrs["of_node"].value if "of_node" in d.attrs else ""
        except Exception:  # noqa: BLE001 — attr read may raise on some builds
            of_node = ""
        if "44a00000" in of_node:
            rx_tpl_dev = d
            break
    if rx_tpl_dev is None:
        # ``of_node`` isn't always exposed as an IIO attr; fall back
        # to the higher-numbered duplicate.  cf_axi_adc binds the RX
        # TPL after ``ad_adc`` binds OBS, so the RX iio:device has
        # the larger numeric id.
        candidates = [d for d in ctx.devices if d.name == "ad_ip_jesd204_tpl_adc"]
        if candidates:
            rx_tpl_dev = max(candidates, key=lambda d: int(d.id.rsplit(":device", 1)[1]))

    target_names: tuple[str, ...] = (
        "axi-adrv9009-rx-hpc",
        "axi-adrv9009-rx-obs-hpc",
        "ad_ip_jesd204_tpl_adc",
    )
    if rx_tpl_dev is not None:
        target_names = (rx_tpl_dev.id,)

    try:
        assert_rx_capture_valid(
            ctx,
            target_names,
            n_samples=2**12,
            context="adrv9009 zc706 overlay",
        )
    except AssertionError:
        # On-target diagnostics: IRQ counts disambiguate
        # DMA-not-firing from JESD-not-streaming for the next
        # round of debugging.
        print("=== /proc/interrupts ===")
        print(shell_out(shell, "cat /proc/interrupts"))
        print("=== dmesg tail ===")
        print(shell_out(shell, "dmesg | tail -n 60"))
        raise

    # Phase 2: opportunistic spectrum check via pyadi-iio.
    #
    # ``pyadi-iio`` looks up the buffered ADC by the production
    # name ``axi-adrv9009-rx-hpc``.  Our merged DTB names the same
    # node ``ad_ip_jesd204_tpl_adc`` (sdtgen unit-name), so the
    # ``adi.adrv9009`` constructor returns an object with
    # ``_rxadc = None`` instead of raising — every subsequent
    # ``dev.rx_*`` access then crashes with ``AttributeError``.
    # Detect that state up front and skip; Phase 1 already
    # validated the data path.
    import adi

    try:
        dev = adi.adrv9009(uri=f"ip:{ip}")
    except Exception as exc:  # noqa: BLE001 — connect failure → skip phase 2
        print(f"adi.adrv9009 unavailable; skipping FFT phase: {exc}")
        return
    if getattr(dev, "_rxadc", None) is None:
        print(
            "adi.adrv9009 missing 'axi-adrv9009-rx-hpc' IIO name "
            "(merged DTB exposes 'ad_ip_jesd204_tpl_adc' instead) — "
            "skipping FFT phase; Phase 1 already validated the data path."
        )
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
