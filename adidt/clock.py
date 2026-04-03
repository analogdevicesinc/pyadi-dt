import adidt.dt as dt
import adidt.parts as parts  # noqa: F401 - Used in eval()


class clock(dt):
    """Device tree interface with clock-chip configuration support."""

    supported_parts = ["HMC7044", "AD9523-1", "AD9545"]

    def _to_class_naming(self, name):
        """Convert a part name such as 'HMC7044' or 'AD9523-1' to its module class name."""
        return name.lower().replace("-", "_")

    def set(self, part: str, config, append=False):
        """Apply a JIF configuration dict to the named clock part's DT node.

        Args:
            part (str): Clock part name, must be in supported_parts.
            config: JIF configuration struct for the clock part.
            append (bool): If True, append to existing subnodes rather than replacing them.

        Raises:
            Exception: If the part is not supported or its DT node cannot be found.
        """
        if part not in self.supported_parts:
            raise Exception(f"Unknown or unsupported part: {part}")

        dev = eval(f"parts.{self._to_class_naming(part)}_dt()")

        # Check if node in dt
        node = self.get_node_by_compatible(dev.compatible_id)
        if not node:
            raise Exception(f"No DT node found for {part} ({dev.compatible_id})")
        if len(node) > 1:
            raise Exception(
                f"Too many nodes found with name {dev.compatible_id}. Must supply node name"
            )

        dev.set_dt_node_from_config(node[0], config, append)
