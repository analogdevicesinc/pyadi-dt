"""PetaLinux variant of the merged-DTB hardware test harness.

The XSA hw tests in ``test/hw/test_*_xsa_hw.py`` exercise the pyadi-dt
overlay through the Xilinx ``sdtgen``/lopper path: parse XSA → render
overlay → merge with sdtgen base DTS → ``dtc`` → boot.  The PetaLinux
variant runs the same overlay through PetaLinux's own DTG instead:

    XSA → petalinux-create → petalinux-config --get-hw-description
        → pyadi-dt ``XsaPipeline.run(output_format="petalinux")``
        → install ``system-user.dtsi`` + ``device-tree.bbappend``
        → petalinux-build -c device-tree
        → ``images/linux/system.dtb``
        → boot via labgrid (Kuiper kernel + rootfs)
        → standard verify (no kernel faults, IIO probe, JESD DATA, RX capture)

A board test module declares the same :class:`BoardSystemProfile` it uses
for its XSA variant (typically with a renamed ``out_label``) and calls
:func:`run_petalinux_build_and_verify`.  The boot+verify half is delegated
to :func:`boot_and_verify_from_dtb` so the two variants share post-DTB
behavior bit-for-bit.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping, Optional

import pytest

from adidt.xsa.merge.petalinux import validate_petalinux_project
from adidt.xsa.pipeline import XsaPipeline
from adidt.xsa.parse.topology import XsaParser
from test.hw._system_base import (
    BoardSystemProfile,
    acquire_or_local_xsa,
    boot_and_verify_from_dtb,
    local_xsa_or_skip,
    requires_lg,
)
from test.hw.hw_helpers import DEFAULT_OUT_DIR


__all__ = [
    "acquire_or_local_xsa",
    "BoardSystemProfile",
    "local_xsa_or_skip",
    "requires_lg",
    "requires_petalinux",
    "run_petalinux_build_and_verify",
]


_DEFAULT_PETALINUX_INSTALL = "/opt/Xilinx/PetaLinux/2023.2"


DEFAULT_PROJECT_CACHE = os.environ.get(
    "PETALINUX_PROJECT_CACHE", "1"
).lower() not in {"0", "false", "no"}

PROJECT_CACHE_DIR = Path(
    os.environ.get(
        "PETALINUX_PROJECT_CACHE_DIR",
        str(Path.home() / ".cache" / "adidt" / "petalinux"),
    )
)


def _has_petalinux_install() -> bool:
    install = Path(os.environ.get("PETALINUX_INSTALL", _DEFAULT_PETALINUX_INSTALL))
    if (install / "settings.sh").is_file():
        return True
    return shutil.which("petalinux-create") is not None


requires_petalinux = pytest.mark.skipif(
    not _has_petalinux_install(),
    reason=(
        "PetaLinux install not found.  Set PETALINUX_INSTALL to the "
        "PetaLinux 2023.2+ install root (containing settings.sh) "
        "or ensure petalinux-create is on PATH."
    ),
)


def _resolve_petalinux_install(spec: BoardSystemProfile) -> Path:
    install = Path(
        os.environ.get(spec.petalinux_install_env, _DEFAULT_PETALINUX_INSTALL)
    )
    if not (install / "settings.sh").is_file():
        # Tools may be on PATH already; we'll let _petalinux_env handle it.
        if shutil.which("petalinux-create") is None:
            pytest.skip(
                f"PetaLinux install not found: {install}/settings.sh missing "
                f"and petalinux-create not on PATH"
            )
    return install


_ENV_CACHE: dict[str, dict[str, str]] = {}


def _petalinux_env(install: Path) -> dict[str, str]:
    """Return the environment variables that ``source settings.sh`` sets.

    Cached per install path for the lifetime of the pytest session.  Falls
    back to the current environment when ``settings.sh`` is missing (for
    setups where the user has already sourced it in their shell).
    """
    key = str(install)
    cached = _ENV_CACHE.get(key)
    if cached is not None:
        return cached

    settings = install / "settings.sh"
    if not settings.is_file():
        env = dict(os.environ)
        _ENV_CACHE[key] = env
        return env

    cmd = ["bash", "-lc", f"source {settings} && env -0"]
    result = subprocess.run(
        cmd,
        capture_output=True,
        check=True,
        timeout=120,
    )
    env: dict[str, str] = {}
    for entry in result.stdout.split(b"\x00"):
        if not entry:
            continue
        try:
            text = entry.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if "=" not in text:
            continue
        k, _, v = text.partition("=")
        env[k] = v
    _ENV_CACHE[key] = env
    return env


def _pl_run(
    cmd: list[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: int,
    label: str,
) -> str:
    """Run a PetaLinux subprocess; on non-zero, fail the test with tail logs."""
    print(f"$ ({label}) {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=dict(env),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        pytest.fail(
            f"PetaLinux step failed: {label}\n"
            f"cmd: {' '.join(cmd)}\n"
            f"cwd: {cwd}\n"
            f"returncode: {result.returncode}\n"
            f"stdout (last 4 KB):\n{result.stdout[-4096:]}\n"
            f"stderr (last 4 KB):\n{result.stderr[-4096:]}"
        )
    return result.stdout


def _xsa_sha256(xsa_path: Path) -> str:
    h = hashlib.sha256()
    with xsa_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _template_for_boot_mode(boot_mode: str) -> str:
    if boot_mode == "sd":
        return "zynqMP"
    if boot_mode == "tftp":
        return "zynq"
    raise ValueError(
        f"cannot infer petalinux template for boot_mode={boot_mode!r}; "
        "set spec.petalinux_template explicitly"
    )


def _petalinux_project_root(xsa_path: Path, *, template: str) -> Path:
    return PROJECT_CACHE_DIR / template / _xsa_sha256(xsa_path) / "proj"


def _project_is_created(project_dir: Path) -> bool:
    """Return True if ``petalinux-create`` already produced this project."""
    return (project_dir / "project-spec").is_dir()


def _project_has_hw(project_dir: Path) -> bool:
    """Return True if ``petalinux-config --get-hw-description`` already ran.

    PetaLinux 2023.2 stages the imported XSA at
    ``project-spec/hw-description/system.xsa`` regardless of the source
    XSA filename — so its presence is a reliable indicator that the
    hw-description step completed successfully.
    """
    return (
        project_dir / "project-spec" / "hw-description" / "system.xsa"
    ).is_file()


def _petalinux_create(
    install: Path,
    project_dir: Path,
    template: str,
    *,
    env: Mapping[str, str],
) -> None:
    """Create a fresh PetaLinux project at *project_dir* if absent."""
    if _project_is_created(project_dir):
        return
    parent = project_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    # ``petalinux-create`` refuses to write into an existing directory; if a
    # half-baked tree from a prior failed run is present, clear it first.
    if project_dir.exists():
        shutil.rmtree(project_dir)
    # PetaLinux 2023.2 ``petalinux-create`` writes into the current
    # working directory; there is no ``-o`` flag.  ``cwd=parent`` controls
    # where the project tree is created.
    _pl_run(
        [
            "petalinux-create",
            "-t",
            "project",
            "--template",
            template,
            "--name",
            project_dir.name,
        ],
        cwd=parent,
        env=env,
        timeout=300,
        label="petalinux-create",
    )
    assert project_dir.exists(), (
        f"petalinux-create did not produce {project_dir}"
    )


def _petalinux_get_hw_description(
    install: Path,
    project_dir: Path,
    xsa_path: Path,
    *,
    env: Mapping[str, str],
    timeout: int = 1800,
) -> None:
    """Import the XSA into *project_dir*.

    PetaLinux scans the supplied directory for ``*.xsa`` and uses the first
    one alphabetically.  We isolate the XSA in a private ``xsa_import/``
    subdir under the project so sibling XSA files in the source location
    don't get picked up by mistake.
    """
    if _project_has_hw(project_dir):
        return
    import_dir = project_dir / "xsa_import"
    import_dir.mkdir(parents=True, exist_ok=True)
    staged_xsa = import_dir / "system_top.xsa"
    if not staged_xsa.exists() or staged_xsa.stat().st_size != xsa_path.stat().st_size:
        shutil.copy2(xsa_path, staged_xsa)
    _pl_run(
        [
            "petalinux-config",
            f"--get-hw-description={import_dir}",
            "--silentconfig",
        ],
        cwd=project_dir,
        env=env,
        timeout=timeout,
        label="petalinux-config --get-hw-description",
    )
    assert _project_has_hw(project_dir), (
        "petalinux-config --get-hw-description ran but "
        "project-spec/hw-description/system.xsa was not created"
    )


def _install_pyadi_outputs(
    project_dir: Path,
    system_user_dtsi: Path,
    bbappend: Path,
) -> None:
    """Copy pyadi-dt outputs into the PetaLinux device-tree recipe.

    Mirrors ``adidt/cli/main.py`` install behavior: backs up an existing
    ``system-user.dtsi`` to ``.bak`` once, then ``shutil.copy2`` (preserves
    mtime so identical re-installs do not invalidate the bitbake cache).
    Skips the copy entirely when source bytes already match destination.
    """
    validate_petalinux_project(project_dir)
    dt_recipe = project_dir / "project-spec" / "meta-user" / "recipes-bsp" / "device-tree"
    dt_files = dt_recipe / "files"
    dt_files.mkdir(parents=True, exist_ok=True)

    dest_dtsi = dt_files / "system-user.dtsi"
    backup = dt_files / "system-user.dtsi.bak"
    new_bytes = system_user_dtsi.read_bytes()
    if not dest_dtsi.exists():
        shutil.copy2(system_user_dtsi, dest_dtsi)
    elif dest_dtsi.read_bytes() != new_bytes:
        if not backup.exists():
            shutil.copy2(dest_dtsi, backup)
        shutil.copy2(system_user_dtsi, dest_dtsi)

    dest_bbappend = dt_recipe / "device-tree.bbappend"
    bbappend_bytes = bbappend.read_bytes()
    if not dest_bbappend.exists() or dest_bbappend.read_bytes() != bbappend_bytes:
        shutil.copy2(bbappend, dest_bbappend)


def _petalinux_build_dt(
    install: Path,
    project_dir: Path,
    *,
    env: Mapping[str, str],
    timeout: int = 1800,
) -> None:
    _pl_run(
        ["petalinux-build", "-c", "device-tree"],
        cwd=project_dir,
        env=env,
        timeout=timeout,
        label="petalinux-build -c device-tree",
    )


def _extract_dtb(project_dir: Path) -> Path:
    dtb = project_dir / "images" / "linux" / "system.dtb"
    assert dtb.exists() and dtb.stat().st_size > 0, (
        f"petalinux-build did not produce a non-empty DTB at {dtb}"
    )
    return dtb


def _apply_dtb_fixups(spec: BoardSystemProfile, dtb: Path) -> None:
    """Patch the produced DTB in place for known PetaLinux/board mismatches.

    PetaLinux 2023.2's stock DTG output for ZynqMP doesn't always match the
    board-level wiring assumed by the Kuiper-style boot setup we use to
    verify these tests:

    * ``/chosen/bootargs`` is hardcoded to ``"earlycon ... root=/dev/ram0
      rw"`` (driven by ``CONFIG_SUBSYSTEM_BOOTARGS_AUTO``).  Most U-Boot
      builds don't overwrite an existing ``/chosen/bootargs``, so when
      the same DTB is booted against the Kuiper SD-card rootfs the
      kernel panics with ``Unable to mount root fs on
      unknown-block(179,2)``.  Stripping the property lets U-Boot's own
      ``bootargs`` env var flow through.
    * For ZynqMP boards the ZCU102 SD slot has 3.3 V-only level
      translators; the SDHCI1 node needs ``no-1-8-v`` to prevent the
      kernel from negotiating UHS-I SDR104 at 1.8 V (the SD card then
      throws read I/O errors and the rootfs mount panics, identical
      symptom to the bootargs case).  PetaLinux's stock DTG emits the
      node without ``no-1-8-v``; add it so SDR104 is skipped.

    Both fixups are no-ops when the property/node is already in the
    desired state, so the function is safe to call unconditionally.
    """
    import fdt

    text = dtb.read_bytes()
    tree = fdt.parse_dtb(text)
    changed = False

    chosen = tree.get_node("/chosen")
    if chosen is not None and chosen.exist_property("bootargs"):
        chosen.remove_property("bootargs")
        changed = True

    if spec.boot_mode == "sd":
        # SDHCI1 lives under different bus paths depending on PetaLinux
        # template / version (e.g. ``/axi/mmc@ff170000`` in 2023.2).
        # Walk all subtrees once and patch the @ff170000 node.
        for node in _walk_nodes(tree):
            if node.name and "@ff170000" in node.name:
                if not node.exist_property("no-1-8-v"):
                    node.append(fdt.Property("no-1-8-v"))
                    changed = True

    if changed:
        dtb.write_bytes(tree.to_dtb(version=17))


def _walk_nodes(tree):
    """Yield every node in *tree*, depth-first."""
    stack = [tree.root]
    while stack:
        node = stack.pop()
        yield node
        for child in node.nodes:
            stack.append(child)


def _assert_zynqmp_platform_inferred(spec: BoardSystemProfile, topology) -> None:
    """Catch a silent ``inferred_platform() == 'unknown'`` on ZynqMP.

    :class:`PetalinuxFormatter` only rewrites ``&amba`` → ``&amba_pl`` for
    platforms in its ``_ZYNQMP_PLATFORMS`` set
    (``adidt/xsa/petalinux.py:13-21``).  If inference fails on a ZynqMP
    XSA the build fails later with a phandle error — fail fast here with
    a clearer hint.
    """
    if spec.boot_mode != "sd":
        return
    plat = (topology.inferred_platform() or "").lower()
    if plat in {"", "unknown"}:
        pytest.fail(
            f"ZynqMP boot_mode='sd' but topology.inferred_platform() = "
            f"{plat!r}; PetaLinux build will fail with a phandle error "
            "because &amba won't be rewritten to &amba_pl.  Inspect the "
            "XSA or override the platform in the cfg."
        )


def run_petalinux_build_and_verify(
    spec: BoardSystemProfile,
    *,
    board,
    request,
    tmp_path: Path,
    out_dir: Optional[Path] = None,
) -> tuple[Any, Any, str]:
    """End-to-end PetaLinux device-tree build + boot + verify.

    Steps:

    1. Resolve ``${PETALINUX_INSTALL}`` (default ``/opt/Xilinx/PetaLinux/2023.2``)
       and extract its env (``source settings.sh``) once per session.
    2. Resolve the XSA via ``spec.xsa_resolver``.
    3. Pick or reuse a cached PetaLinux project keyed by sha256 of the XSA.
    4. ``petalinux-create`` (cache miss only) and
       ``petalinux-config --get-hw-description`` (cache miss only).
    5. Run ``XsaPipeline().run(..., output_format="petalinux")`` and install
       the produced ``system-user.dtsi`` + ``device-tree.bbappend`` into the
       project.
    6. ``petalinux-build -c device-tree``.
    7. Extract ``images/linux/system.dtb``, copy it under *out_dir* with
       ``spec.out_label`` so per-board log/staging files don't collide.
    8. Delegate to :func:`boot_and_verify_from_dtb`.

    Returns ``(shell, ctx, dmesg_txt)``.
    """
    out_dir = out_dir or (DEFAULT_OUT_DIR / "petalinux" / spec.out_label)
    out_dir.mkdir(parents=True, exist_ok=True)

    install = _resolve_petalinux_install(spec)
    env = _petalinux_env(install)

    xsa_path = spec.xsa_resolver(tmp_path)
    assert xsa_path.exists(), f"XSA not found: {xsa_path}"

    topology = XsaParser().parse(xsa_path)
    spec.topology_assert(topology)
    _assert_zynqmp_platform_inferred(spec, topology)

    template = spec.petalinux_template or _template_for_boot_mode(spec.boot_mode)
    project_dir = _petalinux_project_root(xsa_path, template=template)

    if not DEFAULT_PROJECT_CACHE and project_dir.exists():
        shutil.rmtree(project_dir)

    _petalinux_create(install, project_dir, template, env=env)
    _petalinux_get_hw_description(install, project_dir, xsa_path, env=env)

    pipeline_out = out_dir / "pyadi"
    pipeline_out.mkdir(parents=True, exist_ok=True)
    # PetaLinux's own DTG provides the base DTS via
    # ``petalinux-config --get-hw-description``; pyadi-dt only needs to
    # render the overlay nodes and format them as system-user.dtsi.
    # ``run_petalinux_only`` skips the redundant sdtgen call so this flow
    # works in PetaLinux-only environments without Vivado/Vitis installed.
    result = XsaPipeline().run_petalinux_only(
        xsa_path=xsa_path,
        cfg=spec.cfg_builder(),
        output_dir=pipeline_out,
        profile=spec.sdtgen_profile,
    )
    system_user_dtsi: Path = result["system_user_dtsi"]
    bbappend: Path = result["bbappend"]
    assert system_user_dtsi.exists(), (
        f"pipeline did not produce system-user.dtsi: {system_user_dtsi}"
    )

    _install_pyadi_outputs(project_dir, system_user_dtsi, bbappend)

    _petalinux_build_dt(install, project_dir, env=env)

    pl_dtb = _extract_dtb(project_dir)
    local_dtb = out_dir / f"{spec.out_label}.dtb"
    shutil.copyfile(pl_dtb, local_dtb)
    _apply_dtb_fixups(spec, local_dtb)

    return boot_and_verify_from_dtb(
        spec,
        local_dtb,
        board=board,
        request=request,
        out_dir=out_dir,
    )
