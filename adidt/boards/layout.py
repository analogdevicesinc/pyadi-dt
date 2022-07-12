from jinja2 import Environment, FileSystemLoader
import os


class layout:
    """Common Layout Class for DT generation templates."""

    includes = [""]

    template_filename = None
    output_filename = None

    # def gen_dt_preprocess(self, **kwargs):
    #     return kwargs

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
        loc = os.path.join(loc, "..", "templates")
        file_loader = FileSystemLoader(loc)
        env = Environment(loader=file_loader)

        loc = os.path.join(self.template_filename)
        template = env.get_template(loc)

        kwargs = self.gen_dt_preprocess(**kwargs)
        output = template.render(**kwargs)

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
