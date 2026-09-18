"""Keep the requirements.txt flow in sync with pyproject.toml."""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

repo_root = Path(__file__).resolve().parents[1]


def _pyproject() -> dict:
    return tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))


def _requirement_lines(name: str) -> list[str]:
    lines = []
    for raw in (repo_root / name).read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return lines


def test_requirements_txt_matches_runtime_dependencies():
    expected = _pyproject()["project"]["dependencies"]

    assert _requirement_lines("requirements.txt") == expected


def test_requirements_dev_txt_matches_dev_extra():
    extras = _pyproject()["project"]["optional-dependencies"]
    # The dev extra references the package's own test+xsa extras; a
    # requirements file cannot, so it must spell them out.
    self_reference = "pyadi-dt[test,xsa]"
    assert self_reference in extras["dev"]
    # pyadi-build is a private repository only the hardware-CI runners can
    # clone; it stays in the extra but is intentionally left out of the file.
    private = [dep for dep in extras["dev"] if dep.startswith("pyadi-build ")]
    assert private, "expected the dev extra to still carry pyadi-build"
    excluded = {self_reference, *private}
    expected = (
        ["-r requirements.txt"]
        + extras["test"]
        + extras["xsa"]
        + [dep for dep in extras["dev"] if dep not in excluded]
    )

    assert _requirement_lines("requirements_dev.txt") == expected


def test_requirements_dev_txt_includes_runtime_requirements():
    assert "-r requirements.txt" in _requirement_lines("requirements_dev.txt")
