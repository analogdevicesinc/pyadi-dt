"""Tests for the pyadi-dt MCP server (TDD — written before implementation)."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adidt.mcp_server import generate_devicetree, mcp


def _tool_data(result):
    """Return the semantic payload from a FastMCP ToolResult."""
    if isinstance(result.structured_content, dict) and set(
        result.structured_content.keys()
    ) == {"result"}:
        return result.structured_content["result"]
    return result.structured_content


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def test_server_has_tools():
    """Verify that the MCP server registers all expected tools."""
    tool_names = {t.name for t in asyncio.run(mcp.list_tools())}
    expected = {
        "generate_devicetree",
        "list_xsa_profiles",
        "show_xsa_profile",
        "read_dt_property",
    }
    assert expected.issubset(tool_names), f"Missing tools: {expected - tool_names}"


# ---------------------------------------------------------------------------
# list_xsa_profiles
# ---------------------------------------------------------------------------


def test_list_xsa_profiles():
    """list_xsa_profiles should return a non-empty list of profile names."""
    tool = asyncio.run(mcp.get_tool("list_xsa_profiles"))
    result = asyncio.run(tool.run({}))
    data = _tool_data(result)
    assert isinstance(data, list)
    assert len(data) > 0
    # Spot-check a known profile
    assert "ad9081_zcu102" in data


# ---------------------------------------------------------------------------
# show_xsa_profile
# ---------------------------------------------------------------------------


def test_show_xsa_profile_valid():
    """show_xsa_profile should return a dict for a known profile."""
    tool = asyncio.run(mcp.get_tool("show_xsa_profile"))
    result = asyncio.run(tool.run({"name": "ad9081_zcu102"}))
    data = _tool_data(result)
    assert isinstance(data, dict)
    assert "defaults" in data


def test_show_xsa_profile_ad9084_vcu118():
    """show_xsa_profile should expose the AD9084-EBZ-on-VCU118 profile."""
    tool = asyncio.run(mcp.get_tool("show_xsa_profile"))
    result = asyncio.run(tool.run({"name": "ad9084_vcu118"}))
    data = _tool_data(result)
    assert data["defaults"]["ad9084_board"]["dev_clk_ref"] == "adf4382 0"
    assert data["defaults"]["ad9084_board"]["hsci_label"] == "axi_hsci_0"


def test_show_xsa_profile_invalid():
    """show_xsa_profile should return an error for an unknown profile."""
    tool = asyncio.run(mcp.get_tool("show_xsa_profile"))
    result = asyncio.run(tool.run({"name": "nonexistent_board_xyz"}))
    data = _tool_data(result)
    assert "error" in data


# ---------------------------------------------------------------------------
# generate_devicetree — error path
# ---------------------------------------------------------------------------


def test_generate_devicetree_missing_xsa():
    """generate_devicetree should return an error for a nonexistent XSA path."""
    tool = asyncio.run(mcp.get_tool("generate_devicetree"))
    result = asyncio.run(
        tool.run(
            {
                "xsa_path": "/tmp/does_not_exist.xsa",
                "output_dir": "/tmp/dt_out",
            }
        )
    )
    data = _tool_data(result)
    assert "error" in data


# ---------------------------------------------------------------------------
# generate_devicetree — mock pipeline
# ---------------------------------------------------------------------------


def test_generate_devicetree_mock(tmp_path):
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
        mock_instance.run.return_value = {k: Path(v) for k, v in mock_result.items()}
        MockPipeline.return_value = mock_instance

        tool = asyncio.run(mcp.get_tool("generate_devicetree"))
        result = asyncio.run(
            tool.run(
                {
                    "xsa_path": str(xsa_file),
                    "config_json": '{"jesd": {"rx": {"L": 4}}}',
                    "output_dir": str(output_dir),
                    "profile": "ad9081_zcu102",
                    "emit_report": True,
                    "emit_clock_graphs": False,
                }
            )
        )

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
        # sdtgen_timeout must always be forwarded
        assert "sdtgen_timeout" in call_kwargs.kwargs

        # Verify the response contains the paths
        data = _tool_data(result)
        assert "merged" in data
        assert "overlay" in data


def test_generate_devicetree_defaults_enable_report_and_clock_graphs(tmp_path):
    """Default MCP calls should emit reports and clock graphs."""
    xsa_file = tmp_path / "test.xsa"
    xsa_file.touch()
    output_dir = tmp_path / "output"

    with patch("adidt.mcp_server.XsaPipeline") as MockPipeline:
        mock_instance = MagicMock()
        mock_instance.run.return_value = {
            "base_dir": output_dir / "base",
            "overlay": output_dir / "test.dtso",
            "merged": output_dir / "test.dts",
            "report": output_dir / "test_report.html",
            "clock_dot": output_dir / "test_clock.dot",
            "clock_d2": output_dir / "test_clock.d2",
        }
        MockPipeline.return_value = mock_instance

        generate_devicetree(
            xsa_path=str(xsa_file),
            output_dir=str(output_dir),
        )

        mock_instance.run.assert_called_once()
        call_kwargs = mock_instance.run.call_args
        assert call_kwargs.kwargs["emit_report"] is True
        assert call_kwargs.kwargs["emit_clock_graphs"] is True


def test_generate_devicetree_default_sdtgen_timeout(tmp_path):
    """MCP default sdtgen_timeout should be 300 s (adequate for AD9084+VCU118 XSA)."""
    xsa_file = tmp_path / "test.xsa"
    xsa_file.touch()

    with patch("adidt.mcp_server.XsaPipeline") as MockPipeline:
        mock_instance = MagicMock()
        mock_instance.run.return_value = {
            "base_dir": tmp_path / "base",
            "overlay": tmp_path / "test.dtso",
            "merged": tmp_path / "test.dts",
        }
        MockPipeline.return_value = mock_instance

        generate_devicetree(xsa_path=str(xsa_file), output_dir=str(tmp_path))

        call_kwargs = mock_instance.run.call_args
        assert call_kwargs.kwargs["sdtgen_timeout"] == 300


def test_generate_devicetree_sdtgen_timeout_forwarded(tmp_path):
    """Caller-specified sdtgen_timeout should be forwarded to XsaPipeline.run()."""
    xsa_file = tmp_path / "test.xsa"
    xsa_file.touch()

    with patch("adidt.mcp_server.XsaPipeline") as MockPipeline:
        mock_instance = MagicMock()
        mock_instance.run.return_value = {
            "base_dir": tmp_path / "base",
            "overlay": tmp_path / "test.dtso",
            "merged": tmp_path / "test.dts",
        }
        MockPipeline.return_value = mock_instance

        generate_devicetree(
            xsa_path=str(xsa_file), output_dir=str(tmp_path), sdtgen_timeout=600
        )

        call_kwargs = mock_instance.run.call_args
        assert call_kwargs.kwargs["sdtgen_timeout"] == 600


def test_generate_devicetree_reference_dts_forwarded(tmp_path):
    """reference_dts path should be forwarded to XsaPipeline.run() as a Path."""
    xsa_file = tmp_path / "test.xsa"
    xsa_file.touch()
    ref_dts = tmp_path / "reference.dts"
    ref_dts.write_text("/dts-v1/;")

    with patch("adidt.mcp_server.XsaPipeline") as MockPipeline:
        mock_instance = MagicMock()
        mock_instance.run.return_value = {
            "base_dir": tmp_path / "base",
            "overlay": tmp_path / "test.dtso",
            "merged": tmp_path / "test.dts",
            "map": tmp_path / "parity_map.json",
            "coverage": tmp_path / "parity_coverage.json",
        }
        MockPipeline.return_value = mock_instance

        generate_devicetree(
            xsa_path=str(xsa_file),
            output_dir=str(tmp_path),
            reference_dts=str(ref_dts),
            strict_parity=True,
        )

        call_kwargs = mock_instance.run.call_args
        assert call_kwargs.kwargs["reference_dts"] == ref_dts
        assert call_kwargs.kwargs["strict_parity"] is True


def test_generate_devicetree_returns_canonical_merged_dts_and_pl_dtsi(tmp_path):
    """MCP results should point callers at the merged DTS and required pl.dtsi include."""
    xsa_file = tmp_path / "test.xsa"
    xsa_file.touch()
    output_dir = tmp_path / "output"
    base_dir = output_dir / "base"
    base_dir.mkdir(parents=True)
    pl_dtsi = base_dir / "pl.dtsi"
    pl_dtsi.write_text("/ { };")

    with patch("adidt.mcp_server.XsaPipeline") as MockPipeline:
        mock_instance = MagicMock()
        mock_instance.run.return_value = {
            "base_dir": base_dir,
            "overlay": output_dir / "test.dtso",
            "merged": output_dir / "test.dts",
        }
        MockPipeline.return_value = mock_instance

        data = generate_devicetree(
            xsa_path=str(xsa_file),
            output_dir=str(output_dir),
        )

        assert data["dts_path"] == str(output_dir / "test.dts")
        assert data["pl_dtsi_path"] == str(pl_dtsi)
        assert data["merged"] == str(output_dir / "test.dts")
