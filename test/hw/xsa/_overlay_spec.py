"""Declarative spec + factories for runtime overlay hardware tests.

A :class:`BoardOverlayProfile` instance fully describes how the shared
overlay-lifecycle test suite (in :mod:`test.hw.xsa._overlay_base`)
should run for a particular board + carrier combination: which XSA to
use, how to derive the JESD/clock cfg, how to boot, which IIO devices
to expect, and any board-specific hooks for the DMA loopback phase.

A board test module declares a ``SPEC`` constant and exposes it as the
module-scoped ``overlay_spec`` fixture; it then imports the shared
fixtures + 6 test functions from :mod:`test.hw.xsa._overlay_base` and
pytest collects them into the board file's namespace under their
canonical names (``test_load_overlay``, ``test_dma_loopback``, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Optional, Sequence

import pytest

from test.hw.hw_helpers import acquire_xsa


BootMode = Literal["tftp", "sd", "fabric_jtag"]
FftMode = Literal["required", "optional", "skip"]


CfgBuilder = Callable[[], dict[str, Any]]
XsaResolver = Callable[[Path], Path]
TopologyAssert = Callable[[Any], None]
DmesgFilter = Callable[[str], str]
PreCaptureHook = Callable[[Any, Path], bool]
CaptureTargetsResolver = Callable[[Any], Sequence[str]]
PyAdiFactory = Callable[[str], Any]
FailureDiagnostics = Callable[[Any], None]


def _identity(text: str) -> str:
    return text


def _noop_topology(_topology: Any) -> None:
    return None


@dataclass(frozen=True)
class BoardOverlayProfile:
    """Per-board configuration consumed by the shared overlay test suite.

    Required fields (no default):

    * ``overlay_name`` — unique configfs node name, e.g. ``"ad9081_zcu102_xsa"``.
    * ``lg_features`` — labgrid place feature tuple, applied as
      ``@pytest.mark.lg_feature(...)`` to every hardware test by the
      ``xsa/conftest.py`` collection hook.
    * ``skip_reason_label`` — short human-readable name used in skip messages.
    * ``cfg_builder`` — zero-arg callable returning the cfg dict for
      :meth:`adidt.xsa.pipeline.XsaPipeline.run`.
    * ``xsa_resolver`` — single-arg callable that takes a ``tmp_path``
      and returns a path to the XSA on disk (or calls ``pytest.skip``).
    * ``sdtgen_profile`` — pipeline profile name (e.g. ``"adrv9009_zc706"``).
    * ``boot_mode`` — one of ``"tftp"``, ``"sd"``, ``"fabric_jtag"``.

    All other fields have safe defaults so a minimal board declaration
    only fills those seven required slots.
    """

    overlay_name: str
    lg_features: tuple[str, ...]
    skip_reason_label: str

    cfg_builder: CfgBuilder
    xsa_resolver: XsaResolver
    sdtgen_profile: str

    boot_mode: BootMode

    topology_assert: TopologyAssert = _noop_topology
    sdtgen_timeout: int = 300

    dtso_must_contain_all: tuple[str, ...] = ()
    dtso_must_contain_any: tuple[str, ...] = ()

    kernel_fixture_name: Optional[str] = None
    settle_after_apply_s: float = 5.0

    iio_required_all: tuple[str, ...] = ()
    iio_required_any: tuple[str, ...] = ()
    iio_frontend_label: str = "RX frontend"

    dmesg_filter: DmesgFilter = _identity

    fft_mode: FftMode = "skip"
    pre_capture_hook: Optional[PreCaptureHook] = None
    capture_targets_resolver: Optional[CaptureTargetsResolver] = None
    capture_target_names: tuple[str, ...] = ()
    pyadi_class_name: Optional[str] = None
    pyadi_factory: Optional[PyAdiFactory] = None
    dds_tone_hz: int = 1_000_000
    dds_scale: float = 0.5
    rx_buffer_size: int = 2**14
    fft_failure_diagnostics: Optional[FailureDiagnostics] = None

    extra_imports_check: tuple[str, ...] = field(default=())


# ---------------------------------------------------------------------------
# Resolver factories — common XSA acquisition patterns the boards reuse.
# ---------------------------------------------------------------------------


def local_xsa_or_skip(*candidate_filenames: str) -> XsaResolver:
    """Return a resolver that picks the first existing local XSA fixture.

    Looks under ``test/hw/xsa/`` and ``test/hw/xsa/ref_data/`` for each
    candidate basename in order; calls :func:`pytest.skip` if none are
    present.  Used by FMCDAQ3+VCU118 (no Kuiper download exists for the
    MicroBlaze build) and as a fallback for AD9081+ZCU102.
    """
    here = Path(__file__).parent

    def _resolver(_tmp_path: Path) -> Path:
        for name in candidate_filenames:
            for parent in (here, here / "ref_data"):
                candidate = parent / name
                if candidate.exists():
                    return candidate
        searched = ", ".join(
            str(parent / name)
            for name in candidate_filenames
            for parent in (here, here / "ref_data")
        )
        pytest.skip(f"XSA fixture missing — looked at: {searched}")

    return _resolver


def acquire_or_local_xsa(
    local_filename: str,
    release: str,
    project: str,
    *,
    fallback_filenames: tuple[str, ...] = (),
) -> XsaResolver:
    """Return a resolver that prefers a local XSA, else downloads from Kuiper.

    Tries ``test/hw/xsa/<local_filename>`` (and any
    ``fallback_filenames``) first; if none are present, hands off to
    :func:`test.hw.hw_helpers.acquire_xsa` which downloads from the
    given Kuiper *release* / *project*.  Skips the test on download
    failure rather than erroring — the same behavior the original
    inline ``pipeline_result`` fixtures had.
    """
    here = Path(__file__).parent

    def _resolver(tmp_path: Path) -> Path:
        for name in (local_filename, *fallback_filenames):
            for parent in (here, here / "ref_data"):
                candidate = parent / name
                if candidate.exists():
                    return candidate
        try:
            return acquire_xsa(
                here / local_filename,
                release,
                project,
                tmp_path,
            )
        except Exception as exc:  # noqa: BLE001 — any IO/download failure → skip
            pytest.skip(f"could not acquire XSA ({project}@{release}): {exc}")

    return _resolver
