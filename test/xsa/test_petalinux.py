"""Unit tests for PetaLinux integration formatter."""

import pytest
from pathlib import Path

from adidt.xsa.petalinux import PetalinuxFormatter, validate_petalinux_project


# Sample overlay content matching the format produced by DtsMerger._build_overlay
SAMPLE_OVERLAY = """\
/dts-v1/;
/plugin/;

/*
 * ADI Device Tree Overlay — fmcdaq2_zcu102
 *
 * Apply alongside the base DTB:
 *   dtoverlay fmcdaq2_zcu102.dtso
 *
 * Or compile and load manually:
 *   dtc -@ -I dts -O dtb -o fmcdaq2_zcu102.dtbo fmcdaq2_zcu102.dtso
 */

&amba {
\t/* --- Clock Generators --- */
\ttest_clock_node;
};
&spi0 {
\tclk0_ad9523: ad9523_1@0 {
\t\tcompatible = "adi,ad9523";
\t\treg = <0>;
\t};
};
&axi_ad9680_jesd204_rx {
\tcompatible = "adi,axi-jesd204-rx-1.0";
};
"""


class TestPetalinuxFormatter:
    def test_strips_plugin_header(self):
        result = PetalinuxFormatter().format_system_user_dtsi(SAMPLE_OVERLAY)
        assert "/dts-v1/;" not in result
        assert "/plugin/;" not in result

    def test_strips_file_header_comment(self):
        result = PetalinuxFormatter().format_system_user_dtsi(SAMPLE_OVERLAY)
        assert "ADI Device Tree Overlay" not in result
        assert "dtoverlay" not in result

    def test_adds_system_conf_include(self):
        result = PetalinuxFormatter().format_system_user_dtsi(SAMPLE_OVERLAY)
        assert '#include "system-conf.dtsi"' in result

    def test_adds_system_conf_for_modern_petalinux(self):
        result = PetalinuxFormatter().format_system_user_dtsi(
            SAMPLE_OVERLAY, petalinux_version="2024.1"
        )
        assert '#include "system-conf.dtsi"' in result

    def test_skips_system_conf_for_old_petalinux(self):
        result = PetalinuxFormatter().format_system_user_dtsi(
            SAMPLE_OVERLAY, petalinux_version="2019.2"
        )
        assert '#include "system-conf.dtsi"' not in result

    def test_preserves_node_content(self):
        result = PetalinuxFormatter().format_system_user_dtsi(SAMPLE_OVERLAY)
        assert "&spi0 {" in result
        assert "ad9523_1@0" in result
        assert "&axi_ad9680_jesd204_rx {" in result
        assert 'compatible = "adi,axi-jesd204-rx-1.0"' in result

    def test_preserves_amba_for_zynq(self):
        result = PetalinuxFormatter().format_system_user_dtsi(
            SAMPLE_OVERLAY, platform="zc706"
        )
        assert "&amba {" in result
        assert "&amba_pl {" not in result

    def test_rewrites_amba_to_amba_pl_for_zynqmp(self):
        result = PetalinuxFormatter().format_system_user_dtsi(
            SAMPLE_OVERLAY, platform="zcu102"
        )
        assert "&amba_pl {" in result
        assert "&amba {" not in result

    def test_rewrites_amba_for_zu11eg(self):
        result = PetalinuxFormatter().format_system_user_dtsi(
            SAMPLE_OVERLAY, platform="zu11eg"
        )
        assert "&amba_pl {" in result

    def test_no_rewrite_when_platform_none(self):
        result = PetalinuxFormatter().format_system_user_dtsi(
            SAMPLE_OVERLAY, platform=None
        )
        assert "&amba {" in result

    def test_has_spdx_header(self):
        result = PetalinuxFormatter().format_system_user_dtsi(SAMPLE_OVERLAY)
        assert "SPDX-License-Identifier" in result

    def test_has_pyadi_dt_provenance(self):
        result = PetalinuxFormatter().format_system_user_dtsi(SAMPLE_OVERLAY)
        assert "pyadi-dt" in result

    def test_no_leading_blank_lines_before_content(self):
        result = PetalinuxFormatter().format_system_user_dtsi(SAMPLE_OVERLAY)
        lines = result.splitlines()
        # After SPDX header and include, first non-empty content should not have
        # excessive blank lines
        found_include = False
        blank_count = 0
        for ln in lines:
            if "system-conf" in ln:
                found_include = True
                continue
            if found_include:
                if not ln.strip():
                    blank_count += 1
                else:
                    break
        assert blank_count <= 1

    def test_handles_empty_overlay(self):
        result = PetalinuxFormatter().format_system_user_dtsi("/dts-v1/;\n/plugin/;\n")
        assert "SPDX-License-Identifier" in result
        assert "/dts-v1/;" not in result

    def test_handles_overlay_without_header_comment(self):
        minimal = "/dts-v1/;\n/plugin/;\n\n&spi0 {\n\ttest;\n};\n"
        result = PetalinuxFormatter().format_system_user_dtsi(minimal)
        assert "&spi0 {" in result
        assert "/dts-v1/;" not in result


class TestBbappendGeneration:
    def test_bbappend_content(self):
        result = PetalinuxFormatter().generate_bbappend()
        assert "FILESEXTRAPATHS" in result
        assert "${THISDIR}/files" in result

    def test_bbappend_ends_with_newline(self):
        result = PetalinuxFormatter().generate_bbappend()
        assert result.endswith("\n")


class TestValidatePetalinuxProject:
    def test_valid_project(self, tmp_path):
        dt_files = (
            tmp_path
            / "project-spec"
            / "meta-user"
            / "recipes-bsp"
            / "device-tree"
            / "files"
        )
        dt_files.mkdir(parents=True)
        # Should not raise
        validate_petalinux_project(tmp_path)

    def test_invalid_project_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Not a valid PetaLinux project"):
            validate_petalinux_project(tmp_path)

    def test_invalid_project_suggests_petalinux_config(self, tmp_path):
        with pytest.raises(ValueError, match="petalinux-config"):
            validate_petalinux_project(tmp_path)

    def test_partial_structure_raises(self, tmp_path):
        (tmp_path / "project-spec" / "meta-user").mkdir(parents=True)
        with pytest.raises(ValueError):
            validate_petalinux_project(tmp_path)
