"""Normalize duplicate CPU metadata in sdtgen's preprocessed ZynqMP trees."""

from __future__ import annotations

import re
from pathlib import Path

_CPU_NODE = re.compile(r"(?m)^[ \t]*(cpus_\w+)\s*:\s*[\w@-]+\s*\{")


def dedup_zynqmp_root_nodes(pp_dts: Path) -> None:
    """Remove repeated CPU cluster declarations while retaining board data.

    System device-tree output repeats CPU cluster labels from zynqmp.dtsi.
    Only the later declarations are metadata duplicates. Their containing root
    block also defines DDR, aliases, chosen and board properties, all of which
    must survive compilation. Root-block count is not a reliable discriminator.
    """
    text = pp_dts.read_text()
    seen: set[str] = set()
    removals: list[tuple[int, int]] = []
    for match in _CPU_NODE.finditer(text):
        label = match.group(1)
        if label not in seen:
            seen.add(label)
            continue
        depth = 1
        for pos in range(match.end(), len(text)):
            if text[pos] == "{":
                depth += 1
            elif text[pos] == "}":
                depth -= 1
                if depth == 0:
                    end = pos + 1
                    if text[end : end + 1] == ";":
                        end += 1
                    removals.append((match.start(), end))
                    break
    for start, end in reversed(removals):
        text = text[:start] + text[end:]
    text = text.replace("cpus_microblaze_0: cpus {", "cpus_microblaze_0: cpus-pmu {")
    pp_dts.write_text(text)
