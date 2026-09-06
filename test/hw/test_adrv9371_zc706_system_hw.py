"""Boot the AD9371 tree composed through System, without XSA node generation."""

from pathlib import Path

import pytest

import adidt
from adidt.xsa.build.board_fixups import apply_board_fixups
from adidt.xsa.merge.merger import DtsMerger
from adidt.xsa.parse.sdtgen import SdtgenRunner
from adidt.xsa.parse.topology import XsaParser
from test.hw._system_base import boot_and_verify_from_merged_dts, requires_lg
from test.hw.test_adrv9371_zc706_hw import SPEC
from test.hw.hw_helpers import DEFAULT_OUT_DIR


@requires_lg
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_adrv9371_zc706_system_hw(board, tmp_path, request):
    xsa = SPEC.xsa_resolver(tmp_path)
    topology = XsaParser().parse(xsa)
    out_dir = DEFAULT_OUT_DIR / "adrv9371_system"
    out_dir.mkdir(parents=True, exist_ok=True)
    base_dir = out_dir / "base"
    base = SdtgenRunner().run(xsa, base_dir, timeout=300)
    apply_board_fixups("adrv937x_zc706", base_dir)
    fmc = adidt.eval.adrv937x_fmc()
    fpga = adidt.fpga.zc706()
    system = adidt.System(name="adrv9371_system", components=[fmc, fpga])
    system.apply_xsa_topology(topology)
    system.connect_spi(bus_index=0, primary=fpga.spi[0], secondary=fmc.clock.spi, cs=0)
    system.connect_spi(
        bus_index=0, primary=fpga.spi[0], secondary=fmc.converter.spi, cs=1
    )
    system.add_link(
        source=fmc.converter,
        sink=fpga.gt[0],
        sink_reference_clock=fmc.xcvr_refclk,
        sink_core_clock=fmc.dev_clk,
        sink_sysref=fmc.sysref_dev,
    )
    system.add_link(
        source=fpga.gt[1],
        sink=fmc.converter,
        source_reference_clock=fmc.xcvr_refclk,
        source_core_clock=fmc.dev_clk,
        sink_sysref=fmc.sysref_fmc,
    )
    model = system.to_board_model()
    nodes = adidt.BoardModelRenderer().render(model)
    DtsMerger().merge(Path(base).read_text(), nodes, out_dir, system.name)
    boot_and_verify_from_merged_dts(
        SPEC,
        out_dir / f"{system.name}.dts",
        board=board,
        request=request,
        out_dir=out_dir,
        dtb_basename=f"{system.name}.dtb",
    )
