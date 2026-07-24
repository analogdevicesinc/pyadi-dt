from pathlib import Path


ROOT = Path(__file__).parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
DEDUPLICATED_WORKFLOWS = (
    "binding-audit.yml",
    "test.yml",
    "type-check.yml",
)


def _push_branches(workflow: str) -> list[str]:
    lines = (WORKFLOWS / workflow).read_text().splitlines()
    push_index = lines.index("  push:")
    pull_request_index = lines.index("  pull_request:", push_index)
    push_block = lines[push_index:pull_request_index]
    return [line.strip()[2:].strip("'\"") for line in push_block if line.strip().startswith("- ")]


def test_feature_branches_do_not_duplicate_push_and_pull_request_runs():
    for workflow in DEDUPLICATED_WORKFLOWS:
        branches = _push_branches(workflow)
        assert "main" in branches
        assert "**" not in branches


def test_release_maintenance_branches_keep_push_validation():
    for workflow in DEDUPLICATED_WORKFLOWS:
        branches = _push_branches(workflow)
        assert "20[1-9][0-9]_R[1-9]" in branches
        assert "staging/*" in branches
