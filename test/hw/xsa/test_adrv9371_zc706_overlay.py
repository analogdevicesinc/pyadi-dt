"""ADRV9371 + ZC706 runtime device-tree overlay hardware test.

Mirrors :mod:`test.hw.xsa.test_adrv9009_zc706_overlay` for the ZC706 +
ADRV9371-FMC daughter card on the ``bq`` labgrid place.  Same six-test
shape (unit, configfs, load, DMA, unload, reload), same configfs
lifecycle, same dmesg-delta error gating.

Differences from the ADRV9009 variant:

1. **Profile transport** — ADRV9371 uses the Mykonos firmware
   architecture; the per-radio configuration is baked into the DT as
   ``adi,*-profile-*`` / ``adi,clocks-*`` properties on
   ``ad9371-phy@1`` at probe time (see ``adrv937x_zc706.json`` and
   :mod:`adidt.xsa.builders.adrv937x`).  There is no runtime
   ``profile_config`` sysfs equivalent, so the DMA test does not push
   a profile after overlay apply — the radio is already configured by
   the merged base DTB before the overlay is applied.
2. **DMA path** — ZC706 + ADRV9371 reference HDL has no internal
   DAC→ADC loopback, same as ADRV9009.  Phase 1 (mandatory) asserts
   non-zero, non-latched RX samples via :func:`assert_rx_capture_valid`.
   Phase 2 (opportunistic) computes an FFT to look for a coherent
   tone if a TX→RX SMA cable is wired on the FMC; absence of a peak
   is logged but not a failure.

Two distinct bring-up blockers were debugged and fixed during this
test's development against the ``release:zynq-zc706-adv7511-adrv937x``
bitstream that ``bq`` loads:

1. **ILAS framing mismatch** (``mismatch=0xc7f8``, 9 framing fields
   disagreeing) — the AD9371 deframer's "received-ILAS" registers
   were stale zeros because the FPGA TX framer never emitted a valid
   ILAS sequence.  Root cause: the TPL DAC core
   (``axi_ad9371_core_tx`` upstream) was missing from the JESD204
   topology graph, so ``cf_axi_dds_jesd204_post_running_stage`` /
   ``cf_axi_dds_start_sync`` never armed the DAC data path.  Fixed
   in ``adidt/xsa/builders/adrv937x.py`` ``tx_core_second`` block
   (adds ``jesd204-device`` / ``#jesd204-cells`` / ``jesd204-inputs``
   on the TPL DAC core) and the redirected ``trx_inputs_value``
   pointing the AD9371 phy at the TPL DAC core for its TX link.

2. **AXI DMAC IRQ number wrong in DT** — sdtgen extracted SPI 31/32
   from the XSA but the loaded bitstream actually wires the DMAC IRQ
   wires to SPI 57/56 (= GIC IRQ 89/88).  Confirmed on bq: DMAC
   ``TRANSFER_DONE`` incremented and ``GICD ICDISPR[2]`` had bit 25
   set (= IRQ 89 pending) while the DT-declared IRQ stayed at 0 in
   ``/proc/interrupts``.  Manually injecting IRQ 63 via
   ``GICD+0x204`` correctly fired the registered handler — proving
   the kernel's IRQ machinery worked, only the DT-declared IRQ
   number was wrong.  Fixed in the same builder by setting
   ``dma_interrupts_str`` on the RX/TX ``JesdLinkModel``s; the
   ``_render_dma_overlay`` then emits a ``/delete-property/
   interrupts;`` + ``interrupts = <0 57 4>`` (RX) / ``<0 56 4>``
   (TX) override matching the upstream Kuiper reference DT.

LG_ENV: ``test/hw/env/bq.yaml``.
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
    stage_dtb_as_devicetree,
    unload_overlay,
)

_HAS_LG = bool(os.environ.get("LG_COORDINATOR") or os.environ.get("LG_ENV"))
requires_lg = pytest.mark.skipif(
    not _HAS_LG,
    reason=(
        "set LG_COORDINATOR or LG_ENV for ADRV9371 ZC706 overlay hardware tests"
        " (see .env.example)"
    ),
)

DEFAULT_KUIPER_RELEASE = "2023_R2_P1"
DEFAULT_KUIPER_PROJECT = "zynq-zc706-adv7511-adrv937x"
DEFAULT_VCXO_HZ = 122_880_000

OVERLAY_NAME = "adrv9371_zc706_xsa"
DTBO_REMOTE_PATH = f"/tmp/{OVERLAY_NAME}.dtbo"
FDT_MAGIC = b"\xd0\x0d\xfe\xed"

DDS_TONE_HZ = 1_000_000
DDS_SCALE = 0.5
RX_BUFFER_SIZE = 2**14

EXPECTED_IIO_NAMES_ANY = (
    "axi-ad9371-rx-hpc",
    "ad_ip_jesd204_tpl_adc",
)
EXPECTED_IIO_NAMES_ALL = ("ad9528-1", "ad9371-phy")


def _adrv9371_cfg() -> dict[str, Any]:
    """ADRV9371+ZC706 XSA pipeline cfg.

    Lifted verbatim from :mod:`test.hw.test_adrv9371_zc706_hw` so the
    XSA pipeline path the overlay test exercises is identical to the
    one the full-DTB system test exercises — any framing or GPIO
    drift between the two stays a single edit.

    JESD framing matches the Kuiper reference design
    ``zynq-zc706-adv7511-adrv937x``: RX = M=4 L=2 S=1 → F=4;
    TX = M=4 L=4 S=1 → F=2 (per ``analogdevicesinc/hdl/projects/
    adrv9371x/zc706/README``).  Mykonos profile properties come from
    ``adidt/xsa/profiles/adrv937x_zc706.json`` and are not duplicated
    here.
    """
    cfg: dict[str, Any] = {
        "adrv9009_board": {
            "misc_clk_hz": 122_880_000,
            "spi_bus": "spi0",
            "clk_cs": 0,
            "trx_cs": 1,
            "trx_reset_gpio": 106,
            "trx_sysref_req_gpio": 112,
            "ad9528_reset_gpio": 113,
            "ad9528_vcxo_freq": DEFAULT_VCXO_HZ,
            "rx_link_id": 1,
            "tx_link_id": 0,
        },
        "jesd": {
            "rx": {"F": 4, "K": 32, "M": 4, "L": 2},
            "tx": {"F": 2, "K": 32, "M": 4, "L": 4},
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
    """Run :class:`XsaPipeline` once per module and return its output dict."""
    local_xsa = Path(__file__).parent / "system_top_adrv9371_zc706.xsa"
    try:
        xsa_path = acquire_xsa(
            local_xsa,
            DEFAULT_KUIPER_RELEASE,
            DEFAULT_KUIPER_PROJECT,
            tmp_path_factory.mktemp("xsa_dl"),
        )
    except Exception as exc:  # noqa: BLE001 — any download/IO failure → skip
        pytest.skip(f"could not acquire ADRV9371+ZC706 XSA: {exc}")

    topology = XsaParser().parse(xsa_path)
    assert topology.jesd204_rx, "No JESD204 RX instances in XSA topology"
    assert topology.jesd204_tx, "No JESD204 TX instances in XSA topology"

    out_dir = tmp_path_factory.mktemp("overlay") / "out"
    return XsaPipeline().run(
        xsa_path=xsa_path,
        cfg=_adrv9371_cfg(),
        output_dir=out_dir,
        profile="adrv937x_zc706",
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

    Same rationale as the ADRV9009 ZC706 overlay test: the merged DTB
    has the AD9528 + AD9371 SPI nodes already in place, so the overlay
    exercises the configfs lifecycle on top of an already-probed tree
    without inheriting unrelated stock-image boot issues.

    The DTB is renamed to ``devicetree.dtb`` because
    :class:`BootFPGASoCTFTP` (configured in ``test/hw/env/bq.yaml``)
    sets ``dtb_image_name: devicetree.dtb`` — the file U-Boot's
    ``tftp devicetree.dtb`` looks up in the TFTP root.
    """
    out_dir = tmp_path_factory.mktemp("merged_boot")
    merged_dts = pipeline_result["merged"]
    dtb_raw = out_dir / "adrv9371_zc706_xsa.dtb"
    compile_dts_to_dtb(merged_dts, dtb_raw)

    staged = stage_dtb_as_devicetree(dtb_raw, out_dir / "tftp_staging")

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
    # Mykonos re-init after overlay apply takes longer than the AD9081
    # path; give the JESD FSM time to walk SYNC -> ILAS -> DATA before
    # any sysfs check.
    time.sleep(8.0)


def _assert_iio_devices_present(ctx, *, context: str) -> None:
    found = {d.name for d in ctx.devices if d.name}
    suffix = f" ({context})" if context else ""
    for required in EXPECTED_IIO_NAMES_ALL:
        assert required in found, (
            f"IIO device {required!r} not present{suffix}. Devices: {sorted(found)}"
        )
    assert any(n in found for n in EXPECTED_IIO_NAMES_ANY), (
        f"AD9371 RX frontend not present{suffix}. "
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
    assert "ad9371" in src.lower() or "axi-jesd204" in src, (
        f"Pipeline overlay does not reference ADRV9371 / JESD nodes: {dtso}"
    )
    assert overlay_dtbo.exists() and overlay_dtbo.stat().st_size > 100


@requires_lg
@pytest.mark.lg_feature(["adrv9371", "zc706"])
def test_configfs_overlay_support(booted_board):
    """Target kernel must support runtime overlays via configfs."""
    assert_configfs_overlay_support(_shell(booted_board))


@requires_lg
@pytest.mark.lg_feature(["adrv9371", "zc706"])
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
    assert_no_probe_errors(dmesg_new)

    ctx, _ = open_iio_context(shell)
    _assert_iio_devices_present(ctx, context="after overlay load")

    rx_status, tx_status = assert_jesd_links_data(shell, context="after overlay load")
    print(f"$ cat .../*.axi?jesd204?rx/status\n{rx_status}")
    print(f"$ cat .../*.axi?jesd204?tx/status\n{tx_status}")


@requires_lg
@pytest.mark.lg_feature(["adrv9371", "zc706"])
def test_dma_loopback(booted_board):
    """Verify DMA TX→RX data path.

    Two verification phases:

    * **Mandatory:** :func:`assert_rx_capture_valid` confirms that an
      RX buffer arrives with non-zero, non-latched samples.
    * **Opportunistic FFT:** drive a DDS tone on TX and look for a
      coherent peak in the RX spectrum.  ZC706 + ADRV9371 reference
      HDL has no internal DAC→ADC loopback, so without an external
      TX→RX SMA cable on the FMC the noise-floor metric is logged
      and the stage passes — TX→RX coupling is a lab-setup concern,
      not an overlay-lifecycle concern.
    """
    pytest.importorskip("adi")
    np = pytest.importorskip("numpy")

    shell = _shell(booted_board)
    if not overlay_is_loaded(shell, OVERLAY_NAME):
        pytest.skip("overlay not loaded — test_load_overlay must run first")

    ctx, ip = open_iio_context(shell)

    # Probe TPL ADC version + force RSTN + chan-enable BEFORE capture.
    # Earlier diagnostics showed reg 0x40 (RSTN) reading 0 even though
    # cf_axi_adc.probe writes 0x3 — the core looks held in reset.
    # If forcibly setting RSTN unblocks DMA, the issue is between
    # cf_axi_adc.probe and the JESD post_running stage.
    # Use AXI register access path — cf_axi_adc routes plain debugfs
    # writes to the SPI converter (AD9371) by default; OR'ing
    # 0x80000000 (DEBUGFS_DRA_PCORE_REG_MAGIC, cf_axi_adc.h:193)
    # routes to the TPL ADC's MMIO registers.
    # Phase 1: bare data-path smoke check.  AD9371 driver name is
    # ``ad9371-phy``; pyadi-iio's ``adi.adrv9371`` looks up the
    # buffered RX ADC by ``axi-ad9371-rx-hpc``.  The sdtgen-generated
    # merged DTB labels the same buffered frontend
    # ``ad_ip_jesd204_tpl_adc``; either is a valid capture target.
    try:
        assert_rx_capture_valid(
            ctx,
            (
                "axi-ad9371-rx-hpc",
                "ad_ip_jesd204_tpl_adc",
            ),
            n_samples=2**12,
            context="adrv9371 zc706 overlay",
        )
    except AssertionError:
        # Surface the canonical signature that distinguishes the
        # documented HDL IRQ-wiring blocker from a real DT regression.
        # If TRANSFER_DONE > 0 + IRQ_PENDING != 0 + GICD pending == 0
        # + /proc/interrupts count == 0, the DMAC IRQ line is the
        # culprit (HDL bitstream).  Anything else is a new bug.
        print("=== DMAC HW progress (TRANSFER_DONE / IRQ_PENDING / IRQ_SOURCE) ===")
        print(
            shell_out(
                shell,
                "for off in 0x084 0x088 0x418 0x428 0x42c; do "
                "  v=$(busybox devmem $((0x7c400000 + off)) 2>&1 | head -1); "
                "  printf 'dmac+%s = %s\\n' $off \"$v\"; "
                "done",
            )
        )
        print("=== GIC distributor (IRQ 63 enable + pending) ===")
        print(
            shell_out(
                shell,
                # Zynq-7000 GICD at 0xF8F01000;
                #   ICDISER1=+0x104 (enable for IRQs 32-63)
                #   ICDISPR1=+0x204 (pending for IRQs 32-63)
                # axi_dmac@7c400000 → SPI 31 → GIC IRQ 63 → bit 31 of word 1.
                "for r in 0x104 0x204; do "
                "  v=$(busybox devmem $((0xF8F01000 + r)) 2>&1 | head -1); "
                "  printf 'GICD+%s = %s\\n' $r \"$v\"; "
                "done",
            )
        )
        print("=== /proc/interrupts (jesd + axi_dmac counts) ===")
        print(
            shell_out(
                shell,
                "grep -E 'jesd|axi_dmac' /proc/interrupts || true",
            )
        )
        raise

    # Phase 2: opportunistic spectrum check via pyadi-iio.
    import adi

    try:
        dev = adi.adrv9371(uri=f"ip:{ip}")
    except Exception as exc:  # noqa: BLE001 — connect failure → skip phase 2
        print(f"adi.adrv9371 unavailable; skipping FFT phase: {exc}")
        return
    if getattr(dev, "_rxadc", None) is None:
        print(
            "adi.adrv9371 missing 'axi-ad9371-rx-hpc' IIO name "
            "(merged DTB exposes 'ad_ip_jesd204_tpl_adc' instead) — "
            "skipping FFT phase; Phase 1 already validated the data path."
        )
        return

    dev.rx_enabled_channels = [0]
    dev.rx_buffer_size = RX_BUFFER_SIZE
    sample_rate = int(dev.rx_sample_rate)
    print(f"ADRV9371 RX sample rate: {sample_rate} Hz, buffer: {RX_BUFFER_SIZE}")

    try:
        try:
            dev.dds_single_tone(DDS_TONE_HZ, DDS_SCALE, channel=0)
        except Exception as exc:  # noqa: BLE001 — log and continue without DDS
            print(f"adrv9371 DDS setup failed; capturing anyway: {exc}")

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
@pytest.mark.lg_feature(["adrv9371", "zc706"])
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
@pytest.mark.lg_feature(["adrv9371", "zc706"])
def test_reload_overlay(booted_board):
    """Load → unload → load cycle; re-verify devices + JESD link."""
    shell = _shell(booted_board)
    _ensure_unloaded(shell)

    _apply_and_wait(shell)
    ctx, _ = open_iio_context(shell)
    _assert_iio_devices_present(ctx, context="after overlay reload")
    assert_jesd_links_data(shell, context="after overlay reload")
