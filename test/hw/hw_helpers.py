"""Shared helpers and constants for XSA hardware integration tests."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import re as _re

from adidt.xsa.merge.dts_normalize import dedup_zynqmp_root_nodes

HERE = Path(__file__).parent


DEFAULT_OUT_DIR = HERE / "output"
DEFAULT_BUILD_KERNEL = os.environ.get("ADI_XSA_BUILD_KERNEL", "1").lower() not in {
    "0",
    "false",
    "no",
}

# File-based kernel cache: skip a full pyadi-build ``prepare_source`` +
# ``build`` run when a kernel image for the same (platform, config) has
# already been produced.  Keyed by sha256 of the 2023_R2.yaml contents
# so editing the config invalidates the cache automatically.  Disable by
# setting ``ADIDT_KERNEL_CACHE=0``.
DEFAULT_KERNEL_CACHE = os.environ.get("ADIDT_KERNEL_CACHE", "1").lower() not in {
    "0",
    "false",
    "no",
}
KERNEL_CACHE_DIR = Path(
    os.environ.get(
        "ADIDT_KERNEL_CACHE_DIR", str(Path.home() / ".cache" / "adidt" / "kernel")
    )
)


def _strip_unresolved_overlays(dts_path: Path, stderr: str) -> bool:
    """Remove ``&label { ... };`` blocks for labels that dtc reports as missing.

    Returns True if any blocks were stripped.
    """
    import re

    labels = set(re.findall(r"Label or path (\S+) not found", stderr))
    if not labels:
        return False
    text = dts_path.read_text()
    changed = False
    for label in labels:
        # Match &label { ... }; blocks (handles nested braces simply)
        pattern = rf"^\s*&{re.escape(label)}\s*\{{[^}}]*\}};?\s*$"
        new_text = re.sub(pattern, "", text, flags=re.MULTILINE)
        if new_text != text:
            text = new_text
            changed = True
    if changed:
        dts_path.write_text(text)
    return changed


def compile_dts_to_dtb(dts_path: Path, dtb_path: Path) -> None:
    """Compile a DTS file to a DTB binary.

    If the DTS contains ``#include`` directives the file is first preprocessed
    with ``cpp``.  The resulting DTB is written to *dtb_path*.

    Args:
        dts_path: Path to the source ``.dts`` file.
        dtb_path: Destination path for the compiled ``.dtb`` output.

    Raises:
        RuntimeError: if ``cpp`` or ``dtc`` exits with a non-zero return code.
    """
    compile_input = dts_path
    text = dts_path.read_text()

    if "#include" in text:
        if shutil.which("cpp") is None:
            raise RuntimeError(
                "cpp not found on PATH (required for #include preprocessing)"
            )
        preprocessed = dtb_path.parent / f"{dts_path.stem}.pp.dts"
        include_dirs = [dts_path.parent, dts_path.parent / "base"]
        cmd = ["cpp", "-P", "-nostdinc", "-undef", "-x", "assembler-with-cpp"]
        for inc in include_dirs:
            if inc.exists():
                cmd.extend(["-I", str(inc)])
        cmd.extend([str(dts_path), str(preprocessed)])
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise RuntimeError(f"cpp failed:\n{res.stderr}")
        compile_input = preprocessed

    # Fix duplicate node names from sdtgen (e.g., cpus_a53 and
    # cpus_microblaze_0 both using node name "cpus")
    if compile_input != dts_path:
        dedup_zynqmp_root_nodes(compile_input)

    res = subprocess.run(
        ["dtc", "-I", "dts", "-O", "dtb", "-o", str(dtb_path), str(compile_input)],
        capture_output=True,
        text=True,
        check=False,
    )
    if (
        res.returncode != 0
        and "Label or path" in res.stderr
        and "not found" in res.stderr
    ):
        # Strip unresolved overlay blocks and retry
        if _strip_unresolved_overlays(compile_input, res.stderr):
            res = subprocess.run(
                [
                    "dtc",
                    "-I",
                    "dts",
                    "-O",
                    "dtb",
                    "-o",
                    str(dtb_path),
                    str(compile_input),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
    if res.returncode != 0:
        raise RuntimeError(f"dtc failed:\n{res.stderr}")


def stage_dtb_as_devicetree(dtb: Path, staging_dir: Path) -> Path:
    """Copy *dtb* into *staging_dir* renamed to ``devicetree.dtb``.

    The Zynq-7000 ``BootFPGASoCTFTP`` driver in the ``bq`` and ``nemo``
    labgrid environments hard-codes ``dtb_image_name: devicetree.dtb`` —
    the file must have that exact basename when it lands in the TFTP
    root for U-Boot's ``tftp devicetree.dtb`` to find it.
    """
    staging_dir.mkdir(parents=True, exist_ok=True)
    staged = staging_dir / "devicetree.dtb"
    shutil.copyfile(dtb, staged)
    return staged


def compile_dtso_to_dtbo(dtso_path: Path, dtbo_path: Path) -> None:
    """Compile a DTS overlay to a DTBO binary.

    Uses ``dtc -@`` to preserve external symbol references (``&label``
    phandles) required for runtime overlay application via configfs.

    Args:
        dtso_path: Path to the source ``.dtso`` overlay file.
        dtbo_path: Destination path for the compiled ``.dtbo`` output.

    Raises:
        RuntimeError: if ``dtc`` exits with a non-zero return code.
    """
    compile_input = dtso_path
    text = dtso_path.read_text()

    if "#include" in text:
        if shutil.which("cpp") is None:
            raise RuntimeError(
                "cpp not found on PATH (required for #include preprocessing)"
            )
        preprocessed = dtbo_path.parent / f"{dtso_path.stem}.pp.dtso"
        include_dirs = [dtso_path.parent, dtso_path.parent / "base"]
        cmd = ["cpp", "-P", "-nostdinc", "-undef", "-x", "assembler-with-cpp"]
        for inc in include_dirs:
            if inc.exists():
                cmd.extend(["-I", str(inc)])
        cmd.extend([str(dtso_path), str(preprocessed)])
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise RuntimeError(f"cpp failed:\n{res.stderr}")
        compile_input = preprocessed

    res = subprocess.run(
        [
            "dtc",
            "-@",
            "-I",
            "dts",
            "-O",
            "dtb",
            "-o",
            str(dtbo_path),
            str(compile_input),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(f"dtc overlay compilation failed:\n{res.stderr}")


CONFIGFS_OVERLAYS = "/sys/kernel/config/device-tree/overlays"


def assert_configfs_overlay_support(shell) -> None:
    """Fail the calling test if the target lacks configfs overlay support.

    The ``/sys/kernel/config/device-tree/overlays`` directory only exists
    when the kernel is built with ``CONFIG_OF_CONFIGFS=y`` (which implies
    ``CONFIG_OF_OVERLAY=y``) and ``configfs`` is mounted.  Without it
    there is no way to apply a ``.dtbo`` at runtime.
    """
    res = shell_out(
        shell,
        f"test -d {CONFIGFS_OVERLAYS} && echo OK || echo MISSING",
    )
    assert "OK" in res, (
        f"configfs overlay directory not found at {CONFIGFS_OVERLAYS}. "
        "Ensure the target kernel was built with CONFIG_OF_OVERLAY=y and "
        "configfs is mounted."
    )


def deploy_dtbo_via_shell(shell, dtbo_path: Path, remote_path: str) -> None:
    """Transfer a ``.dtbo`` to the target over the serial shell.

    Encodes the DTBO as base64 and writes it in 512-byte chunks so the
    transfer survives serial line-length limits on the target shell.
    ``base64 -d`` on the target reconstructs the binary and the remote
    size is verified against the local file.  No SSH or networking
    required — mirrors the Talise-profile push pattern in
    ``test/hw/test_adrv9009_zcu102_hw.py``.

    Args:
        shell: An ``ADIShellDriver`` instance.
        dtbo_path: Local ``.dtbo`` file.
        remote_path: Absolute destination path on the target.
    """
    import base64

    data = dtbo_path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    b64_path = f"{remote_path}.b64"

    shell_out(shell, f"rm -f {remote_path} {b64_path}")
    chunk_size = 512
    for i in range(0, len(b64), chunk_size):
        chunk = b64[i : i + chunk_size]
        shell_out(shell, f"printf '%s' '{chunk}' >> {b64_path}")
    shell_out(shell, f"base64 -d {b64_path} > {remote_path}")
    shell_out(shell, f"rm -f {b64_path}")

    remote_size = shell_out(
        shell, f"stat -c %s {remote_path} 2>/dev/null; true"
    ).strip()
    assert remote_size == str(len(data)), (
        f"dtbo transfer size mismatch: local={len(data)}, remote={remote_size!r}"
    )


def overlay_is_loaded(shell, name: str) -> bool:
    """Return True if ``/sys/kernel/config/device-tree/overlays/<name>`` exists."""
    res = shell_out(
        shell,
        f"test -d {CONFIGFS_OVERLAYS}/{name} && echo YES || echo NO",
    )
    return "YES" in res


def load_overlay(shell, name: str, dtbo_remote_path: str) -> str:
    """Apply a ``.dtbo`` at runtime via configfs.

    Creates ``{CONFIGFS_OVERLAYS}/<name>/`` and writes *dtbo_remote_path*
    to its ``path`` attribute, which the kernel resolves via the firmware
    loader and applies to the live tree.  The returned string ends in
    ``RC=<n>`` so callers can assert ``"RC=0"``.
    """
    shell_out(shell, f"mkdir -p {CONFIGFS_OVERLAYS}/{name}")
    return shell_out(
        shell,
        f"echo -n {dtbo_remote_path} > {CONFIGFS_OVERLAYS}/{name}/path 2>&1; "
        "echo RC=$?",
    )


def unload_overlay(shell, name: str) -> str:
    """Remove an applied overlay via ``rmdir`` on its configfs entry."""
    return shell_out(
        shell,
        f"rmdir {CONFIGFS_OVERLAYS}/{name} 2>&1; echo RC=$?",
    )


def require_hw_prereqs() -> None:
    """Skip the current test if required system tools are missing.

    Checks for ``sdtgen``, ``dtc``, and ``usbsdmux`` on ``PATH``.  Also
    probes the local ``venv/bin/usbsdmux`` path as a fallback before giving
    up on ``usbsdmux``.
    """
    if shutil.which("sdtgen") is None:
        pytest.skip("sdtgen not found on PATH (Vivado tools required)")
    if shutil.which("dtc") is None:
        pytest.skip("dtc not found on PATH")
    if shutil.which("usbsdmux") is None:
        local_usbsdmux = Path.cwd() / "venv" / "bin" / "usbsdmux"
        if local_usbsdmux.exists():
            os.environ["PATH"] = f"{local_usbsdmux.parent}:{os.environ.get('PATH', '')}"
    if shutil.which("usbsdmux") is None:
        pytest.skip("usbsdmux not found on PATH")


# Known-benign ``dmesg`` lines unrelated to our ADC/DAC/JESD flow.  These
# appear on stock Kuiper ZCU102 boots regardless of the rendered DTB and
# would produce false positives if matched against the generic
# panic/error patterns below.
_DMESG_BENIGN_SUBSTRINGS = (
    "xilinx-dp-snd-codec",
    "regulatory.db",
    "Direct firmware load for",
    "failed to load firmware",
    # Wifi/USB hotplug noise seen on some Kuiper releases:
    "cfg80211: failed to load",
    # Harmless driver-level probe deferrals re-tried later.  The kernel
    # surfaces these both symbolically (``-EPROBE_DEFER``) and as the
    # raw errno (``-517``) depending on the caller.
    "EPROBE_DEFER",
    "error -517",
    # ZynqMP early-boot WARNING: the kernel logs a Call trace through
    # gic_of_init / of_irq_init because the RPU-bus interrupt-controller
    # cannot be initialized from Linux on ZynqMP.  Always benign; the
    # primary GIC still initializes correctly.
    "gic_of_init",
    "of_irq_init",
    "irqchip_init",
    "__primary_switched",
    "rpu-bus/interrupt-controller",
    # Stock Kuiper ZynqMP (ZCU102) probes these SoC peripherals from the
    # base DTS regardless of the overlay we merge in — the hardware is
    # either unconfigured (no DisplayPort monitor attached) or not wired
    # out on the board (no SATA).  Match by device-node address so a
    # genuine regression on the same driver elsewhere still trips.
    "ffcb0000.watchdog",  # Cadence WDT — unroutable clocks
    "fd4a0000.display",  # ZynqMP DisplayPort — no monitor + DPMS pipe
    "fd0c0000.ahci",  # Ceva AHCI/SATA — not routed on ZCU102
    # Kuiper's prebuilt ``simpleImage.vcu118_fmcdaq3`` declares a
    # secondary AXI UART Lite at 0x41400000 whose DT entry is
    # missing ``current-speed``; the driver probe fails with -EINVAL
    # and this never affects the bring-up path (main UART at
    # 0x40600000 works and drives the serial console).
    "41400000.serial",
)

# Hard-fail patterns — these indicate a genuine kernel fault.
_DMESG_FATAL_PATTERNS = (
    "Kernel panic",
    "Unable to handle kernel",
    "Internal error:",
    "Oops:",
    "BUG:",
    # ``Call trace:`` alone fires on benign WARNINGs (e.g. ZynqMP's
    # early-boot GIC RPU-bus irq-controller init warning).  The real
    # panic/oops signatures above already catch actual faults, so we
    # don't rely on the trace marker.
    "SError Interrupt",
    "synchronous external abort",
    "segfault",
    "Kernel stack",
    "general protection",
    "watchdog: BUG:",
    "soft lockup",
    "hard LOCKUP",
)


def assert_no_kernel_faults(dmesg_txt: str) -> None:
    """Fail the calling test if *dmesg_txt* contains a kernel fault.

    Scans for panic/oops/BUG/SError signatures. Raises ``AssertionError``
    with the offending lines for quick triage. Benign Kuiper boot noise
    (audio codec probe, regulatory.db firmware, deferred probes) is
    ignored via :data:`_DMESG_BENIGN_SUBSTRINGS`.
    """
    bad: list[str] = []
    for line in dmesg_txt.splitlines():
        if any(s in line for s in _DMESG_BENIGN_SUBSTRINGS):
            continue
        if any(p in line for p in _DMESG_FATAL_PATTERNS):
            bad.append(line)
    assert not bad, "Kernel fault(s) detected in dmesg:\n" + "\n".join(bad)


# Driver-probe-failure patterns in dmesg.  These appear when a probe()
# callback returns a negative errno other than -EPROBE_DEFER (the defer
# path is the normal retry-until-resolved dance and is allowlisted via
# _DMESG_BENIGN_SUBSTRINGS above).  Regex, not plain substrings —
# ``probe of <dev> failed with error <N>`` is the canonical kernel
# message.  Overlay-apply errors fall in the same bucket because a
# failed overlay almost always cascades into silent probe misses.
_DMESG_PROBE_ERROR_PATTERNS = (
    r"probe of \S+ failed with error",
    r"Error applying overlay",
    r"failed to apply overlay",
    r"Error resolving",
)


def assert_no_probe_errors(dmesg_txt: str) -> None:
    """Fail the calling test if *dmesg_txt* contains driver-probe errors.

    Complements :func:`assert_no_kernel_faults` — a driver can fail to
    probe without ever producing a kernel fault (e.g. a DT overlay
    apply error, a regulator not showing up, a phandle mismatch).
    Reuses :data:`_DMESG_BENIGN_SUBSTRINGS` so known-benign probe
    chatter (firmware loads, ``-EPROBE_DEFER`` retries, ZynqMP early-
    boot warnings) does not fire.
    """
    compiled = [_re.compile(p) for p in _DMESG_PROBE_ERROR_PATTERNS]
    bad: list[str] = []
    for line in dmesg_txt.splitlines():
        if any(s in line for s in _DMESG_BENIGN_SUBSTRINGS):
            continue
        if any(rx.search(line) for rx in compiled):
            bad.append(line)
    assert not bad, "Driver probe errors detected in dmesg:\n" + "\n".join(bad)


@dataclass
class IlasMismatch:
    """Structured AD937x ILAS mismatch report extracted from dmesg.

    Populated by :func:`parse_ilas_status`.  ``has_mismatch`` is the
    canonical "something is wrong" signal used by
    :func:`assert_ilas_aligned`.
    """

    deframer_status: int | None = None
    mismatch_mask: int | None = None
    fields: list[str] = field(default_factory=list)
    raw_lines: list[str] = field(default_factory=list)

    @property
    def has_mismatch(self) -> bool:
        if self.fields:
            return True
        if self.mismatch_mask not in (None, 0):
            return True
        return False

    def summary(self) -> str:
        parts: list[str] = []
        if self.deframer_status is not None:
            parts.append(f"deframerStatus=0x{self.deframer_status:02x}")
        if self.mismatch_mask is not None:
            parts.append(f"mask=0x{self.mismatch_mask:04x}")
        if self.fields:
            parts.append("fields=[" + ", ".join(self.fields) + "]")
        return "; ".join(parts) or "no ILAS info"


_ILAS_DEFRAMER_STATUS_RX = _re.compile(r"deframerStatus\s*\(0x([0-9a-fA-F]+)\)")
_ILAS_MISMATCH_MASK_RX = _re.compile(r"ILAS mismatch[:\s]+(?:0x)?([0-9a-fA-F]+)")
_ILAS_FIELD_RX = _re.compile(r"ILAS\s+(.+?)\s+did not match")


def parse_ilas_status(dmesg_txt: str) -> IlasMismatch:
    """Extract AD937x ILAS mismatch info from *dmesg_txt*.

    The Mykonos driver emits lines like::

        ad9371 spi1.1: deframerStatus (0x21)
        ad9371 spi1.1: ILAS mismatch: c7f8
        ILAS lanes per converter did not match
        ILAS scrambling did not match
        ...

    When the deframer reports a good ILAS the mismatch / field lines
    don't appear, so ``has_mismatch`` stays ``False``.
    """
    report = IlasMismatch()
    for line in dmesg_txt.splitlines():
        m = _ILAS_DEFRAMER_STATUS_RX.search(line)
        if m:
            report.deframer_status = int(m.group(1), 16)
            report.raw_lines.append(line)
            continue
        m = _ILAS_MISMATCH_MASK_RX.search(line)
        if m:
            report.mismatch_mask = int(m.group(1), 16)
            report.raw_lines.append(line)
            continue
        m = _ILAS_FIELD_RX.search(line)
        if m:
            report.fields.append(m.group(1).strip())
            report.raw_lines.append(line)
    return report


def assert_ilas_aligned(dmesg_txt: str, context: str = "") -> None:
    """Fail the calling test if the AD937x deframer reports an ILAS mismatch.

    Use as the end-to-end gate just before :func:`assert_rx_capture_valid`:
    when ILAS fails, the link drops to ``disabled`` and no samples flow,
    so capture must not even be attempted.
    """
    report = parse_ilas_status(dmesg_txt)
    if not report.has_mismatch:
        return
    suffix = f" ({context})" if context else ""
    lines = [f"AD937x ILAS mismatch detected{suffix}: {report.summary()}"]
    if report.fields:
        lines.append("  Mismatched ILAS fields:")
        lines.extend(f"    - {name}" for name in report.fields)
    if report.raw_lines:
        lines.append("  Raw dmesg lines:")
        lines.extend(f"    {raw}" for raw in report.raw_lines)
    raise AssertionError("\n".join(lines))


def check_jesd_framing_plausibility(jesd_cfg: dict) -> list[str]:
    """Return warnings when ``jesd_cfg`` violates the F = M*Np*S/(8*L) relation.

    Only inspects the ``rx`` and ``tx`` sub-dicts of *jesd_cfg* and
    skips sides that are missing any of M/L/F (caller decides how much
    structure to require).  ``Np`` defaults to ``16`` and ``S`` defaults
    to ``1`` — the standard values for ADI JESD204B/C designs.

    This is a pre-flight sanity check for XSA pipeline cfg dicts: a
    mistyped ``F`` or swapped ``M``/``L`` usually boots far enough that
    the failure only surfaces at ILAS training, which is hard to debug
    on hardware.  Run it at test/CLI entry so obvious cfg typos fail
    fast with a clear message.
    """
    warnings: list[str] = []
    for side in ("rx", "tx"):
        sub = jesd_cfg.get(side)
        if not isinstance(sub, dict):
            continue
        M = sub.get("M")
        L = sub.get("L")
        F = sub.get("F")
        Np = sub.get("Np", 16)
        S = sub.get("S", 1)
        if None in (M, L, F):
            continue
        if L == 0 or (M * Np * S) % (8 * L) != 0:
            warnings.append(
                f"jesd.{side}: M*Np*S / (8*L) = {M}*{Np}*{S}/(8*{L}) is "
                f"not an integer; F={F} cannot match."
            )
            continue
        expected_F = (M * Np * S) // (8 * L)
        if expected_F != F:
            warnings.append(
                f"jesd.{side}: F={F} != M*Np*S/(8*L) = "
                f"{M}*{Np}*{S}/(8*{L}) = {expected_F}"
            )
    return warnings


def shell_out(shell, cmd: str) -> str:
    """Run *cmd* via an ``ADIShellDriver`` and return the output as a string.

    Args:
        shell: An ``ADIShellDriver`` instance whose ``run`` method executes
            shell commands on the target board.
        cmd: Shell command string to execute.

    Returns:
        Command output as a single newline-joined string.
    """
    res = shell.run(cmd)
    out = res[0] if isinstance(res, tuple) else res
    if isinstance(out, list):
        return "\n".join(out)
    return str(out)


def acquire_xsa(
    local_xsa: Path,
    release: str,
    project: str,
    tmp_path: Path,
) -> Path:
    """Return *local_xsa* if it exists, otherwise download from Kuiper release."""
    if local_xsa.exists():
        return local_xsa
    from test.xsa.kuiper_release import download_project_xsa

    return download_project_xsa(
        release=release,
        project_dir=project,
        cache_dir=tmp_path / "kuiper_cache",
        output_dir=tmp_path / "xsa",
    )


def deploy_and_boot(board, dtb: Path, kernel_image: Path | None = None):
    """Push DTB (+ optional kernel) via ``KuiperDLDriver`` and transition to shell.

    Returns the ``ADIShellDriver`` handle.
    """
    kuiper = board.target.get_driver("KuiperDLDriver")
    kuiper.get_boot_files_from_release()
    if kernel_image is not None:
        kuiper.add_files_to_target(kernel_image)
    kuiper.add_files_to_target(dtb)
    board.transition("shell")
    return board.target.get_driver("ADIShellDriver")


def collect_dmesg(
    shell,
    out_dir: Path,
    label: str,
    grep_pattern: str | None = None,
) -> str:
    """Snapshot full dmesg + err-level dmesg to ``out_dir`` and return full text.

    Also prints ``ls /sys/bus/spi/devices`` and an optional
    ``dmesg | grep -Ei <grep_pattern>`` tail for diagnostics.
    """
    dmesg_log = out_dir / f"dmesg_{label}.log"
    dmesg_txt = shell_out(shell, "dmesg")
    dmesg_log.write_text(dmesg_txt)

    err_log = out_dir / f"dmesg_{label}_err.log"
    err_log.write_text(shell_out(shell, "dmesg --level=err,warn"))
    print(f"Saved dmesg logs: {dmesg_log} and {err_log}")

    diag_cmds = ["ls /sys/bus/spi/devices"]
    if grep_pattern:
        diag_cmds.append(f"dmesg | grep -Ei '{grep_pattern}' | tail -n 200")
    for cmd in diag_cmds:
        print(f"$ {cmd}")
        print(shell_out(shell, cmd))
    return dmesg_txt


def open_iio_context(shell):
    """Return ``(iio.Context, ip_address)`` for the booted target."""
    import iio

    ip_addresses = shell.get_ip_addresses()
    assert ip_addresses, "ADIShellDriver could not report a board IP address"
    ip_address = str(ip_addresses[0].ip).split("/")[0]
    print(f"Using IP address for IIO context: {ip_address}")
    ctx = iio.Context(f"ip:{ip_address}")
    assert ctx is not None, "Failed to create IIO context"
    return ctx, ip_address


def read_jesd_status(
    shell,
    rx_glob: str = "*.axi[_-]jesd204[_-]rx",
    tx_glob: str = "*.axi[_-]jesd204[_-]tx",
) -> tuple[str, str]:
    """Return ``(rx_status, tx_status)`` from the platform-device sysfs nodes."""
    rx_status = shell_out(
        shell,
        f"cat /sys/bus/platform/devices/{rx_glob}/status 2>/dev/null "
        "| head -n 20 || true",
    )
    tx_status = shell_out(
        shell,
        f"cat /sys/bus/platform/devices/{tx_glob}/status 2>/dev/null "
        "| head -n 20 || true",
    )
    return rx_status, tx_status


def assert_jesd_links_data(
    shell,
    context: str = "",
    rx_glob: str = "*.axi[_-]jesd204[_-]rx",
    tx_glob: str = "*.axi[_-]jesd204[_-]tx",
) -> tuple[str, str]:
    """Read RX + TX JESD status and assert both show ``Link status: DATA``."""
    rx_status, tx_status = read_jesd_status(shell, rx_glob, tx_glob)
    suffix = f" ({context})" if context else ""
    assert "Link status: DATA" in rx_status, (
        f"RX JESD link not in DATA{suffix}:\n{rx_status}"
    )
    assert "Link status: DATA" in tx_status, (
        f"TX JESD link not in DATA{suffix}:\n{tx_status}"
    )
    return rx_status, tx_status


def assert_rx_capture_valid(
    ctx,
    device_candidates: str | tuple[str, ...],
    n_samples: int = 2**12,
    min_std: float = 1.0,
    context: str = "",
) -> dict:
    """Capture ``n_samples`` from an IIO device and verify data is flowing.

    Covers the "IIO device probed but no samples actually arrive" failure
    mode: the JESD204 link reports DATA, drivers probe cleanly, IIO
    devices appear, but the DMA / JESD transport / clock path silently
    stops delivering samples.  The buffer comes back, but every sample
    is zero, or every sample is latched to one value.

    Asserts:

    - At least one RX channel is not all-zero (DMA actually transferred
      bytes).
    - At least one RX channel's |std| is ``>= min_std`` LSBs (samples
      actually vary — noise floor alone clears this threshold easily,
      but a latched converter does not).

    Uses raw libiio so it works with any buffered IIO device, including
    AD9081 designs that expose the buffered frontend as the TPL core
    (``ad_ip_jesd204_tpl_adc``) rather than ``axi-ad9081-rx-hpc``.

    Args:
        ctx: A live ``iio.Context`` (e.g. from :func:`open_iio_context`).
        device_candidates: IIO device name to capture from, or a tuple
            of candidate names — the first one present on *ctx* wins.
        n_samples: buffer depth for the capture.
        min_std: minimum |std| across all channels, in raw-LSB units.
        context: tag prepended to assertion-failure messages.

    Returns:
        ``dict`` mapping channel id → captured ``numpy.ndarray``.
    """
    import iio
    import numpy as np

    suffix = f" ({context})" if context else ""
    candidates = (
        (device_candidates,)
        if isinstance(device_candidates, str)
        else tuple(device_candidates)
    )
    all_names = sorted(d.name for d in ctx.devices if d.name)

    def _has_rx_scan(d):
        return any(c.scan_element and not c.output for c in d.channels)

    dev = next(
        (d for d in (ctx.find_device(n) for n in candidates) if d is not None), None
    )
    if dev is None or not _has_rx_scan(dev):
        # No named candidate is RX-buffered — fall back to the first
        # *AXI DMA frontend* on the context (name starts with ``axi-`` /
        # ``cf-`` or contains ``tpl``).  Control-plane devices like
        # ``ad9528`` or ``ad9371-phy`` may expose scan channels too, but
        # they aren't wired to an AXI-DMA and ``buf.refill()`` would just
        # time out on them.
        buffered = [
            d
            for d in ctx.devices
            if d.name
            and (
                d.name.startswith("axi-") or d.name.startswith("cf-") or "tpl" in d.name
            )
            and _has_rx_scan(d)
        ]
        dev = buffered[0] if buffered else None
    assert dev is not None, (
        f"No RX-buffered IIO device found{suffix}. "
        f"Tried: {list(candidates)}. Present: {all_names}"
    )

    scan_channels = [c for c in dev.channels if c.scan_element and not c.output]
    assert scan_channels, (
        f"No RX scan channels on {dev.name!r}{suffix}. Present: {all_names}"
    )

    print(f"rx capture{suffix}: selected IIO device {dev.name!r}")
    buf = None
    try:
        for ch in scan_channels:
            ch.enabled = True
        buf = iio.Buffer(dev, n_samples, False)
        try:
            buf.refill()
        except TimeoutError as exc:
            raise AssertionError(
                f"Buffer refill timed out on {dev.name!r}{suffix} — "
                "AXI DMA is not delivering samples (JESD or DMA path "
                "stalled).  Present devices: " + ", ".join(all_names)
            ) from exc
        per_channel: dict[str, np.ndarray] = {}
        for ch in scan_channels:
            raw = ch.read(buf)
            # AXI ADC frontends emit signed int16 (or sign-extended
            # int14/int12); dtype=int16 is correct for every chip this
            # suite currently runs against.
            per_channel[ch.id] = np.frombuffer(raw, dtype=np.int16)
    finally:
        if buf is not None:
            del buf
        for ch in scan_channels:
            try:
                ch.enabled = False
            except Exception:
                pass

    nonzero = [name for name, arr in per_channel.items() if arr.any()]
    assert nonzero, (
        f"All channels on {dev.name!r} returned zero samples{suffix} — "
        "JESD/DMA/clock path is likely stalled."
    )

    stds = {name: float(np.abs(arr).std()) for name, arr in per_channel.items()}
    max_std = max(stds.values())
    assert max_std >= min_std, (
        f"All channels on {dev.name!r} latched to a constant value{suffix} "
        f"(max |std|={max_std:.3g} < {min_std}) — data path stuck."
    )

    print(
        f"rx capture{suffix}: device={dev.name}, "
        f"{len(per_channel)} channel(s), {n_samples} samples, "
        f"non-zero={list(nonzero)}, max |std|={max_std:.2f}"
    )
    return per_channel


def _kernel_cache_key(platform_arch: str, config_path: Path) -> str:
    """Return a short sha256 over *platform_arch* and the config file bytes."""
    import hashlib

    h = hashlib.sha256()
    h.update(platform_arch.encode())
    h.update(b"\0")
    h.update(config_path.read_bytes())
    return h.hexdigest()[:16]


def _cached_kernel_dir(platform_arch: str, config_path: Path) -> Path:
    """Return the per-(platform, config-hash) directory holding a cached kernel."""
    return (
        KERNEL_CACHE_DIR / platform_arch / _kernel_cache_key(platform_arch, config_path)
    )


def _find_cached_kernel(platform_arch: str, config_path: Path) -> Path | None:
    """Return the path to a cached kernel image, preserving the original basename.

    The first non-empty regular file under the cache directory is returned so
    that the filename the boot strategy/TFTP layer consumes (``uImage``,
    ``zImage``, ``Image``, …) matches what ``pyadi-build`` produced.
    """
    cache_dir = _cached_kernel_dir(platform_arch, config_path)
    if not cache_dir.is_dir():
        return None
    for entry in sorted(cache_dir.iterdir()):
        if entry.is_file() and entry.stat().st_size > 0:
            return entry
    return None


def build_kernel_image(platform_arch: str) -> Path | None:
    """Build a Linux kernel image using ``pyadi-build`` for *platform_arch*.

    Caches the built image under ``KERNEL_CACHE_DIR`` keyed by the SHA-256
    of the config YAML — subsequent runs for the same (platform, config)
    skip the pyadi-build ``prepare_source`` + ``build`` cycle entirely.
    Set ``ADIDT_KERNEL_CACHE=0`` to force a rebuild, or
    ``ADIDT_KERNEL_CACHE_DIR`` to relocate the cache.

    Args:
        platform_arch: ``"zynqmp"`` for ZynqMP / ZCU102 targets, or
            ``"zynq"`` for Zynq-7000 / ZC706 targets.

    Returns:
        Path to the built (or cached) kernel image, or ``None`` if
        :data:`DEFAULT_BUILD_KERNEL` is ``False``.

    Raises:
        ValueError: for unknown *platform_arch* values.
        RuntimeError: if the build produced no kernel image or the resulting
            file does not exist on disk.
    """
    # Allow tests to bypass the pyadi-build dependency by pointing at a
    # pre-built kernel image — useful in environments without the
    # private pyadi-build package, or for fast iteration when the kernel
    # is already known-good (e.g. matching a Kuiper sdcard image).
    override_var = f"ADIDT_KERNEL_IMAGE_{platform_arch.upper()}"
    override = os.environ.get(override_var)
    if override:
        path = Path(override)
        if not path.is_file():
            pytest.skip(f"{override_var}={override!s} does not exist")
        print(f"Using pre-built {platform_arch} kernel image from {override_var}: {path}")
        return path

    if not DEFAULT_BUILD_KERNEL:
        return None

    config_path = HERE / "2023_R2.yaml"
    if not config_path.exists():
        pytest.skip(f"pyadi-build config not found: {config_path}")

    if DEFAULT_KERNEL_CACHE:
        cached = _find_cached_kernel(platform_arch, config_path)
        if cached is not None:
            print(f"Reusing cached {platform_arch} kernel image: {cached}")
            return cached

    try:
        from adibuild import BuildConfig, LinuxBuilder
    except ModuleNotFoundError as ex:
        pytest.skip(f"pyadi-build dependency missing: {ex}")

    config = BuildConfig.from_yaml(config_path)
    if platform_arch == "zynqmp":
        from adibuild.platforms import ZynqMPPlatform

        platform_cfg = config.get_platform("zynqmp")
        platform = ZynqMPPlatform(platform_cfg)
    elif platform_arch == "zynq":
        from adibuild.platforms import ZynqPlatform

        platform_cfg = config.get_platform("zynq")
        platform = ZynqPlatform(platform_cfg)
    else:
        raise ValueError(f"Unknown platform arch: {platform_arch!r}")

    builder = LinuxBuilder(config, platform)
    builder.prepare_source()
    result = builder.build(clean_before=False)

    kernel = result.get("kernel_image")
    if not kernel:
        raise RuntimeError(f"pyadi-build returned no kernel image: {result}")
    kernel_path = Path(kernel)
    if not kernel_path.exists():
        raise RuntimeError(f"Built kernel image not found: {kernel_path}")

    # Zynq-7000 U-Boot boots via ``bootm`` which requires a U-Boot-format
    # ``uImage`` (zImage + legacy header).  pyadi-build emits a raw
    # ``zImage``; wrap it with ``mkimage`` so the boot strategy finds the
    # filename it expects.
    if platform_arch == "zynq" and kernel_path.name == "zImage":
        kernel_path = _wrap_zimage_as_uimage(kernel_path)

    if DEFAULT_KERNEL_CACHE:
        cache_dir = _cached_kernel_dir(platform_arch, config_path)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached = cache_dir / kernel_path.name
        shutil.copyfile(kernel_path, cached)
        print(f"Cached {platform_arch} kernel image: {kernel_path} -> {cached}")
        return cached
    return kernel_path


def _wrap_zimage_as_uimage(zimage: Path) -> Path:
    """Wrap a Zynq-7000 ``zImage`` as a U-Boot ``uImage`` using ``mkimage``.

    Load/entry use the canonical Zynq-7000 offset ``0x8000``.  The produced
    ``uImage`` lives in the same directory as the source ``zImage``.
    """
    if shutil.which("mkimage") is None:
        raise RuntimeError(
            "mkimage not found on PATH; install u-boot-tools to build uImage"
        )
    uimage = zimage.with_name("uImage")
    cmd = [
        "mkimage",
        "-A",
        "arm",
        "-O",
        "linux",
        "-T",
        "kernel",
        "-C",
        "none",
        "-a",
        "0x8000",
        "-e",
        "0x8000",
        "-n",
        "Linux Kernel",
        "-d",
        str(zimage),
        str(uimage),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"mkimage failed:\n{res.stdout}\n{res.stderr}")
    return uimage
