from __future__ import annotations

import io
import tarfile
from pathlib import Path


class KuiperXsaError(RuntimeError):
    """Raised when Kuiper release download or XSA extraction fails."""


def _require_kuiper_plugin():
    try:
        from adi_lg_plugins.drivers.kuiperdldriver import Downloader, KuiperDLDriver
    except ImportError as ex:
        raise KuiperXsaError(
            "adi-labgrid-plugins is required for Kuiper XSA download tests"
        ) from ex
    return Downloader, KuiperDLDriver


def download_boot_partition_release(release: str, cache_dir: Path) -> Path:
    """Download (or reuse) the Kuiper boot-partition tarball for a release."""
    Downloader, KuiperDLDriver = _require_kuiper_plugin()
    cache_dir.mkdir(parents=True, exist_ok=True)
    tarball_path = cache_dir / f"{release}_latest_boot_partition.tar.gz"
    if tarball_path.exists():
        return tarball_path

    url = KuiperDLDriver.sw_downloads_template.format(release=release)
    response = Downloader().retry_session().get(url, stream=True, timeout=120)
    if not response.ok:
        raise KuiperXsaError(
            f"failed to download Kuiper boot partition: release={release} "
            f"url={url} status={response.status_code}"
        )

    with tarball_path.open("wb") as fout:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                fout.write(chunk)

    return tarball_path


def extract_project_xsa(
    tarball_path: Path,
    project_dir: str,
    output_dir: Path,
    xsa_name: str = "system_top.xsa",
) -> Path:
    """Extract ``project_dir/bootgen_sysfiles.tgz`` -> ``xsa_name`` to output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    nested_member_name = f"{project_dir}/bootgen_sysfiles.tgz"

    with tarfile.open(tarball_path, "r:gz") as outer_tar:
        nested_member = outer_tar.getmember(nested_member_name)
        nested_f = outer_tar.extractfile(nested_member)
        if nested_f is None:
            raise KuiperXsaError(f"missing member data: {nested_member_name}")
        nested_bytes = nested_f.read()

    with tarfile.open(fileobj=io.BytesIO(nested_bytes), mode="r:gz") as inner_tar:
        xsa_members = [m for m in inner_tar.getmembers() if m.name.endswith(".xsa")]
        if not xsa_members:
            raise KuiperXsaError(
                f"no .xsa found in nested archive for project {project_dir}"
            )

        selected = None
        for member in xsa_members:
            if member.name.endswith(f"/{xsa_name}") or member.name == xsa_name:
                selected = member
                break
        if selected is None:
            selected = xsa_members[0]

        src = inner_tar.extractfile(selected)
        if src is None:
            raise KuiperXsaError(f"unable to read XSA member {selected.name}")

        out_path = output_dir / Path(selected.name).name
        out_path.write_bytes(src.read())

    return out_path


def download_project_xsa(
    release: str,
    project_dir: str,
    cache_dir: Path,
    output_dir: Path,
    xsa_name: str = "system_top.xsa",
) -> Path:
    tarball_path = download_boot_partition_release(release=release, cache_dir=cache_dir)
    return extract_project_xsa(
        tarball_path=tarball_path,
        project_dir=project_dir,
        output_dir=output_dir,
        xsa_name=xsa_name,
    )
