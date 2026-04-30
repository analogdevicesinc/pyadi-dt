"""Unit tests for adidt.xsa.merge.dts_normalize.dedup_zynqmp_root_nodes."""

from __future__ import annotations

import textwrap

from adidt.xsa.merge.dts_normalize import dedup_zynqmp_root_nodes


def _write(tmp_path, body: str):
    p = tmp_path / "pp.dts"
    p.write_text(textwrap.dedent(body).lstrip("\n"))
    return p


def test_dedup_zynqmp_root_nodes_drops_fourth_block(tmp_path):
    """A 4-root-block input loses the last (sdtgen system-top) block."""
    p = _write(
        tmp_path,
        """
        /dts-v1/;
        / {
         block0_marker;
        };
        / {
         block1_marker;
        };
        / {
         block2_marker;
        };
        / {
         block3_marker;
        };
        """,
    )
    dedup_zynqmp_root_nodes(p)
    text = p.read_text()
    assert "block0_marker" in text
    assert "block1_marker" in text
    assert "block2_marker" in text
    assert "block3_marker" not in text


def test_dedup_zynqmp_root_nodes_preserves_chosen_and_aliases(tmp_path):
    """``chosen`` and ``aliases`` from the dropped block re-appear at EOF."""
    p = _write(
        tmp_path,
        """
        /dts-v1/;
        / {
         block0;
        };
        / {
         block1;
        };
        / {
         block2;
        };
        / {
         chosen {
          stdout-path = "serial0:115200n8";
         };
         aliases {
          serial0 = "/amba/serial@e0001000";
         };
         dropped_other;
        };
        &amba {
         post_marker;
        };
        """,
    )
    dedup_zynqmp_root_nodes(p)
    text = p.read_text()
    assert "dropped_other" not in text
    assert "stdout-path" in text
    assert 'serial0 = "/amba/serial@e0001000"' in text
    assert "post_marker" in text  # trailing &label refs preserved


def test_dedup_zynqmp_root_nodes_renames_microblaze_pmu_cpus(tmp_path):
    """The MicroBlaze PMU ``cpus`` label gets renamed to ``cpus-pmu``.

    Avoids the duplicate ``cpus`` node-name conflict with the A53 ``cpus``
    block that ``zynqmp.dtsi`` includes.
    """
    p = _write(
        tmp_path,
        """
        /dts-v1/;
        / {
         block0;
        };
        cpus_microblaze_0: cpus {
         pmu_node;
        };
        """,
    )
    dedup_zynqmp_root_nodes(p)
    text = p.read_text()
    assert "cpus_microblaze_0: cpus-pmu {" in text
    assert "cpus_microblaze_0: cpus {" not in text


def test_dedup_zynqmp_root_nodes_no_op_when_fewer_than_four_blocks(tmp_path):
    """A 3-root-block input is left alone (Zynq-7000 / non-ZynqMP)."""
    body = textwrap.dedent(
        """
        /dts-v1/;
        / {
         block0;
        };
        / {
         block1;
        };
        / {
         block2;
        };
        """
    ).lstrip("\n")
    p = tmp_path / "pp.dts"
    p.write_text(body)
    dedup_zynqmp_root_nodes(p)
    assert p.read_text() == body
