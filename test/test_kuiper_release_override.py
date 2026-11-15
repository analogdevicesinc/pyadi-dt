"""Release override used to run lab rigs against another Kuiper release."""

from pathlib import Path

from test.hw import hw_helpers


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
