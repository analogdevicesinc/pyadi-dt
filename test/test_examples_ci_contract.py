"""Contracts for the dedicated examples CI gate."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "test.yml"
EXAMPLE_TEST_GROUPS = (
    "test/devices/test_examples_smoke.py",
    "test/devices/test_examples_ad9081_parity.py",
    "test/test_examples_xsa_smoke.py",
    "test/xsa/test_example_adrv9009_profile_file.py",
    "test/xsa/test_example_fmcdaq2_zc706.py",
    "test/test_jif_contract_examples.py",
    "test/test_examples_ci_contract.py",
)


def test_examples_have_a_dedicated_blocking_ci_job() -> None:
    """Keep all example checks visible and blocking in package CI."""
    workflow = WORKFLOW.read_text()

    assert "examples-test:" in workflow
    assert 'pip install ".[test,xsa]"' in workflow
    assert "Pull canonical ADRV9009 Talise profile" in workflow
    assert "--download-talise-profile" in workflow
    for test_group in EXAMPLE_TEST_GROUPS:
        assert test_group in workflow
    assert "needs: [python-test, examples-test]" in workflow


def test_every_python_example_is_discovered_by_an_example_test() -> None:
    """Require executable or import-smoke discovery for every Python example."""
    examples = REPO_ROOT / "examples"
    top_level = {path.name for path in examples.glob("*.py")}
    xsa = {path.name for path in (examples / "xsa").glob("*.py")}
    jif_contract = {path.name for path in (examples / "jif_contract").glob("*.py")}

    assert top_level
    assert xsa
    assert jif_contract

    smoke_source = (REPO_ROOT / "test/devices/test_examples_smoke.py").read_text()
    xsa_source = (REPO_ROOT / "test/test_examples_xsa_smoke.py").read_text()
    contract_source = (REPO_ROOT / "test/test_jif_contract_examples.py").read_text()

    assert 'EXAMPLES_DIR.glob("*.py")' in smoke_source
    assert 'XSA_DIR.glob("*.py")' in xsa_source
    for script in jif_contract:
        assert script in contract_source
