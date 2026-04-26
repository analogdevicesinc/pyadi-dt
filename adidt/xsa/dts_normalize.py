"""DTS post-processing helpers shared between the merger and test harness.

These functions operate on a preprocessed DTS file on disk and rewrite
it in place to work around known sdtgen output quirks.  Both the
merger's optional ``dtc`` smoke test and the hardware test harness's
``compile_dts_to_dtb`` need the same fix-ups, so they live here.
"""

from __future__ import annotations

import re
from pathlib import Path


_ROOT_BLOCK_OPEN_RE = re.compile(r"^/ \{", re.M)


def dedup_zynqmp_root_nodes(pp_dts: Path) -> None:
    """Rewrite *pp_dts* to remove the duplicate sdtgen ZynqMP root block.

    sdtgen for ZynqMP generates ``system-top.dts`` that ``#include``s
    ``zynqmp.dtsi``, ``zynqmp-clk-ccf.dtsi``, and ``pl.dtsi``.  After
    ``cpp`` preprocessing, the file has 4 ``/ { ... };`` blocks:

    * Block 0: ``zynqmp.dtsi`` (canonical A53 CPU, peripherals, clocks)
    * Block 1: ``zynqmp-clk-ccf.dtsi`` (PS reference clock)
    * Block 2: ``pl.dtsi`` (FPGA PL bus with all AXI IPs)
    * Block 3: ``system-top.dts`` (sdtgen re-declaration of cpus,
      amba_pl, etc.)

    Block 3 duplicates everything already defined in Blocks 0-2 and
    causes ``dtc`` ``duplicate_node_names`` errors.  Remove it
    entirely — the content after Block 3 (overlay ``&label { ... }``
    references appended by the merger) is preserved.

    The ``chosen`` and ``aliases`` sub-nodes from Block 3 are required
    for console output and device aliasing, so they're spliced into a
    new minimal root block before the trailing overlay references.

    Also renames the MicroBlaze PMU CPU node label collision
    (``cpus_microblaze_0: cpus`` clashes with ``cpus_a53: cpus`` from
    ``zynqmp.dtsi``).  The MicroBlaze PMU CPU node only carries
    address-map metadata so the rename is a no-op for the running OS.

    No-op when the file does not match the ZynqMP sdtgen pattern (fewer
    than 4 root blocks).
    """
    text = pp_dts.read_text()

    root_blocks: list[tuple[int, int]] = []
    for m in _ROOT_BLOCK_OPEN_RE.finditer(text):
        start = m.start()
        depth = 0
        for i in range(m.end() - 1, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    if end < len(text) and text[end] == ";":
                        end += 1
                    if end < len(text) and text[end] == "\n":
                        end += 1
                    root_blocks.append((start, end))
                    break

    if len(root_blocks) >= 4:
        last_start, last_end = root_blocks[-1]
        last_block = text[last_start:last_end]

        preserved: list[str] = []
        for node_name in ("chosen", "aliases"):
            node_re = re.compile(
                rf"^ {node_name}\b[^\{{]*\{{.*?^ \}};",
                re.M | re.S,
            )
            m = node_re.search(last_block)
            if m:
                preserved.append(m.group())

        text = text[:last_start] + text[last_end:]

        if preserved:
            preserved_block = "/ {\n" + "\n".join(preserved) + "\n};\n"
            text = text.rstrip() + "\n\n" + preserved_block + "\n"

    text = text.replace(
        "cpus_microblaze_0: cpus {",
        "cpus_microblaze_0: cpus-pmu {",
    )

    pp_dts.write_text(text)
