"""Runner-local kernel handoff from CIM; no builds or hardware side effects."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

DEFAULT_CIM_RELEASE = "2023_R2"
CIM_RELEASES = {
    "2023_R2": {
        "builder_release": "2023_R2",
        "ref": "2023_R2",
        "commit": "86d61468a7856e952c7ca237f798d86d6abd2e27",
    },
    "2026-R1": {
        "builder_release": "2026_R1",
        "ref": "xlnx_2026.1.0",
        "commit": "b47bbbe8ca7bc582c96251fa30d86e55de363f68",
    },
}


def cim_release(value: str | None = None) -> str:
    """Validate exact release names, without silently normalizing typos."""
    release = (
        os.environ.get("ADIDT_CIM_RELEASE", DEFAULT_CIM_RELEASE)
        if value is None
        else value
    )
    if release not in CIM_RELEASES:
        raise ValueError(
            f"Unsupported CIM release {release!r}; choose {', '.join(CIM_RELEASES)}"
        )
    return release


def _image_file(value: str, source: str, *, absolute: bool = False) -> Path:
    path = Path(value)
    if absolute and not path.is_absolute():
        raise RuntimeError(f"{source}: kernel_image must be an absolute path")
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"{source}: kernel image is not a non-empty file: {path}")
    return path


def read_kernel_artifacts(
    manifest: str, platform: str, *, release: str | None = None
) -> Path:
    """Validate a version-1 artifact manifest and rehash its kernel image."""
    release = cim_release(release)
    try:
        path = Path(manifest)
        if not path.is_file():
            raise RuntimeError(f"Kernel artifact manifest is not a file: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise RuntimeError(f"{path}: expected a JSON object")
        if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
            raise RuntimeError(f"{path}: unsupported schema_version; expected 1")
        if data.get("platform") != platform:
            raise RuntimeError(f"{path}: expected platform {platform!r}")
        provenance = data.get("provenance")
        source = provenance.get("source") if isinstance(provenance, dict) else None
        expected = CIM_RELEASES[release]
        if not isinstance(source, dict) or any(
            source.get(key) != expected[key] for key in ("ref", "commit")
        ):
            raise RuntimeError(
                f"{path}: expected {release} source ref/commit provenance"
            )
        # Older 2023_R2 manifests lack a release field; source pins identify them.
        if (
            isinstance(provenance, dict)
            and "release" in provenance
            and provenance["release"] != expected["builder_release"]
        ):
            raise RuntimeError(f"{path}: expected release {release!r}")
        image = data.get("kernel_image")
        if not isinstance(image, str) or not image:
            raise RuntimeError(f"{path}: kernel_image must be a non-empty string")
        checksum = data.get("sha256")
        if not isinstance(checksum, str) or not re.fullmatch(
            r"[0-9a-fA-F]{64}", checksum
        ):
            raise RuntimeError(f"{path}: sha256 must contain 64 hexadecimal characters")
        image_path = _image_file(image, str(path), absolute=True)
        digest = hashlib.sha256()
        with image_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != checksum.lower():
            raise RuntimeError(f"{path}: kernel image SHA-256 mismatch: {image_path}")
        return image_path
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            f"Invalid kernel artifact manifest {manifest}: {exc}"
        ) from exc


def resolve_kernel_image(platform: str, *, enabled: bool | None = None) -> Path | None:
    """Prefer explicit images, then disabled mode, then validated CIM artifacts."""
    if platform not in {"zynq", "zynqmp"}:
        raise ValueError(f"Unknown platform arch: {platform!r}")
    override_var = f"ADIDT_KERNEL_IMAGE_{platform.upper()}"
    override = os.environ.get(override_var)
    if override:
        return _image_file(override, override_var)
    if enabled is None:
        enabled = os.environ.get("ADI_XSA_BUILD_KERNEL", "1").lower() not in {
            "0",
            "false",
            "no",
        }
    if not enabled:
        return None
    release = cim_release()
    artifact_var = f"ADIDT_KERNEL_ARTIFACTS_{platform.upper()}"
    manifest = os.environ.get(artifact_var)
    if not manifest:
        raise RuntimeError(
            f"No {platform} kernel prepared. Before acquiring hardware, build the "
            f"CIM adi-linux target with KERNEL_RELEASE={CIM_RELEASES[release]['builder_release']} "
            f"KERNEL_PLATFORM={platform} and set {artifact_var} to its "
            f"artifacts.json, or set {override_var} to a prebuilt boot-ready image. "
            "Set ADI_XSA_BUILD_KERNEL=0 to retain the board's existing kernel."
        )
    return read_kernel_artifacts(manifest, platform, release=release)
