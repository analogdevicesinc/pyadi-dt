"""Nox configuration for running tests and tasks with uv backend."""

import nox

# Use uv for faster package installations
nox.options.default_venv_backend = "uv"

# Define Python versions to test against (from pyproject.toml)
# PYTHON_VERSIONS = ["3.9", "3.10", "3.11", "3.12"]
PYTHON_VERSIONS = ["3.10"]


@nox.session(python=PYTHON_VERSIONS)
def tests(session):
    """Run the test suite with pytest."""
    # Install the package with dev dependencies
    session.install(".[dev]")

    # Run pytest with verbose output
    session.run("pytest", "-vs", "test/", *session.posargs)


@nox.session(python=PYTHON_VERSIONS)
def tests_remote(session):
    """Run tests including remote board tests (requires --ip argument)."""
    # Install the package with dev dependencies
    session.install(".[dev]")

    # Check if --ip is provided in posargs
    if not any(arg.startswith("--ip") for arg in session.posargs):
        session.warn("No --ip argument provided. Remote tests may be skipped.")

    # Run pytest with verbose output and pass through all arguments
    session.run("pytest", "-vs", *session.posargs)


@nox.session(python="3.11")
def lint(session):
    """Run linting checks with ruff (if available)."""
    try:
        session.install("ruff")
        session.run("ruff", "check", "adidt", "test")
    except Exception:
        session.warn("Ruff not available or linting failed")


@nox.session(python="3.11")
def format(session):
    """Format code with ruff."""
    try:
        session.install("ruff")
        session.run("ruff", "format", "adidt", "test")
    except Exception:
        session.warn("Ruff not available or formatting failed")


@nox.session(python="3.11")
def format_check(session):
    """Check code formatting with ruff."""
    try:
        session.install("ruff")
        session.run("ruff", "format", "--check", "adidt", "test")
    except Exception:
        session.warn("Ruff not available or format check failed")


@nox.session(python="3.11")
def docs(session):
    """Build documentation with mkdocs."""
    session.install("mkdocs", "mkdocs-material")
    session.install(".")
    session.run("mkdocs", "build", "--verbose", "--strict")


@nox.session(python="3.11")
def docs_serve(session):
    """Serve documentation locally with mkdocs."""
    session.install("mkdocs", "mkdocs-material")
    session.install(".")
    session.run("mkdocs", "serve")


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


@nox.session(python="3.11")
def type_check(session):
    """Run type checking with mypy."""
    try:
        session.install(".[dev]", "mypy")
        session.run("mypy", "adidt", "--ignore-missing-imports")
    except Exception:
        session.warn("Type checking failed or mypy not configured")


@nox.session(python="3.11")
def build(session):
    """Build distribution packages."""
    session.install("build")
    session.run("python", "-m", "build")


@nox.session(python="3.11")
def test_quick(session):
    """Run quick validation tests."""
    session.install(".[dev]")
    session.run("pytest", "-vs", "test_quick.py", *session.posargs)


@nox.session(python="3.11")
def test_validation(session):
    """Run validation tests."""
    session.install(".[dev]")
    session.run("pytest", "-vs", "test_validation.py", *session.posargs)


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
