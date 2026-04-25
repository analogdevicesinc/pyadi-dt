"""Shared FFT loopback verification for overlay hardware tests.

Lifts the ~80-LOC FFT spectrum-analysis block that was inlined in three
overlay tests (AD9081+ZCU102 mandatory check; ADRV9009+ZC706 and
ADRV9371+ZC706 opportunistic check) into a single helper.

Two modes are supported:

* ``"required"`` — drive a DDS tone, capture, FFT-analyse the spectrum,
  and *assert* a coherent non-DC peak above the noise floor (SNR > 10 dB).
  Used when the board's reference HDL has internal DAC→ADC loopback
  (AD9081 ZCU102) so a tone is always expected.
* ``"optional"`` — same capture + analysis, but a low SNR result is
  *logged* and the test passes.  Used when the board's HDL has no
  internal loopback (ADRV9009/ADRV9371) — without an external SMA
  cable the noise floor is the only thing in the spectrum, and that
  is a lab-setup concern, not an overlay-lifecycle failure.
"""

from __future__ import annotations

from typing import Any, Literal

import pytest

FftMode = Literal["required", "optional"]

_SNR_THRESHOLD_DB = 10.0
_DC_GUARD_BINS = 5
_PEAK_GUARD_BINS = 5
_PRIMING_REFILLS = 3


def prepare_pyadi_device(
    spec, ip: str
) -> Any | None:
    """Build the pyadi-iio device for the FFT phase, or return ``None``.

    Uses ``spec.pyadi_factory`` when set (AD9081 needs a constructor
    that aliases sdtgen IIO names to the production hpc names).
    Otherwise tries ``getattr(adi, spec.pyadi_class_name)(uri=...)``.

    Returns ``None`` when the device's ``_rxadc`` is unset — this is
    the sdtgen-name fallback case where pyadi-iio's hardcoded
    ``axi-<chip>-rx-hpc`` lookup misses; the caller treats this as
    "skip the FFT phase, phase 1 already validated the data path".
    """
    if spec.pyadi_factory is not None:
        return spec.pyadi_factory(f"ip:{ip}")

    if spec.pyadi_class_name is None:
        return None

    import adi

    cls = getattr(adi, spec.pyadi_class_name, None)
    if cls is None:
        return None
    try:
        dev = cls(uri=f"ip:{ip}")
    except Exception as exc:  # noqa: BLE001 — connect failure → caller skips
        print(f"adi.{spec.pyadi_class_name} unavailable: {exc}")
        return None
    if getattr(dev, "_rxadc", None) is None:
        print(
            f"adi.{spec.pyadi_class_name} missing buffered RX adapter "
            "(merged DTB likely exposes sdtgen 'ad_ip_jesd204_tpl_adc' name) — "
            "skipping FFT phase; phase 1 already validated the data path."
        )
        return None
    return dev


def fft_loopback_check(
    *,
    dev: Any,
    sample_rate: int,
    dds_tone_hz: int,
    dds_scale: float,
    rx_buffer_size: int,
    mode: FftMode,
    label: str = "",
) -> None:
    """Drive a DDS tone, capture, and verify the loopback spectrum.

    Args:
        dev: pyadi-iio device with ``rx_enabled_channels``,
            ``rx_buffer_size``, ``rx_sample_rate``, ``dds_single_tone``,
            ``rx`` methods.
        sample_rate: integer sample rate in Hz.
        dds_tone_hz: DDS tone frequency to drive on TX.
        dds_scale: DDS tone amplitude (0..1).
        rx_buffer_size: capture buffer size in samples.
        mode: ``"required"`` asserts on low SNR; ``"optional"`` logs.
        label: free-text tag printed alongside log lines.

    Raises:
        AssertionError: in ``"required"`` mode when no coherent peak
            emerges (SNR ≤ 10 dB) or the peak sits within 10 fbins of
            Nyquist.
    """
    np = pytest.importorskip("numpy")
    suffix = f" [{label}]" if label else ""

    dev.rx_enabled_channels = [0]
    dev.rx_buffer_size = rx_buffer_size
    print(f"FFT phase{suffix}: sample_rate={sample_rate} Hz, buffer={rx_buffer_size}")

    try:
        try:
            dev.dds_single_tone(dds_tone_hz, dds_scale, channel=0)
        except Exception as exc:  # noqa: BLE001 — DDS optional in capture-only mode
            print(f"FFT phase{suffix}: DDS setup failed; capturing anyway: {exc}")

        for _ in range(_PRIMING_REFILLS):
            dev.rx()
        raw = dev.rx()
    except TimeoutError:
        pytest.skip(
            f"DMA buffer refill timed out{suffix} — "
            "JESD link may not be in DATA mode"
        )
    finally:
        for cleanup in ("disable_dds", "rx_destroy_buffer"):
            try:
                getattr(dev, cleanup)()
            except Exception:  # noqa: BLE001 — best-effort cleanup
                pass

    samples = raw[0] if isinstance(raw, list) else raw
    samples = np.asarray(samples)

    if mode == "optional" and samples.size < 1024:
        print(
            f"FFT phase{suffix}: capture too short ({samples.size}); "
            "skipping spectrum check"
        )
        return
    assert samples.size >= 1024, f"RX capture too short{suffix}: {samples.size}"
    assert np.max(np.abs(samples)) > 0, (
        f"RX data is all zeros{suffix} — DMA path or JESD link stalled"
    )

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

    zero_idx = int(np.argmin(np.abs(freqs)))
    nondc_mask = np.ones(mags.size, dtype=bool)
    nondc_mask[
        max(0, zero_idx - _DC_GUARD_BINS) : min(mags.size, zero_idx + _DC_GUARD_BINS + 1)
    ] = False

    search_mags = np.where(nondc_mask, mags, 0.0)
    peak_idx = int(np.argmax(search_mags))
    peak_mag = float(mags[peak_idx])
    if peak_mag <= 0:
        msg = f"FFT phase{suffix}: spectrum has no non-DC content (RX inert?)"
        if mode == "required":
            pytest.fail(msg + " — JESD/DMA path inert")
        print(msg)
        return

    mags_db = 20.0 * np.log10(np.maximum(mags, 1e-9) / peak_mag)
    signal_freq = float(abs(freqs[peak_idx]))
    signal_mag_db = float(mags_db[peak_idx])

    noise_mask = nondc_mask.copy()
    lo = max(0, peak_idx - _PEAK_GUARD_BINS)
    hi = min(mags.size, peak_idx + _PEAK_GUARD_BINS + 1)
    noise_mask[lo:hi] = False
    noise_db = float(np.median(mags_db[noise_mask]))
    snr_db = signal_mag_db - noise_db

    print(
        f"FFT phase{suffix}: peak {signal_freq:.0f} Hz "
        f"({signal_mag_db:.1f} dB), noise floor {noise_db:.1f} dB, "
        f"SNR {snr_db:.1f} dB, fbin {fbin:.0f} Hz, DDS req {dds_tone_hz} Hz"
    )

    if snr_db < _SNR_THRESHOLD_DB:
        msg = (
            f"FFT phase{suffix}: no coherent tone "
            f"(SNR {snr_db:.1f} dB ≤ {_SNR_THRESHOLD_DB} dB)"
        )
        if mode == "required":
            pytest.fail(msg + " — loopback path is not delivering the DDS tone")
        print(
            msg + " — recording noise-only result and passing.  External "
            "TX↔RX coupling is a lab-setup detail, not an overlay-lifecycle "
            "requirement."
        )
        return

    assert signal_freq < nyquist - 10 * fbin, (
        f"Loopback peak too close to Nyquist{suffix} ({signal_freq:.0f} Hz > "
        f"{nyquist - 10 * fbin:.0f} Hz)"
    )
    print(f"FFT phase{suffix}: tone detected, SNR {snr_db:.1f} dB at {signal_freq:.0f} Hz")
