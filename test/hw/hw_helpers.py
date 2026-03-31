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
    if len(root_blocks) >= 4:
        last_start, last_end = root_blocks[-1]
        text = text[:last_start] + text[last_end:]

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


def build_kernel_image(platform_arch: str) -> Path | None:
    """Build a Linux kernel image using ``pyadi-build`` for *platform_arch*.

    Args:
        platform_arch: ``"zynqmp"`` for ZynqMP / ZCU102 targets, or
            ``"zynq"`` for Zynq-7000 / ZC706 targets.

    Returns:
        Path to the built kernel image, or ``None`` if
        :data:`DEFAULT_BUILD_KERNEL` is ``False``.

    Raises:
        ValueError: for unknown *platform_arch* values.
        RuntimeError: if the build produced no kernel image or the resulting
            file does not exist on disk.
    """
    if not DEFAULT_BUILD_KERNEL:
        return None

    try:
        from adibuild import BuildConfig, LinuxBuilder
    except ModuleNotFoundError as ex:
        pytest.skip(f"pyadi-build dependency missing: {ex}")

    config_path = HERE / "2023_R2.yaml"
    if not config_path.exists():
        pytest.skip(f"pyadi-build config not found: {config_path}")

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
    return kernel_path
