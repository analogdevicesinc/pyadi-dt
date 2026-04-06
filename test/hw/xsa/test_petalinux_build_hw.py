"""PetaLinux full-build integration tests.

Exercises the complete PetaLinux workflow:
  XSA → petalinux-create → petalinux-config → pyadi-dt system-user.dtsi →
  petalinux-build -c device-tree → verify DTB

Requirements:
  - PetaLinux tools on PATH (petalinux-create, petalinux-config, petalinux-build)
  - XSA file (via PETALINUX_XSA env var or Kuiper release download)
  - Sufficient disk space (~10 GB for PetaLinux project)

Environment variables:
  PETALINUX_XSA:       Path to XSA file (skips Kuiper download when set)
  PETALINUX_TEMPLATE:  PetaLinux template (default: zynqMP)
  PETALINUX_PROFILE:   pyadi-dt profile name (default: auto-detect)
  PETALINUX_VERSION:   PetaLinux version string (default: None, assumes >= 2020.1)
  PETALINUX_CONFIG_JSON: Path to pyadi-dt config JSON (default: {})
  ADI_KUIPER_BOOT_RELEASE: Kuiper release for XSA download (default: 2023_r2)
  ADI_KUIPER_XSA_PROJECT:  Kuiper project dir for XSA download

Usage:
  PETALINUX_XSA=/path/to/design.xsa pytest test/hw/xsa/test_petalinux_build_hw.py -v
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

# Skip entire module if PetaLinux tools are not available
if shutil.which("petalinux-create") is None:
    pytest.skip(
        "petalinux-create not found on PATH (PetaLinux tools required)",
        allow_module_level=True,
    )


def _require_tool(name: str) -> str:
    """Return the path to a tool or skip the test."""
    path = shutil.which(name)
    if path is None:
        pytest.skip(f"{name} not found on PATH")
    return path


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 600) -> str:
    """Run a command, return stdout, fail on non-zero exit."""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        pytest.fail(
            f"Command failed: {' '.join(cmd)}\n"
            f"returncode: {result.returncode}\n"
            f"stdout: {result.stdout[-2000:]}\n"
            f"stderr: {result.stderr[-2000:]}"
        )
    return result.stdout


def _resolve_xsa(tmp_path: Path) -> Path:
    """Resolve the XSA path from env var or Kuiper download."""
    env_xsa = os.environ.get("PETALINUX_XSA")
    if env_xsa:
        xsa = Path(env_xsa)
        if not xsa.exists():
            pytest.fail(f"PETALINUX_XSA file not found: {xsa}")
        return xsa

    # Fall back to Kuiper release download
    release = os.environ.get("ADI_KUIPER_BOOT_RELEASE", "2023_r2")
    project = os.environ.get("ADI_KUIPER_XSA_PROJECT")
    if not project:
        pytest.skip(
            "Set PETALINUX_XSA or ADI_KUIPER_XSA_PROJECT to provide an XSA file"
        )

    try:
        from test.xsa.kuiper_release import download_project_xsa
    except ImportError:
        pytest.skip("adi-labgrid-plugins required for Kuiper XSA download")

    return download_project_xsa(
        release=release,
        project_dir=project,
        cache_dir=tmp_path / "kuiper_cache",
        output_dir=tmp_path / "xsa",
    )


@pytest.fixture(scope="module")
def xsa_path(tmp_path_factory):
    """Resolve the XSA file for PetaLinux tests."""
    tmp = tmp_path_factory.mktemp("petalinux_xsa")
    return _resolve_xsa(tmp)


@pytest.fixture(scope="module")
def petalinux_project(xsa_path, tmp_path_factory):
    """Create and configure a PetaLinux project from the XSA.

    This fixture is module-scoped so the project is reused across tests
    within the module (creating a PetaLinux project takes several minutes).
    """
    _require_tool("petalinux-create")
    _require_tool("petalinux-config")

    template = os.environ.get("PETALINUX_TEMPLATE", "zynqMP")
    tmp = tmp_path_factory.mktemp("petalinux_project")
    project_dir = tmp / "adi_test_project"

    # Create project
    _run(
        [
            "petalinux-create",
            "--type",
            "project",
            "--template",
            template,
            "--name",
            project_dir.name,
        ],
        cwd=tmp,
        timeout=120,
    )
    assert project_dir.exists(), f"petalinux-create did not create {project_dir}"

    # Import hardware description (XSA)
    _run(
        [
            "petalinux-config",
            "--get-hw-description",
            str(xsa_path.parent),
            "--silentconfig",
        ],
        cwd=project_dir,
        timeout=600,
    )

    # Verify expected directory structure
    dt_files = (
        project_dir
        / "project-spec"
        / "meta-user"
        / "recipes-bsp"
        / "device-tree"
        / "files"
    )
    assert dt_files.is_dir(), (
        f"PetaLinux project missing device-tree/files directory: {dt_files}"
    )

    return project_dir


def test_petalinux_project_created(petalinux_project):
    """Verify the PetaLinux project was created and configured."""
    assert petalinux_project.exists()
    assert (petalinux_project / "project-spec").is_dir()
    assert (petalinux_project / "project-spec" / "meta-user").is_dir()


def test_inject_system_user_dtsi(petalinux_project, xsa_path):
    """Generate system-user.dtsi via pyadi-dt and inject into PetaLinux project."""
    from adidt.xsa.pipeline import XsaPipeline
    from adidt.xsa.petalinux import validate_petalinux_project

    validate_petalinux_project(petalinux_project)

    config_path = os.environ.get("PETALINUX_CONFIG_JSON")
    if config_path:
        cfg = json.loads(Path(config_path).read_text())
    else:
        cfg = {}

    profile = os.environ.get("PETALINUX_PROFILE")
    out_dir = petalinux_project / "pyadi_dt_output"
    out_dir.mkdir(exist_ok=True)

    result = XsaPipeline().run(
        xsa_path=xsa_path,
        cfg=cfg,
        output_dir=out_dir,
        sdtgen_timeout=300,
        profile=profile,
        output_format="petalinux",
    )

    assert "system_user_dtsi" in result
    assert "bbappend" in result

    dtsi_src = result["system_user_dtsi"]
    bbappend_src = result["bbappend"]
    assert dtsi_src.exists()
    assert bbappend_src.exists()

    # Verify content sanity
    dtsi_content = dtsi_src.read_text()
    assert "/dts-v1/;" not in dtsi_content
    assert "/plugin/;" not in dtsi_content
    assert '#include "system-conf.dtsi"' in dtsi_content

    # Install into PetaLinux project
    dt_files = (
        petalinux_project
        / "project-spec"
        / "meta-user"
        / "recipes-bsp"
        / "device-tree"
        / "files"
    )
    dt_recipe = dt_files.parent

    # Back up existing system-user.dtsi
    dest_dtsi = dt_files / "system-user.dtsi"
    if dest_dtsi.exists():
        shutil.copy2(dest_dtsi, dt_files / "system-user.dtsi.orig")

    shutil.copy2(dtsi_src, dest_dtsi)
    shutil.copy2(bbappend_src, dt_recipe / "device-tree.bbappend")

    assert dest_dtsi.exists()
    assert (dt_recipe / "device-tree.bbappend").exists()


def test_petalinux_build_device_tree(petalinux_project):
    """Run petalinux-build -c device-tree and verify DTB output."""
    _require_tool("petalinux-build")

    # Ensure system-user.dtsi was injected (depends on test ordering)
    dt_files = (
        petalinux_project
        / "project-spec"
        / "meta-user"
        / "recipes-bsp"
        / "device-tree"
        / "files"
    )
    dtsi = dt_files / "system-user.dtsi"
    if not dtsi.exists():
        pytest.skip(
            "system-user.dtsi not injected (run test_inject_system_user_dtsi first)"
        )

    # Build device tree only (much faster than full build)
    _run(
        ["petalinux-build", "-c", "device-tree"],
        cwd=petalinux_project,
        timeout=1200,  # 20 minutes max
    )

    # Check for generated DTB in PetaLinux build artifacts
    images_dir = petalinux_project / "images" / "linux"
    dtb_candidates = list(images_dir.glob("system.dtb")) if images_dir.exists() else []

    # Also check the Yocto deploy directory
    deploy_dir = petalinux_project / "build" / "tmp" / "deploy" / "images"
    if deploy_dir.exists():
        for arch_dir in deploy_dir.iterdir():
            dtb_candidates.extend(arch_dir.glob("system*.dtb"))
            dtb_candidates.extend(arch_dir.glob("*.dtb"))

    assert dtb_candidates, (
        f"No DTB files found after petalinux-build -c device-tree.\n"
        f"Checked: {images_dir}, {deploy_dir}"
    )

    # Verify at least one DTB is non-empty
    dtb_sizes = {str(p): p.stat().st_size for p in dtb_candidates}
    non_empty = {k: v for k, v in dtb_sizes.items() if v > 0}
    assert non_empty, f"All DTB files are empty: {dtb_sizes}"


def test_petalinux_dtb_contains_adi_nodes(petalinux_project):
    """Decompile the generated DTB and verify ADI nodes are present."""
    if shutil.which("dtc") is None:
        pytest.skip("dtc not found on PATH")

    images_dir = petalinux_project / "images" / "linux"
    dtb = images_dir / "system.dtb" if images_dir.exists() else None
    if dtb is None or not dtb.exists():
        # Search in deploy directory
        deploy_dir = petalinux_project / "build" / "tmp" / "deploy" / "images"
        if deploy_dir.exists():
            for arch_dir in deploy_dir.iterdir():
                candidates = list(arch_dir.glob("system*.dtb"))
                if candidates:
                    dtb = candidates[0]
                    break
    if dtb is None or not dtb.exists():
        pytest.skip("No DTB found (run test_petalinux_build_device_tree first)")

    # Decompile DTB to DTS
    result = subprocess.run(
        ["dtc", "-I", "dtb", "-O", "dts", str(dtb)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"dtc decompile failed:\n{result.stderr[-2000:]}")

    dts = result.stdout

    # Check for ADI-specific content (at least one of these should be present)
    adi_indicators = [
        "adi,",  # ADI DT binding prefix
        "ad9523",  # Clock generators
        "ad9528",
        "hmc7044",
        "ad9081",  # Converters
        "ad9680",
        "ad9144",
        "adrv9009",
        "ad9084",
        "jesd204",  # JESD204 link nodes
        "axi-dmac",  # ADI DMA controller
    ]
    found = [ind for ind in adi_indicators if ind in dts]
    assert found, (
        f"No ADI device tree nodes found in decompiled DTB.\n"
        f"Checked for: {adi_indicators}\n"
        f"DTB path: {dtb}\n"
        f"DTS snippet (first 2000 chars): {dts[:2000]}"
    )


def test_petalinux_full_build(petalinux_project):
    """Run a full petalinux-build and verify boot artifacts.

    This test is very slow (30-60 minutes) and produces a full Linux image.
    It is separated from the device-tree-only build so it can be selected
    or skipped independently.
    """
    if not os.environ.get("PETALINUX_FULL_BUILD"):
        pytest.skip(
            "Set PETALINUX_FULL_BUILD=1 to run the full PetaLinux build "
            "(takes 30-60 minutes)"
        )

    _require_tool("petalinux-build")
    _require_tool("petalinux-package")

    # Full build
    _run(
        ["petalinux-build"],
        cwd=petalinux_project,
        timeout=3600,  # 60 minutes max
    )

    images_dir = petalinux_project / "images" / "linux"
    assert images_dir.exists(), f"images/linux not found after full build"

    # Check for key boot artifacts
    expected_artifacts = ["system.dtb", "BOOT.BIN", "image.ub"]
    found_artifacts = [f.name for f in images_dir.iterdir() if f.is_file()]

    # At least DTB and kernel image should exist
    assert any(a in found_artifacts for a in ["system.dtb", "devicetree.dtb"]), (
        f"No DTB in {images_dir}. Found: {found_artifacts}"
    )

    assert any(
        a in found_artifacts for a in ["Image", "image.ub", "uImage", "zImage"]
    ), f"No kernel image in {images_dir}. Found: {found_artifacts}"

    # Package BOOT.BIN
    _run(
        [
            "petalinux-package",
            "--boot",
            "--force",
            "--fsbl",
            "images/linux/zynqmp_fsbl.elf",
            "--fpga",
            "images/linux/system.bit",
            "--u-boot",
        ],
        cwd=petalinux_project,
        timeout=300,
    )

    boot_bin = images_dir / "BOOT.BIN"
    assert boot_bin.exists(), f"BOOT.BIN not produced by petalinux-package"
    assert boot_bin.stat().st_size > 0, "BOOT.BIN is empty"
