from jinja2 import Environment, FileSystemLoader
import os

from ..model.renderer import BoardModelRenderer


class layout:
    """Common Layout Class for DT generation templates."""

    includes = [""]

    template_filename = None
    output_filename = None
    use_plugin_mode = True  # Set to False for standalone DTS (not overlay)

    def gen_dt_preprocess(self, **kwargs):
        """Pre-process template context before rendering; override to inject extra variables."""
        return kwargs

    def gen_dt(self, **kwargs):
        """Generate the DT file from configuration structs.

        Raises:
            Exception: If the template file does not exist.
            Exception: If the output filename is not defined.

        Args:
            kwargs: Configuration structs.
        """
        if not self.template_filename:
            raise Exception("No template file specified")

        if not self.output_filename:
            raise Exception("No output file specified")

        # Import template
        loc = os.path.dirname(__file__)
        loc = os.path.join(loc, "..", "templates", "boards")
        file_loader = FileSystemLoader(loc)
        env = Environment(loader=file_loader)

        loc = os.path.join(self.template_filename)
        template = env.get_template(loc)

        kwargs = self.gen_dt_preprocess(**kwargs)
        # Construct the context for rendering the template
        render_context = {
            "base_dts_include": self.platform_config["base_dts_include"],
        }
        render_context.update(kwargs)  # Add all other kwargs

        # Generate DTS header based on plugin mode
        if self.use_plugin_mode:
            dts_header = "/dts-v1/;\n/plugin/;\n"
            output = dts_header + template.render(**render_context)
        else:
            # For standalone DTS files, don't add any header
            # The /dts-v1/; will be provided by the include chain or kernel build system
            output = template.render(**render_context)

        with open(self.output_filename, "w") as f:
            f.write(output)

        return self.output_filename

    def gen_dt_from_model(self, model):
        """Render a :class:`~adidt.model.board_model.BoardModel` to a DTS file.

        This is the BoardModel-based alternative to :meth:`gen_dt`.  It renders
        the model via :class:`~adidt.model.renderer.BoardModelRenderer` and
        writes a standalone DTS file with appropriate headers.

        Args:
            model: A :class:`~adidt.model.board_model.BoardModel` instance.

        Returns:
            str: Path to the generated DTS file.
        """
        if not self.output_filename:
            raise Exception("No output file specified")

        nodes = BoardModelRenderer().render(model)
        # Flatten all rendered nodes into a single block
        all_nodes = []
        for key in ("clkgens", "jesd204_rx", "jesd204_tx", "converters"):
            all_nodes.extend(nodes.get(key, []))

        base_include = ""
        if (
            hasattr(self, "platform_config")
            and "base_dts_include" in self.platform_config
        ):
            base_include = self.platform_config["base_dts_include"]

        header = ""
        if self.use_plugin_mode:
            header = "/dts-v1/;\n/plugin/;\n\n"
        elif base_include:
            header = f'#include "{base_include}"\n\n'

        body = "\n\n".join(all_nodes)
        output = header + body + "\n"

        with open(self.output_filename, "w") as f:
            f.write(output)

        return self.output_filename

    def map_jesd_subclass(self, name):
        """Map JESD204 subclass to integer.

        Args:
            name (str): JESD subclass name.

        Raises:
            Exception: Invalid subclass name.

        Returns:
            int: JESD subclass integer.
        """
        modes = ["jesd204a", "jesd204b", "jesd204c"]
        if name not in modes:
            raise Exception("JESD Subclass {} not supported".format(name))
        return modes.index(name)
