import subprocess
import stat
from unittest.mock import patch, MagicMock
import pytest

from adidt.xsa.parse.sdtgen import SdtgenRunner
from adidt.xsa.exceptions import SdtgenNotFoundError, SdtgenError


def _help_result():
    r = MagicMock()
    r.returncode = 0
    r.stdout = "sdtgen -s <xsa> -d <outdir>"
    r.stderr = ""
    return r


def _ok_result():
    r = MagicMock()
    r.returncode = 0
    r.stdout = ""
    r.stderr = ""
    return r


def _help_result_eval_only():
    r = MagicMock()
    r.returncode = 0
    r.stdout = "Usage: sdtgen [options]\\n  -eval tclcommand\\n"
    r.stderr = ""
    return r


def _help_illegal_option_result():
    r = MagicMock()
    r.returncode = 1
    r.stdout = ""
    r.stderr = "error: illegal option '--help'"
    return r


def test_run_invokes_sdtgen_with_correct_args(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "system-top.dts").write_text("/dts-v1/;")

    # New runner per test avoids module-level cache interference
    runner = SdtgenRunner()
    with patch(
        "adidt.xsa.parse.sdtgen.subprocess.run", side_effect=[_help_result(), _ok_result()]
    ) as mock_run:
        result = runner.run(xsa, out_dir)

    # The second call is the actual sdtgen invocation
    sdtgen_call = mock_run.call_args_list[1]
    cmd = sdtgen_call[0][0]
    assert cmd[0] == "sdtgen"
    assert str(xsa) in cmd
    assert str(out_dir) in cmd
    assert result == out_dir / "system-top.dts"


def test_run_raises_not_found_when_binary_missing(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    runner = SdtgenRunner()
    with patch("adidt.xsa.parse.sdtgen.subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(SdtgenNotFoundError):
            runner.run(xsa, out_dir)


def test_run_discovers_vitis_settings_on_missing_binary(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "system-top.dts").write_text("/dts-v1/;")
    settings_script = tmp_path / "settings64.sh"
    settings_script.write_text("echo sourced")

    runner = SdtgenRunner()
    with (
        patch.object(
            SdtgenRunner, "_find_vitis_settings_script", return_value=settings_script
        ),
        patch(
            "adidt.xsa.parse.sdtgen.subprocess.run",
            side_effect=[FileNotFoundError, _help_result(), _ok_result()],
        ) as mock_run,
    ):
        result = runner.run(xsa, out_dir)

    assert mock_run.call_args_list[0][0][0] == ["sdtgen", "--help"]
    assert mock_run.call_args_list[1][0][0][:2] == ["bash", "-lc"]
    assert "source" in mock_run.call_args_list[1][0][0][2]
    assert mock_run.call_args_list[2][0][0][:2] == ["bash", "-lc"]
    assert str(settings_script) in mock_run.call_args_list[1][0][0][2]
    assert result == out_dir / "system-top.dts"


def test_run_raises_error_on_nonzero_exit(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    fail_result = MagicMock()
    fail_result.returncode = 1
    fail_result.stderr = "fatal: bad xsa"
    fail_result.stdout = ""

    runner = SdtgenRunner()
    with patch(
        "adidt.xsa.parse.sdtgen.subprocess.run", side_effect=[_help_result(), fail_result]
    ):
        with pytest.raises(SdtgenError) as exc_info:
            runner.run(xsa, out_dir)
    assert "fatal: bad xsa" in exc_info.value.stderr


def test_run_raises_error_on_timeout(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    runner = SdtgenRunner()
    with patch(
        "adidt.xsa.parse.sdtgen.subprocess.run",
        side_effect=[_help_result(), subprocess.TimeoutExpired("sdtgen", 5)],
    ):
        with pytest.raises(SdtgenError, match="timed out"):
            runner.run(xsa, out_dir, timeout=5)


def test_run_scans_for_dts_when_system_top_absent(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "other_name.dts").write_text("/dts-v1/;")

    runner = SdtgenRunner()
    with patch(
        "adidt.xsa.parse.sdtgen.subprocess.run", side_effect=[_help_result(), _ok_result()]
    ):
        result = runner.run(xsa, out_dir)
    assert result == out_dir / "other_name.dts"


def test_run_raises_error_when_no_dts_produced(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    runner = SdtgenRunner()
    with patch(
        "adidt.xsa.parse.sdtgen.subprocess.run", side_effect=[_help_result(), _ok_result()]
    ):
        with pytest.raises(SdtgenError, match=r"no \.dts output"):
            runner.run(xsa, out_dir)


def test_help_timeout_raises_sdtgen_error(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    runner = SdtgenRunner()
    with patch(
        "adidt.xsa.parse.sdtgen.subprocess.run",
        side_effect=subprocess.TimeoutExpired("sdtgen", 10),
    ):
        with pytest.raises(SdtgenError, match="timed out"):
            runner.run(xsa, out_dir)


def test_run_uses_eval_mode_for_2025_style_sdtgen(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "system-top.dts").write_text("/dts-v1/;")

    runner = SdtgenRunner()
    with patch(
        "adidt.xsa.parse.sdtgen.subprocess.run",
        side_effect=[_help_result_eval_only(), _ok_result()],
    ) as mock_run:
        result = runner.run(xsa, out_dir)

    sdtgen_call = mock_run.call_args_list[1]
    cmd = sdtgen_call[0][0]
    assert cmd[0] == "sdtgen"
    assert cmd[1] == "-eval"
    assert "set_dt_param" in cmd[2]
    assert str(xsa) in cmd[2]
    assert str(out_dir) in cmd[2]
    assert "generate_sdt" in cmd[2]
    assert result == out_dir / "system-top.dts"


def test_run_falls_back_to_dash_help_when_long_help_is_invalid(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "system-top.dts").write_text("/dts-v1/;")

    runner = SdtgenRunner()
    with patch(
        "adidt.xsa.parse.sdtgen.subprocess.run",
        side_effect=[
            _help_illegal_option_result(),
            _help_result_eval_only(),
            _ok_result(),
        ],
    ) as mock_run:
        result = runner.run(xsa, out_dir)

    assert mock_run.call_args_list[0][0][0][:2] == ["sdtgen", "--help"]
    assert mock_run.call_args_list[1][0][0][:2] == ["sdtgen", "-help"]
    sdtgen_call = mock_run.call_args_list[2]
    cmd = sdtgen_call[0][0]
    assert cmd[1] == "-eval"
    assert result == out_dir / "system-top.dts"


def test_run_postprocesses_sdtgen_cpu_and_interrupt_nodes(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "system-top.dts").write_text(
        '/dts-v1/;\n#include "zynqmp.dtsi"\n/ {\n\tcpus_a53: cpus-a53@0 {\n\t};\n};\n'
    )
    (out_dir / "zynqmp.dtsi").write_text(
        "/ {\n\ttimer {\n\t\tinterrupt-parent = <&imux>;\n\t};\n};\n"
    )
    (out_dir / "pl.dtsi").write_text(
        "/ {\n\taxi_intc {\n\t\tinterrupt-parent = <&imux>;\n\t};\n};\n"
    )

    runner = SdtgenRunner()
    with patch(
        "adidt.xsa.parse.sdtgen.subprocess.run", side_effect=[_help_result(), _ok_result()]
    ):
        runner.run(xsa, out_dir)

    system_top = (out_dir / "system-top.dts").read_text()
    zynqmp = (out_dir / "zynqmp.dtsi").read_text()
    pl = (out_dir / "pl.dtsi").read_text()

    assert "cpus-a53@0" not in system_top
    assert "cpus_a53: cpus {" in system_top
    assert "<&imux>" not in zynqmp
    assert "<&imux>" not in pl
    assert "<&gic_a53>" in zynqmp
    assert "<&gic_a53>" in pl


def test_run_postprocesses_readonly_dtsi(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "system-top.dts").write_text("/dts-v1/;\n/ {}\n")

    zynqmp = out_dir / "zynqmp.dtsi"
    zynqmp.write_text("/ {\n\ttimer {\n\t\tinterrupt-parent = <&imux>;\n\t};\n};\n")
    zynqmp.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

    runner = SdtgenRunner()
    with patch(
        "adidt.xsa.parse.sdtgen.subprocess.run", side_effect=[_help_result(), _ok_result()]
    ):
        runner.run(xsa, out_dir)

    assert "<&imux>" not in zynqmp.read_text()


def test_run_disables_problematic_rpu_ipi_nodes(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "system-top.dts").write_text("/dts-v1/;\n/ {}\n")
    (out_dir / "pcw.dtsi").write_text(
        '&ipi3 {\n\tstatus = "okay";\n};\n'
        '&ipi4 {\n\tstatus = "okay";\n};\n'
        '&ipi7 {\n\tstatus = "okay";\n};\n'
    )

    runner = SdtgenRunner()
    with patch(
        "adidt.xsa.parse.sdtgen.subprocess.run", side_effect=[_help_result(), _ok_result()]
    ):
        runner.run(xsa, out_dir)

    pcw = (out_dir / "pcw.dtsi").read_text()
    assert '&ipi3 {\n\tstatus = "disabled";' in pcw
    assert '&ipi4 {\n\tstatus = "disabled";' in pcw
    assert '&ipi7 {\n\tstatus = "okay";' in pcw


def test_run_adds_missing_sdhci1_properties(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "system-top.dts").write_text("/dts-v1/;\n/ {}\n")
    (out_dir / "pcw.dtsi").write_text(
        (
            'smmu: iommu@fd800000 { status = "disabled"; };\n'
            "sdhci1: mmc@ff170000 {\n"
            '\tstatus = "okay";\n'
            "\tinterrupt-parent = <&gic_a53>;\n"
            "\tinterrupts = <0 49 4>;\n"
            "};\n"
        )
    )

    runner = SdtgenRunner()
    with patch(
        "adidt.xsa.parse.sdtgen.subprocess.run", side_effect=[_help_result(), _ok_result()]
    ):
        runner.run(xsa, out_dir)

    pcw = (out_dir / "pcw.dtsi").read_text()
    assert "iommus = <&smmu 0x871>;" in pcw
    assert "no-1-8-v;" in pcw


def test_run_adds_missing_sdhci1_properties_for_ref_block(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "system-top.dts").write_text("/dts-v1/;\n/ {}\n")
    (out_dir / "pcw.dtsi").write_text(
        '&sdhci1 {\n\tstatus = "okay";\n\tclock-names = "clk_xin", "clk_ahb";\n};\n'
    )

    runner = SdtgenRunner()
    with patch(
        "adidt.xsa.parse.sdtgen.subprocess.run", side_effect=[_help_result(), _ok_result()]
    ):
        runner.run(xsa, out_dir)

    pcw = (out_dir / "pcw.dtsi").read_text()
    assert "iommus = <&smmu 0x871>;" in pcw
    assert "no-1-8-v;" in pcw


def test_run_sanitizes_non_ddr_memory_nodes(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "system-top.dts").write_text("/dts-v1/;\n/ {}\n")
    (out_dir / "pcw.dtsi").write_text(
        "/ {\n"
        "  psu_ocm_ram_0_memory: memory@FFFC0000 {\n"
        '    compatible = "xlnx,psu-ocm-ram-0-1.0" , "mmio-sram";\n'
        '    device_type = "memory";\n'
        '    memory_type = "memory";\n'
        "    reg = <0x0 0xFFFC0000 0x0 0x40000>;\n"
        "  };\n"
        "  psu_ddr_0_memory: memory@0 {\n"
        '    compatible = "xlnx,psu-ddr-1.0";\n'
        '    device_type = "memory";\n'
        '    memory_type = "memory";\n'
        "    reg = <0x0 0x0 0x0 0x7FF00000>;\n"
        "  };\n"
        "  psu_ddr_1_memory: memory@800000000 {\n"
        '    compatible = "xlnx,psu-ddr-1.0";\n'
        '    device_type = "memory";\n'
        '    memory_type = "memory";\n'
        "    reg = <0x00000008 0x00000000 0x0 0x80000000>;\n"
        "  };\n"
        "  psu_qspi_linear_0_memory: memory@c0000000 {\n"
        '    compatible = "xlnx,psu-qspi-linear-1.0-memory";\n'
        '    device_type = "memory";\n'
        '    memory_type = "linear_flash";\n'
        "    reg = <0x0 0xc0000000 0x0 0x20000000>;\n"
        "  };\n"
        "};\n"
    )

    runner = SdtgenRunner()
    with patch(
        "adidt.xsa.parse.sdtgen.subprocess.run", side_effect=[_help_result(), _ok_result()]
    ):
        runner.run(xsa, out_dir)

    pcw = (out_dir / "pcw.dtsi").read_text()
    assert "psu_ddr_0_memory: memory@0" in pcw
    assert "psu_ddr_1_memory: memory@800000000" in pcw
    assert "psu_ocm_ram_0_memory: memory@FFFC0000" in pcw
    assert "psu_qspi_linear_0_memory: memory@c0000000" in pcw
    assert (
        'psu_ocm_ram_0_memory: memory@FFFC0000 {\n    compatible = "xlnx,psu-ocm-ram-0-1.0" , "mmio-sram";\n    memory_type = "memory";'
        in pcw
    )
    assert (
        'psu_qspi_linear_0_memory: memory@c0000000 {\n    compatible = "xlnx,psu-qspi-linear-1.0-memory";\n    memory_type = "linear_flash";'
        in pcw
    )


def test_run_adds_missing_gem3_iommu_property(tmp_path):
    xsa = tmp_path / "design.xsa"
    xsa.write_bytes(b"fake")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "system-top.dts").write_text("/dts-v1/;\n/ {}\n")
    (out_dir / "pcw.dtsi").write_text(
        (
            'smmu: iommu@fd800000 { status = "okay"; };\n'
            "gem3: ethernet@ff0e0000 {\n"
            '\tstatus = "okay";\n'
            '\tphy-mode = "rgmii-id";\n'
            "};\n"
        )
    )

    runner = SdtgenRunner()
    with patch(
        "adidt.xsa.parse.sdtgen.subprocess.run", side_effect=[_help_result(), _ok_result()]
    ):
        runner.run(xsa, out_dir)

    pcw = (out_dir / "pcw.dtsi").read_text()
    assert "iommus = <&smmu 0x877>;" in pcw
