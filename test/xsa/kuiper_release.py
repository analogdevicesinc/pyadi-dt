from __future__ import annotations

import io
import tarfile
from pathlib import Path

import requests


class KuiperXsaError(RuntimeError):
    """Raised when Kuiper release download or XSA extraction fails."""


def download_boot_partition_release(release: str, cache_dir: Path) -> Path:
    """Download (or reuse) the Kuiper boot-partition tarball for a release."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    tarball_path = cache_dir / f"{release}_latest_boot_partition.tar.gz"
    if tarball_path.exists():
        return tarball_path

    url = (
        "https://swdownloads.analog.com/cse/boot_partition_files/"
        f"{release}/latest_boot_partition.tar.gz"
    )
    response = requests.get(url, stream=True, timeout=120)
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
        try:
            nested_member = outer_tar.getmember(nested_member_name)
        except KeyError as ex:
            available_projects = sorted(
                {
                    member.name.split("/", 1)[0]
                    for member in outer_tar.getmembers()
                    if member.name.endswith("/bootgen_sysfiles.tgz")
                }
            )
            preview = ", ".join(available_projects[:8])
            if len(available_projects) > 8:
                preview += ", ..."
            raise KuiperXsaError(
                f"project not found in Kuiper boot partition archive: {project_dir}. "
                f"Available projects: {preview}"
            ) from ex
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


def extract_release_xsas(
    tarball_path: Path,
    project_dirs: list[str],
    output_dir: Path,
    xsa_name: str = "system_top.xsa",
) -> dict[str, Path]:
    """Extract the XSA of every project in *project_dirs* in one archive pass.

    ``extract_project_xsa`` re-reads the whole (several hundred MB) archive for
    each project; this walks it once and caches results under
    ``output_dir/<project_dir>/<xsa_name>`` so repeated runs are free.

    Returns a mapping of project directory to extracted XSA path.  Projects
    whose archive entry holds no XSA are omitted.
    """
    result: dict[str, Path] = {}
    wanted: dict[str, str] = {}
    for project_dir in project_dirs:
        cached = output_dir / project_dir / xsa_name
        if cached.exists():
            result[project_dir] = cached
        else:
            wanted[f"{project_dir}/bootgen_sysfiles.tgz"] = project_dir
    if not wanted:
        return result

    with tarfile.open(tarball_path, "r:gz") as outer_tar:
        for member in outer_tar:
            project_dir = wanted.get(member.name.removeprefix("./"))
            if project_dir is None:
                continue
            nested_f = outer_tar.extractfile(member)
            if nested_f is None:
                continue
            with tarfile.open(
                fileobj=io.BytesIO(nested_f.read()), mode="r:gz"
            ) as inner_tar:
                xsa_members = [
                    m for m in inner_tar.getmembers() if m.name.endswith(".xsa")
                ]
                if not xsa_members:
                    continue
                selected = next(
                    (m for m in xsa_members if Path(m.name).name == xsa_name),
                    xsa_members[0],
                )
                src = inner_tar.extractfile(selected)
                if src is None:
                    continue
                out_path = output_dir / project_dir / xsa_name
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(src.read())
                result[project_dir] = out_path
    return result
