import os
import subprocess
from pathlib import Path

from click.testing import CliRunner

from adidt.cli.main import cli


ROOT = Path(__file__).parents[1]
SKILL_ROOT = ROOT / "skills" / "pyadi-dt-cli"
SKILL = SKILL_ROOT / "SKILL.md"
COMMANDS = SKILL_ROOT / "reference" / "commands.md"
INSTALLER = SKILL_ROOT / "scripts" / "install.sh"
SPHINX_INDEX = ROOT / "doc" / "source" / "index.rst"
SPHINX_CLI = ROOT / "doc" / "source" / "cli.rst"
SPHINX_SKILL = ROOT / "doc" / "source" / "ai_skill.rst"

PUBLIC_COMMANDS = {
    "deps",
    "gen-dts",
    "jif",
    "kuiper-boards",
    "prop",
    "props",
    "sd-move",
    "sd-remote-copy",
    "xsa-profile-show",
    "xsa-profiles",
    "xsa2dt",
}


def _frontmatter(text: str) -> dict[str, str]:
    assert text.startswith("---\n")
    block = text.split("---\n", 2)[1]
    return dict(line.split(": ", 1) for line in block.splitlines())


def test_skill_has_valid_frontmatter_and_linked_files():
    text = SKILL.read_text()
    metadata = _frontmatter(text)
    assert metadata["name"] == "pyadi-dt-cli"
    assert "adidtc" in metadata["description"]
    assert "reference/commands.md" in text
    assert COMMANDS.is_file()
    assert INSTALLER.is_file()


def test_skill_routes_every_public_cli_command():
    text = f"{SKILL.read_text()}\n{COMMANDS.read_text()}"
    assert set(cli.commands) == PUBLIC_COMMANDS
    for command in PUBLIC_COMMANDS:
        assert f"`{command}`" in text or f"adidtc {command}" in text


def test_skill_keeps_hardware_changes_behind_dry_run_and_approval():
    text = SKILL.read_text().lower()
    recipes = COMMANDS.read_text().lower()
    for command in ("sd-move", "sd-remote-copy"):
        assert f"{command}` | always run `--dry-run --show` first" in text
        assert f"{command} " in recipes
    assert "explicit approval" in text
    assert "do not put passwords" in recipes
    assert "successful copy is not" in text


def test_documented_discovery_commands_execute():
    runner = CliRunner()

    profiles = runner.invoke(cli, ["xsa-profiles"])
    assert profiles.exit_code == 0, profiles.output
    assert "ad9081_zcu102" in profiles.output

    profile = runner.invoke(cli, ["xsa-profile-show", "ad9081_zcu102"])
    assert profile.exit_code == 0, profile.output
    assert '"name": "ad9081_zcu102"' in profile.output

    boards = runner.invoke(cli, ["kuiper-boards", "--json-output"])
    assert boards.exit_code == 0, boards.output
    assert '"status"' in boards.output


def test_installer_supports_agents_claude_and_is_idempotent(tmp_path):
    env = {**os.environ, "HOME": str(tmp_path)}
    subprocess.run(["bash", str(INSTALLER), "all"], check=True, env=env)
    subprocess.run(["bash", str(INSTALLER), "all"], check=True, env=env)

    for parent in (".agents", ".claude"):
        installed = tmp_path / parent / "skills" / "pyadi-dt-cli"
        assert installed.is_symlink()
        assert installed.resolve() == SKILL_ROOT.resolve()


def test_sphinx_documents_and_links_the_skill():
    index = SPHINX_INDEX.read_text()
    cli_docs = SPHINX_CLI.read_text()
    skill_docs = SPHINX_SKILL.read_text()

    assert "   ai_skill" in index
    assert ":doc:`ai_skill`" in index
    assert ":doc:`ai_skill`" in cli_docs
    assert "skills/pyadi-dt-cli/SKILL.md" in skill_docs
    assert "./skills/pyadi-dt-cli/scripts/install.sh" in skill_docs
    assert "--dry-run --show" in skill_docs
    assert "explicit approval" in skill_docs
