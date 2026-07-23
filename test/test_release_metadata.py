"""Release metadata consistency tests."""

from importlib.metadata import version

import adidt


def test_package_and_distribution_versions_match():
    """Keep the importable and built-distribution versions synchronized."""
    assert adidt.__version__ == version("adidt")
