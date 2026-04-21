"""Shared helpers and constants for XSA hardware integration tests."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

import re as _re

HERE = Path(__file__).parent


def _dedup_root_nodes(pp_dts: Path) -> None:
    """Remove the duplicate sdtgen root block from a preprocessed ZynqMP DTS.

    sdtgen for ZynqMP generates ``system-top.dts`` that ``#include``s
    ``zynqmp.dtsi``, ``zynqmp-clk-ccf.dtsi``, and ``pl.dtsi``.  After
    ``cpp`` preprocessing, the file has 4 ``/ { ... };`` blocks:

    - Block 0: ``zynqmp.dtsi`` (canonical A53 CPU, peripherals, clocks)
    - Block 1: ``zynqmp-clk-ccf.dtsi`` (PS reference clock)
    - Block 2: ``pl.dtsi`` (FPGA PL bus with all AXI IPs)
    - Block 3: ``system-top.dts`` (sdtgen re-declaration of cpus, amba_pl, etc.)

    Block 3 duplicates everything already defined in Blocks 0-2 and causes
    ``dtc`` ``duplicate_node_names`` errors.  Remove it entirely — the
    content after Block 3 (overlay ``&label { ... }`` references from the
    merger) is preserved.
    """
    import re

    text = pp_dts.read_text()

    # Find all "/ {" block positions using brace counting
    root_re = re.compile(r"^/ \{", re.M)
    root_blocks: list[tuple[int, int]] = []
    for m in root_re.finditer(text):
        start = m.start()
        depth = 0
        for i in range(m.end() - 1, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    if end < len(text) and text[end] == ";":
                        end += 1
                    if end < len(text) and text[end] == "\n":
                        end += 1
                    root_blocks.append((start, end))
                    break

    # Remove the last root block when there are 4+ (the ZynqMP sdtgen pattern).
    # Block 3 (system-top.dts) re-declares everything from Blocks 0-2.
    # BUT preserve `chosen` and `aliases` nodes which only exist in Block 3
    # and are required for console output and device aliasing.
    if len(root_blocks) >= 4:
        last_start, last_end = root_blocks[-1]
        last_block = text[last_start:last_end]

        # Extract chosen and aliases sub-nodes from the removed block
        preserved: list[str] = []
        for node_name in ("chosen", "aliases"):
            node_re = re.compile(
                rf"^ {node_name}\b[^\{{]*\{{.*?^ \}};",
                re.M | re.S,
            )
            m = node_re.search(last_block)
            if m:
                preserved.append(m.group())

        text = text[:last_start] + text[last_end:]

        # Re-insert preserved nodes in a new root block
        if preserved:
            preserved_block = "/ {\n" + "\n".join(preserved) + "\n};\n"
            # Insert before any overlay &label references at end of file
            text = text.rstrip() + "\n\n" + preserved_block + "\n"

    # Rename "cpus_microblaze_0: cpus {" → "cpus_microblaze_0: cpus-pmu {"
    # to avoid conflict with "cpus_a53: cpus" from zynqmp.dtsi.
    # The MicroBlaze PMU CPU node is only used for address-map metadata.
    text = text.replace(
        "cpus_microblaze_0: cpus {",
        "cpus_microblaze_0: cpus-pmu {",
    )

    pp_dts.write_text(text)


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
        _dedup_root_nodes(compile_input)

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
