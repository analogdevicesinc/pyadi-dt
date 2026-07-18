"""Execute the documented pyadi-jif/pyadi-dt contract examples."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from adidt.jif_contract import JifDtBindings, JifDtContract

EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "examples" / "jif_contract"


@pytest.mark.parametrize(
    ("script", "expected_links"),
    [
        ("consume_ad9680.py", {"ad9680.rx"}),
        ("adrv9009_bidirectional.py", {"adrv9009.rx", "adrv9009.tx"}),
    ],
)
def test_contract_example_runs(script: str, expected_links: set[str]) -> None:
    """Examples must execute and report every expected validated link."""
    result = subprocess.run(
        [sys.executable, str(EXAMPLE_DIR / script)],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    summary = json.loads(result.stdout)

    assert summary["status"] == "validated"
    links = summary["links"]
    assert set(links) == expected_links


def test_saved_ad9680_contract_and_bindings_validate_together() -> None:
    """The checked-in JSON pair is an executable interchange fixture."""
    contract = JifDtContract.from_json_file(EXAMPLE_DIR / "ad9680.jif-dt.json")
    bindings = JifDtBindings.model_validate_json(
        (EXAMPLE_DIR / "ad9680.bindings.json").read_text()
    )

    bindings.check(contract)
    assert contract.jesd_links[0].lane_rate_hz == 10_000_000_000
    assert {binding.output_index for binding in bindings.clocks} == {5, 13}