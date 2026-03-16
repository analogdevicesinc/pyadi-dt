from __future__ import annotations

import io
import tarfile
from pathlib import Path

import requests


def download_kuiper_xsa(
    release: str, project: str, cache_dir: Path, out_dir: Path
) -> Path:
    """Download and extract ``system_top.xsa`` from a Kuiper boot-partition release."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    tarball = cache_dir / f"{release}_latest_boot_partition.tar.gz"
    if not tarball.exists():
        url = (
            "https://swdownloads.analog.com/cse/boot_partition_files/"
            f"{release}/latest_boot_partition.tar.gz"
        )
        response = requests.get(url, stream=True, timeout=120)
        response.raise_for_status()
        with tarball.open("wb") as fout:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fout.write(chunk)

    nested_member_name = f"{project}/bootgen_sysfiles.tgz"
    with tarfile.open(tarball, "r:gz") as outer_tar:
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
            raise RuntimeError(
                f"project not found in Kuiper boot partition archive: {project}. "
                f"Available projects: {preview}"
            ) from ex
        nested_f = outer_tar.extractfile(nested_member)
        if nested_f is None:
            raise RuntimeError(f"missing member data: {nested_member_name}")
        nested_bytes = nested_f.read()

    with tarfile.open(fileobj=io.BytesIO(nested_bytes), mode="r:gz") as inner_tar:
        xsa_members = [m for m in inner_tar.getmembers() if m.name.endswith(".xsa")]
        if not xsa_members:
            raise RuntimeError(f"no .xsa found under project {project}")
        selected = next(
            (
                m
                for m in xsa_members
                if m.name.endswith("/system_top.xsa") or m.name == "system_top.xsa"
            ),
            xsa_members[0],
        )
        src = inner_tar.extractfile(selected)
        if src is None:
            raise RuntimeError(f"unable to read XSA member {selected.name}")
        xsa_path = out_dir / Path(selected.name).name
        xsa_path.write_bytes(src.read())
        return xsa_path
