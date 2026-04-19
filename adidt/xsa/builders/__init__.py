"""Per-board builder modules for the XSA-to-DeviceTree pipeline.

Each builder implements the :class:`BoardBuilder` protocol and is responsible
for a single board family (e.g., FMCDAQ2, AD9084).  The :class:`NodeBuilder`
iterates registered builders, calling :meth:`matches` to determine which
builder handles the current topology, then :meth:`build_nodes` to generate
the DTS node strings.

Adding a new board family:

1. Create ``builders/new_board.py`` implementing :class:`BoardBuilder`.
2. Add it to :data:`DEFAULT_BUILDERS` below.
3. No changes to ``node_builder.py`` or ``pipeline.py`` are needed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..topology import XsaTopology


@runtime_checkable
class BoardBuilder(Protocol):
    """Protocol for board-family specific DTS node builders.

    Each builder is responsible for:

    - Detecting whether a given topology + config matches this board family.
    - Generating all DTS node strings for the matched design.
    - Reporting which JESD/clkgen/converter instances it handles (so the
      generic rendering loop in NodeBuilder can skip them).
    """

    def matches(self, topology: "XsaTopology", cfg: dict[str, Any]) -> bool:
        """Return True if *topology* and *cfg* represent this board family."""
        ...

    def build_nodes(
        self,
        node_builder: Any,
        topology: "XsaTopology",
        cfg: dict[str, Any],
        ps_clk_label: str,
        ps_clk_index: int | None,
        gpio_label: str,
    ) -> list[str]:
        """Generate DTS node strings for this board family.

        Args:
            node_builder: The owning :class:`NodeBuilder` instance, providing
                access to ``_render()``, ``_wrap_spi_bus()``, and other shared
                infrastructure.
            topology: Parsed XSA topology.
            cfg: Raw pipeline config dict.
            ps_clk_label: Platform PS clock label (e.g., ``"zynqmp_clk"``).
            ps_clk_index: Platform PS clock index (e.g., ``71``).
            gpio_label: Platform GPIO controller label.

        Returns:
            List of DTS node strings to append to ``result["converters"]``.
        """
        ...

    def skips_generic_jesd(self) -> bool:
        """Return True if this builder handles its own JESD/clkgen rendering.

        When True, the generic JESD RX/TX and converter rendering loops in
        ``NodeBuilder.build()`` will skip instances that belong to this design.
        """
        ...

    def skip_ip_types(self) -> set[str]:
        """Return the set of converter IP types handled by this builder.

        Used by the generic converter rendering loop to skip converters
        that this builder will render itself.
        """
        ...
