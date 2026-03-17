"""Shared helpers and constants for XSA hardware integration tests."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).parent
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

    res = subprocess.run(
        ["dtc", "-I", "dts", "-O", "dtb", "-o", str(dtb_path), str(compile_input)],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(f"dtc failed:\n{res.stderr}")


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
    """Run *cmd* via an ``ADIShellDriver`` and return the output as a string."""
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
