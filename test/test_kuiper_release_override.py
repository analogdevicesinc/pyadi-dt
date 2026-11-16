"""Release override used to run lab rigs against another Kuiper release."""

import importlib.util
import io
import tarfile
from pathlib import Path

from test.hw import hw_helpers


def _tar(members: dict[str, bytes], path: Path | None = None) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(path, "w:gz", fileobj=None if path else buffer) as archive:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def test_jtag_zynqmp_rig_gets_release_bitstream_and_kernel(tmp_path):
    script = Path(__file__).parents[1] / ".github/scripts/prepare_kuiper_boot_files.py"
    spec = importlib.util.spec_from_file_location("prepare_kuiper_boot_files", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    platform, project = module.RIGS[("adrv9009zu11eg", "adrv2crr-fmc")]
    sysfiles = _tar({"system_top.bit": b"bitstream", "fsbl.elf": b"fsbl"})
    release = tmp_path / "release.tar.gz"
    _tar(
        {
            f"{project}/BOOT.BIN": b"boot",
            f"{project}/bootgen_sysfiles.tgz": sysfiles,
            "zynqmp-common/Image": b"kernel",
        },
        release,
    )

    staged = module.stage(release, project, platform, tmp_path / "out")

    assert staged["ADIDT_ZYNQMP_BITSTREAM"].read_bytes() == b"bitstream"
    assert staged["ADIDT_ZYNQMP_KERNEL"].read_bytes() == b"kernel"
    assert set(staged) == {"ADIDT_ZYNQMP_BITSTREAM", "ADIDT_ZYNQMP_KERNEL"}


def test_override_replaces_release_and_skips_local_fixture(tmp_path, monkeypatch):
    local = tmp_path / "system_top.xsa"
    local.write_bytes(b"committed fixture")
    calls = []

    def download(**kwargs):
        calls.append(kwargs)
        return tmp_path / "downloaded.xsa"

    monkeypatch.setattr("test.xsa.kuiper_release.download_project_xsa", download)
    monkeypatch.setenv("ADIDT_KUIPER_RELEASE", "2026_r1")
    monkeypatch.setenv("ADIDT_KUIPER_CACHE", str(tmp_path / "cache"))

    result = hw_helpers.acquire_xsa(
        local, "2023_r2", "zynqmp-zcu102-rev10-ad9081", tmp_path
    )

    assert result == tmp_path / "downloaded.xsa"
    assert calls[0]["release"] == "2026_r1"
    assert calls[0]["project_dir"] == "zynqmp-zcu102-rev10-ad9081/m8_l4"
    assert calls[0]["cache_dir"] == tmp_path / "cache"


def test_without_override_local_fixture_wins(tmp_path, monkeypatch):
    local = tmp_path / "system_top.xsa"
    local.write_bytes(b"committed fixture")
    monkeypatch.delenv("ADIDT_KUIPER_RELEASE", raising=False)
    assert hw_helpers.acquire_xsa(local, "2023_r2", "project", tmp_path) == Path(local)
