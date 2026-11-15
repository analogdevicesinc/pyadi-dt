"""Shared infrastructure for merged-DTB hardware tests.

The 4 XSA-pipeline merged-DTB tests at ``test/hw/test_*_hw.py`` (and
the post-render section of the declarative System API test) all share
the same shape: parse XSA → run pipeline → compile DTS → stage DTB →
boot via labgrid → assert clean dmesg + IIO probe + JESD DATA + RX
capture.  Each per-board diagnostic tail (Talise profile sweep,
ADRV9371 GIC poke, sysfs register dumps) stays in its own test file
because those are genuinely one-off.

A board test module declares a :class:`BoardSystemProfile` and
delegates the standard front-matter to :func:`run_xsa_boot_and_verify`,
or — for the declarative System API path that does its own composition
— calls :func:`boot_and_verify_from_merged_dts` directly with the
merged DTS path it produced.
"""

from __future__ import annotations

import os
import shutil as _shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Optional

import pytest

from adidt.xsa.pipeline import XsaPipeline
from adidt.xsa.parse.topology import XsaParser
from test.hw.hw_helpers import (
    shell_out,
    DEFAULT_OUT_DIR,
    assert_jesd_links_data,
    assert_no_kernel_faults,
    assert_no_probe_errors,
    assert_rx_capture_valid,
    collect_dmesg,
    compile_dts_to_dtb,
    deploy_and_boot,
    open_iio_context,
    stage_dtb_as_devicetree,
)
from test.hw.xsa._overlay_spec import (  # re-exported for board-file convenience
    acquire_or_local_xsa,
    local_xsa_or_skip,
)


__all__ = [
    "BoardSystemProfile",
    "acquire_or_local_xsa",
    "boot_and_verify_from_dtb",
    "boot_and_verify_from_merged_dts",
    "local_xsa_or_skip",
    "requires_lg",
    "run_xsa_boot_and_verify",
    "run_xsa_pipeline",
]


_HAS_LG = bool(os.environ.get("LG_COORDINATOR") or os.environ.get("LG_ENV"))
requires_lg = pytest.mark.skipif(
    not _HAS_LG,
    reason=(
        "set LG_COORDINATOR or LG_ENV for merged-DTB hardware tests (see .env.example)"
    ),
)


CfgBuilder = Callable[[], dict[str, Any]]
XsaResolver = Callable[[Path], Path]
TopologyAssert = Callable[[Any], None]
DmesgFilter = Callable[[str], str]


def _identity(text: str) -> str:
    return text


def _noop_topology(_topology: Any) -> None:
    return None


BootMode = Literal["tftp", "sd"]


@dataclass(frozen=True)
class BoardSystemProfile:
    """Per-board configuration for the standard XSA → boot → verify flow.

    Required fields (no default):

    * ``lg_features`` — labgrid place feature tuple.
    * ``cfg_builder`` — zero-arg callable returning the cfg dict for
      :meth:`adidt.xsa.pipeline.XsaPipeline.run`.
    * ``xsa_resolver`` — single-arg callable: ``(tmp_path) -> Path``.
    * ``boot_mode`` — ``"tftp"`` or ``"sd"``.
    * ``kernel_fixture_name`` — name of a session-scoped kernel-image
      fixture in :mod:`test.hw.conftest`
      (``"built_kernel_image_zynq"`` / ``"built_kernel_image_zynqmp"``).
    * ``out_label`` — short string used in dmesg log filenames and
      assertion ``context=`` arguments.
    * ``dmesg_grep_pattern`` — extended regex for the diagnostic
      ``dmesg | grep -Ei <pattern>`` tail.

    All other fields have safe defaults so a minimal board declaration
    only fills those seven required slots.
    """

    lg_features: tuple[str, ...]

    cfg_builder: CfgBuilder
    xsa_resolver: XsaResolver

    boot_mode: BootMode
    kernel_fixture_name: str

    out_label: str
    dmesg_grep_pattern: str

    sdtgen_profile: Optional[str] = None
    sdtgen_timeout: int = 300

    topology_assert: TopologyAssert = _noop_topology
    merged_dts_must_contain: tuple[str, ...] = ()

    probe_signature_any: tuple[str, ...] = ()
    probe_signature_message: str = "expected probe signature not found in dmesg"

    iio_required_all: tuple[str, ...] = ()
    iio_required_any_groups: tuple[tuple[str, ...], ...] = ()

    jesd_rx_glob: Optional[str] = None
    jesd_tx_glob: Optional[str] = None
    expected_rx_jesd_links: int = 1
    expected_tx_jesd_links: int = 1

    dmesg_filter: DmesgFilter = _identity

    rx_capture_target_names: tuple[str, ...] = ()

    dtb_basename: str = field(default="")  # auto-derived from out_label if empty

    petalinux_template: Optional[Literal["zynqMP", "zynq"]] = None
    petalinux_install_env: str = "PETALINUX_INSTALL"


def _staged_dtb_for_boot(
    spec: BoardSystemProfile, dtb_raw: Path, staging_root: Path
) -> Path:
    """Stage *dtb_raw* under the basename the boot transport expects.

    ``"tftp"`` → ``devicetree.dtb`` (Zynq-7000 BootFPGASoCTFTP).
    ``"sd"``   → ``system.dtb``     (Kuiper ZynqMP U-Boot).
    """
    if spec.boot_mode == "tftp":
        return stage_dtb_as_devicetree(dtb_raw, staging_root / "tftp_staging")
    if spec.boot_mode == "sd":
        staged_dir = staging_root / "sd_staging"
        staged_dir.mkdir(parents=True, exist_ok=True)
        staged = staged_dir / "system.dtb"
        _shutil.copyfile(dtb_raw, staged)
        return staged
    raise ValueError(f"unknown boot_mode: {spec.boot_mode!r}")


def _assert_iio_devices_present(spec: BoardSystemProfile, ctx) -> None:
    found = {d.name for d in ctx.devices if d.name}
    for required in spec.iio_required_all:
        assert required in found, (
            f"IIO device {required!r} not present. Devices: {sorted(found)}"
        )
    for group in spec.iio_required_any_groups:
        assert any(n in found for n in group), (
            f"None of {list(group)} present. Devices: {sorted(found)}"
        )


def boot_and_verify_from_dtb(
    spec: BoardSystemProfile,
    dtb_path: Path,
    *,
    board,
    request,
    out_dir: Path,
):
    """Stage *dtb_path*, boot the board, and run the standard verify.

    Assumes ``dtb_path`` is an already-compiled, non-empty DTB.

    Steps performed:

    1. Stage the DTB under the boot transport's expected basename.
    2. Pull the kernel image fixture named in ``spec.kernel_fixture_name``.
    3. ``deploy_and_boot``.
    4. Collect dmesg and assert no kernel faults / probe errors.
    5. Optional probe signature check (``spec.probe_signature_any``).
    6. Open an IIO context and check ``iio_required_all`` / ``_any``.
    7. Assert both JESD links reach DATA (with optional reg-address globs).
    8. Optional RX capture smoke test (``spec.rx_capture_target_names``).

    Returns ``(shell, ctx, dmesg_txt)`` so callers can run additional
    board-specific diagnostics on the booted target.
    """
    assert dtb_path.exists() and dtb_path.stat().st_size > 0, (
        f"empty/missing DTB: {dtb_path}"
    )

    staged_dtb = _staged_dtb_for_boot(spec, dtb_path, out_dir)
    kernel_image = request.getfixturevalue(spec.kernel_fixture_name)

    shell = deploy_and_boot(board, staged_dtb, kernel_image)

    dmesg_txt = collect_dmesg(
        shell,
        out_dir,
        label=spec.out_label,
        grep_pattern=spec.dmesg_grep_pattern,
    )
    assert_no_kernel_faults(dmesg_txt)
    assert_no_probe_errors(spec.dmesg_filter(dmesg_txt))

    if spec.probe_signature_any:
        lower = dmesg_txt.lower()
        assert any(sig.lower() in lower for sig in spec.probe_signature_any), (
            f"{spec.probe_signature_message}. Looked for: "
            f"{list(spec.probe_signature_any)}"
        )

    ctx, _ = open_iio_context(shell)
    _assert_iio_devices_present(spec, ctx)

    rx_glob = spec.jesd_rx_glob or "*.axi[_-]jesd204[_-]rx"
    tx_glob = spec.jesd_tx_glob or "*.axi[_-]jesd204[_-]tx"
    rx_status, tx_status = assert_jesd_links_data(
        shell,
        context=spec.out_label,
        rx_glob=rx_glob,
        tx_glob=tx_glob,
        expected_rx_links=spec.expected_rx_jesd_links,
        expected_tx_links=spec.expected_tx_jesd_links,
    )
    print(f"$ cat .../{rx_glob}/status\n{rx_status}")
    print(f"$ cat .../{tx_glob}/status\n{tx_status}")

    if spec.rx_capture_target_names:
        try:
            assert_rx_capture_valid(
                ctx,
                spec.rx_capture_target_names,
                n_samples=2**12,
                context=spec.out_label,
            )
        except AssertionError:
            _debug_zero_capture(shell)  # TEMPORARY: 2026.1 AD9081 bring-up
            raise

    return shell, ctx, dmesg_txt


def boot_and_verify_from_merged_dts(
    spec: BoardSystemProfile,
    merged_dts: Path,
    *,
    board,
    request,
    out_dir: Path,
    dtb_basename: Optional[str] = None,
):
    """Compile *merged_dts* with dtc, then boot and run the standard verify.

    Thin wrapper: dtc compile → :func:`boot_and_verify_from_dtb`.
    See that function for the full step list and return value.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    name = dtb_basename or f"{spec.out_label}.dtb"
    dtb_raw = out_dir / name
    compile_dts_to_dtb(merged_dts, dtb_raw)
    assert dtb_raw.exists() and dtb_raw.stat().st_size > 0, (
        f"dtc produced empty/missing DTB: {dtb_raw}"
    )
    return boot_and_verify_from_dtb(
        spec, dtb_raw, board=board, request=request, out_dir=out_dir
    )


def run_xsa_pipeline(
    spec: BoardSystemProfile,
    *,
    tmp_path: Path,
    out_dir: Path,
) -> Path:
    """Resolve the XSA, run :class:`XsaPipeline`, return the merged DTS path.

    Performs the parse + topology assertions documented in
    ``spec.topology_assert``, then runs ``XsaPipeline().run`` with
    ``spec.cfg_builder()`` and ``spec.sdtgen_profile``.  Asserts the
    expected substrings from ``spec.merged_dts_must_contain`` are
    present in the merged DTS.
    """
    xsa_path = spec.xsa_resolver(tmp_path)
    assert xsa_path.exists(), f"XSA not found: {xsa_path}"

    topology = XsaParser().parse(xsa_path)
    spec.topology_assert(topology)
    print(
        f"XSA topology: {len(topology.converters)} converter(s), "
        f"{len(topology.jesd204_rx)} rx jesd, {len(topology.jesd204_tx)} tx jesd"
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    result = XsaPipeline().run(
        xsa_path=xsa_path,
        cfg=spec.cfg_builder(),
        output_dir=out_dir,
        sdtgen_timeout=spec.sdtgen_timeout,
        profile=spec.sdtgen_profile,
    )
    merged_dts = result["merged"]
    assert merged_dts.exists(), f"Merged DTS not written: {merged_dts}"

    merged_content = merged_dts.read_text()
    for needle in spec.merged_dts_must_contain:
        assert needle in merged_content, (
            f"Required substring {needle!r} missing from merged DTS"
        )

    return merged_dts


def run_xsa_boot_and_verify(
    spec: BoardSystemProfile,
    *,
    board,
    request,
    tmp_path: Path,
    out_dir: Optional[Path] = None,
):
    """End-to-end: XSA → pipeline → DTB → boot → standard verify.

    Convenience wrapper for the 4 boards whose tests are pure
    XSA-pipeline drivers (no declarative composition step).  Returns
    the same ``(shell, ctx, dmesg_txt)`` tuple as
    :func:`boot_and_verify_from_merged_dts` for any per-board
    diagnostic tail.
    """
    out_dir = out_dir or DEFAULT_OUT_DIR
    merged_dts = run_xsa_pipeline(spec, tmp_path=tmp_path, out_dir=out_dir)
    return boot_and_verify_from_merged_dts(
        spec,
        merged_dts,
        board=board,
        request=request,
        out_dir=out_dir,
    )


_ZERO_CAPTURE_DEBUG = r"""
import mmap,os,struct,subprocess as s
f=os.open('/dev/mem',os.O_RDWR|os.O_SYNC)
def r(x,o):return struct.unpack('<I',x[o:o+4])[0]
def d(n,b,l):
 x=mmap.mmap(f,0x1000,offset=b);print(n,' '.join('%x=%x'%(o,r(x,o))for o in l));return x
def cap(t):
 print(t,s.run("iio_readdev -s 4096 ad_ip_jesd204_tpl_adc 2>&1|od -An -tx2|sort|uniq -c|sort -rn|head -3",shell=True,capture_output=True,text=True).stdout)
L=[0,4,0xc,0x10,0x14,0x1c,0x80,0x84,0x88,0x100,0x104,0x200]
o=d('offload',0x9c450000,L)
d('tpl',0x84a10000,[0,0x40,0x44,0x5c,0x400,0x404,0x408,0x440,0x444])
d('dma',0x9c420000,[0,0x400,0x404,0x40c,0x418,0x428,0x430])
cap('cap1')
o[0x88:0x8c]=struct.pack('<I',r(o,0x88)|1)
d('bypass',0x9c450000,L)
cap('cap2')
"""


def _debug_zero_capture(shell) -> None:
    """TEMPORARY bring-up aid: dump the receive path and retry with bypass."""
    import base64

    blob = base64.b64encode(_ZERO_CAPTURE_DEBUG.encode()).decode()
    shell_out(shell, "rm -f /tmp/zc.b64")
    for start in range(0, len(blob), 400):
        shell_out(shell, f"echo -n {blob[start : start + 400]} >> /tmp/zc.b64")
    print("ZERO-CAPTURE-DEBUG")
    print(
        shell_out(shell, "base64 -d /tmp/zc.b64 > /tmp/zc.py; python3 /tmp/zc.py 2>&1")
    )
    print(
        shell_out(
            shell,
            "ls /sys/kernel/debug | grep -i offload; iio_attr -c ad_ip_jesd204_tpl_adc 2>&1 | head -12",
        )
    )
