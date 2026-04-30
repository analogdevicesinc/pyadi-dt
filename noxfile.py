"""Nox configuration for running tests and tasks with uv backend."""

from pathlib import Path

import nox

nox.options.default_venv_backend = "uv"

PYTHON_VERSIONS = ["3.10"]


def _install_local_pyd2lang(session):
    """Install a local pyd2lang-native wheel (or source fallback)."""
    dist_dir = (Path(__file__).parent.parent / "pyd2lang-native" / "dist").resolve()
    py_tag = f"cp{str(session.python).replace('.', '')}"
    wheels = sorted(dist_dir.glob(f"pyd2lang_native-*-{py_tag}-*.whl"))

    if wheels:
        wheel = str(wheels[-1])
        session.log(f"Installing local pyd2lang-native wheel: {wheel}")
        session.install("--reinstall", "--no-deps", wheel)
        return

    session.warn(
        f"No local pyd2lang-native wheel matching {py_tag} in {dist_dir}; "
        "falling back to source install from ../pyd2lang-native."
    )
    session.install("--reinstall", "--no-deps", "../pyd2lang-native")


@nox.session(python=PYTHON_VERSIONS)
def tests(session):
    """Run the test suite with pytest.

    Pass additional args after '--' to override the default test path:
        nox -s tests -- test/xsa/ -v -k "ad9081"
    """
    session.install(".[dev]")
    args = session.posargs if session.posargs else ["test/"]
    session.run("pytest", "-vs", *args)


@nox.session(python="3.11")
def lint(session):
    """Run linting checks with ruff."""
    session.install("ruff")
    session.run("ruff", "check", "adidt", "test")


@nox.session(python="3.11")
def format(session):
    """Format code with ruff."""
    session.install("ruff")
    session.run("ruff", "format", "adidt", "test")


@nox.session(python="3.11")
def format_check(session):
    """Check code formatting with ruff."""
    session.install("ruff")
    session.run("ruff", "format", "--check", "adidt", "test")


@nox.session(python="3.12")
def d2_diagrams(session):
    """Compile D2 diagram sources to SVG using pyd2lang-native."""
    _install_local_pyd2lang(session)
    session.run("python", "doc/source/_diagrams/compile_d2.py")


@nox.session(python="3.11")
def docs(session):
    """Build documentation with Sphinx."""
    session.install(
        "sphinx",
        "myst-parser",
        "sphinx-click",
        "sphinxcontrib-mermaid",
        "adi-doctools",
        "linkify-it-py",
        "pyd2lang-native>=0.1.1",
    )
    session.install(".")
    session.run("sphinx-build", "-vv", "-b", "html", "doc/source", "doc/build/html")


@nox.session(python="3.11")
def docs_serve(session):
    """Build and serve documentation locally with Sphinx autobuild."""
    session.install(
        "sphinx",
        "myst-parser",
        "sphinx-click",
        "sphinxcontrib-mermaid",
        "adi-doctools",
        "linkify-it-py",
        "sphinx-autobuild",
        "fdt",
        "pyd2lang-native>=0.1.1",
        ".[dev]",
    )
    session.run("sphinx-autobuild", "doc/source", "doc/build/html", "--host", "0.0.0.0")


@nox.session(python="3.11")
def coverage(session):
    """Run tests with coverage reporting."""
    session.install(".[dev]", "pytest-cov")
    session.run(
        "pytest",
        "-vs",
        "--cov=adidt",
        "--cov-report=html",
        "--cov-report=term",
        *session.posargs,
    )


@nox.session(python="3.12")
def ty(session):
    """Run type checking with ty.

    Mirrors the path list used by ``.github/workflows/type-check.yml``.
    Pass additional paths after '--' to check specific modules:
        nox -s ty -- adidt/model/
    """
    session.install(".[dev]", "ty")
    paths = (
        session.posargs
        if session.posargs
        else [
            "adidt/model/",
            "adidt/xsa/build/builders/",
            "adidt/devices/",
            "adidt/system.py",
            "adidt/tools/",
        ]
    )
    session.run("ty", "check", *paths)


@nox.session(python="3.11")
def build(session):
    """Build distribution packages."""
    session.install("build")
    session.run("python", "-m", "build")


@nox.session(python="3.11")
def dts_lint(session):
    """Run DTS structural linter tests."""
    session.install(".[dev]")
    session.run(
        "pytest",
        "-vs",
        "test/xsa/test_dts_lint.py",
        "test/xsa/test_dts_lint_integration.py",
    )


@nox.session(python="3.11")
def dtc_compile(session):
    """Compile generated DTS files with dtc to catch syntax errors.

    Requires dtc on PATH or at a known PetaLinux sysroots location.
    Skips gracefully if dtc is not available.
    """
    session.install(".[dev]")
    session.run("pytest", "-vs", "test/xsa/test_dtc_compile.py", *session.posargs)


@nox.session(python="3.11")
def test_specific(session):
    """Run specific test file or test function.

    Examples:
        nox -s test_specific -- test/test_dt.py
        nox -s test_specific -- test/test_dt.py::test_function_name
    """
    session.install(".[dev]")
    if not session.posargs:
        session.error("Please provide a test file or test path")
    session.run("pytest", "-vs", *session.posargs)


@nox.session(python="3.12")
def security_audit(session):
    """Audit installed dependencies for known vulnerabilities using pip-audit."""
    session.install(".", "pip-audit")
    session.run("pip-audit", *session.posargs)


@nox.session(python="3.12")
def bandit(session):
    """Run Bandit security linter against source code."""
    session.install("bandit[toml]")
    session.run(
        "bandit", "-r", "adidt/", "-c", ".bandit", "-b", ".bandit-baseline.json",
        *session.posargs,
    )
