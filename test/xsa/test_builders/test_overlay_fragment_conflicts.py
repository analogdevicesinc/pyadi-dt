"""DTC accepts duplicate fragment writes that Linux's OF overlay rejects."""

import shutil
import subprocess

import pytest

from adidt.xsa.build.builders.adrv9009 import ADRV9009Builder
from adidt.xsa.build.builders.adrv937x import ADRV937xBuilder


@pytest.mark.skipif(
    not shutil.which("dtc") or not shutil.which("fdtget"), reason="DTC tools required"
)
@pytest.mark.parametrize(
    "builder,fixture",
    [(ADRV9009Builder, "topo_adrv9009"), (ADRV937xBuilder, "topo_adrv937x")],
)
def test_fragments_do_not_write_same_target_property(
    builder, fixture, request, tmp_path
):
    topology = request.getfixturevalue(fixture)
    nodes = builder().build_nodes(None, topology, {}, "clkc", 15, "gpio")
    source = tmp_path / "overlay.dts"
    source.write_text("/dts-v1/; /plugin/;\n" + "\n".join(nodes))
    blob = tmp_path / "overlay.dtbo"
    subprocess.run(["dtc", "-@", "-O", "dtb", "-o", str(blob), str(source)], check=True)

    def read(*args):
        return subprocess.check_output(["fdtget", str(blob), *args], text=True).split()

    seen = set()
    for label in read("-p", "/__fixups__"):
        for location in read("-t", "s", "/__fixups__", label):
            if not location.endswith(":target:0"):
                continue
            fragment = location.split(":")[0]
            for prop in read("-p", fragment + "/__overlay__"):
                key = (label, prop)
                assert key not in seen, f"Multiple fragments update {label}/{prop}"
                seen.add(key)
