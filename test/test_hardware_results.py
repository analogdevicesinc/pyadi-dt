"""Hardware release gates must distinguish execution from skip-only success."""

import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / ".github/scripts/check_hardware_results.py"


@pytest.mark.parametrize(
    "xml,success",
    [
        (
            '<testsuites><testsuite><testcase name="boot"/></testsuite></testsuites>',
            True,
        ),
        ("<testsuite><testcase/><testcase><skipped/></testcase></testsuite>", True),
        ("<testsuite><testcase><skipped/></testcase></testsuite>", False),
        ("<testsuites><testsuite/></testsuites>", False),
        ("<testsuite><testcase/><testcase><failure/></testcase></testsuite>", False),
        ("<testsuite><testcase><error/></testcase></testsuite>", False),
        ("not XML", False),
        (None, False),
    ],
)
def test_hardware_result_gate(tmp_path, xml, success):
    report = tmp_path / "junit.xml"
    if xml is not None:
        report.write_text(xml)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(report)], capture_output=True
    )
    assert (result.returncode == 0) is success
