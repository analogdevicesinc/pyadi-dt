"""Tests for the pyadi-dt MCP server (TDD — written before implementation)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adidt.mcp_server import mcp


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def test_server_has_tools():
    """Verify that the MCP server registers all expected tools."""
    tool_names = {t.name for t in mcp._tool_manager.tools.values()}
    expected = {
        "generate_devicetree",
        "list_xsa_profiles",
        "show_xsa_profile",
        "read_dt_property",
    }
    assert expected.issubset(tool_names), (
        f"Missing tools: {expected - tool_names}"
    )


# ---------------------------------------------------------------------------
# list_xsa_profiles
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_xsa_profiles():
    """list_xsa_profiles should return a non-empty list of profile names."""
    tool = mcp._tool_manager.tools["list_xsa_profiles"]
    result = await tool.run({})
    data = json.loads(result[0].text)
    assert isinstance(data, list)
    assert len(data) > 0
    # Spot-check a known profile
    assert "ad9081_zcu102" in data


# ---------------------------------------------------------------------------
# show_xsa_profile
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_show_xsa_profile_valid():
    """show_xsa_profile should return a dict for a known profile."""
    tool = mcp._tool_manager.tools["show_xsa_profile"]
    result = await tool.run({"name": "ad9081_zcu102"})
    data = json.loads(result[0].text)
    assert isinstance(data, dict)
    assert "defaults" in data


@pytest.mark.asyncio
async def test_show_xsa_profile_invalid():
    """show_xsa_profile should return an error for an unknown profile."""
    tool = mcp._tool_manager.tools["show_xsa_profile"]
    result = await tool.run({"name": "nonexistent_board_xyz"})
    data = json.loads(result[0].text)
    assert "error" in data


# ---------------------------------------------------------------------------
# generate_devicetree — error path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_devicetree_missing_xsa():
    """generate_devicetree should return an error for a nonexistent XSA path."""
    tool = mcp._tool_manager.tools["generate_devicetree"]
    result = await tool.run({
        "xsa_path": "/tmp/does_not_exist.xsa",
        "output_dir": "/tmp/dt_out",
    })
    data = json.loads(result[0].text)
    assert "error" in data


# ---------------------------------------------------------------------------
# generate_devicetree — mock pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_devicetree_mock(tmp_path):
    """Mock XsaPipeline.run() and verify the tool passes arguments correctly."""
    xsa_file = tmp_path / "test.xsa"
    xsa_file.touch()
    output_dir = tmp_path / "output"

    mock_result = {
        "base_dir": str(output_dir / "base"),
        "overlay": str(output_dir / "test.dtso"),
        "merged": str(output_dir / "test.dts"),
    }

    with patch("adidt.mcp_server.XsaPipeline") as MockPipeline:
        mock_instance = MagicMock()
        mock_instance.run.return_value = {
            k: Path(v) for k, v in mock_result.items()
        }
        MockPipeline.return_value = mock_instance

        tool = mcp._tool_manager.tools["generate_devicetree"]
        result = await tool.run({
            "xsa_path": str(xsa_file),
            "config_json": '{"jesd": {"rx": {"L": 4}}}',
            "output_dir": str(output_dir),
            "profile": "ad9081_zcu102",
            "emit_report": True,
            "emit_clock_graphs": False,
        })

        # Verify the pipeline was called
        mock_instance.run.assert_called_once()
        call_kwargs = mock_instance.run.call_args
        # Check key arguments were forwarded
        assert call_kwargs.kwargs["xsa_path"] == xsa_file
        assert call_kwargs.kwargs["output_dir"] == output_dir
        assert call_kwargs.kwargs["profile"] == "ad9081_zcu102"
        assert call_kwargs.kwargs["emit_report"] is True
        assert call_kwargs.kwargs["emit_clock_graphs"] is False
        assert call_kwargs.kwargs["cfg"] == {"jesd": {"rx": {"L": 4}}}

        # Verify the response contains the paths
        data = json.loads(result[0].text)
        assert "merged" in data
        assert "overlay" in data
