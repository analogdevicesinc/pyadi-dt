from __future__ import annotations

from datetime import datetime
from typing import Any

from jinja2 import Environment, FileSystemLoader
import os

from ..model.board_model import BoardModel
from ..model.renderer import BoardModelRenderer


class layout:
    """Common Layout Class for DT generation templates."""

    includes = [""]

    template_filename: str | None = None
    output_filename: str | None = None
    use_plugin_mode: bool = True  # Set to False for standalone DTS (not overlay)
    platform_config: dict = {}
    platform: str = ""

    # Subclasses that use kernel path resolution should set this.
    DEFAULT_KERNEL_PATH: str = "./linux"

    # FPGA link keys for validate_and_default_fpga_config.
    # Subclasses set e.g. ["fpga_adc", "fpga_dac"] or ["fpga_rx", "fpga_tx", "fpga_orx"].
    FPGA_LINK_KEYS: list[str] = []
    FPGA_DEFAULT_OUT_CLK: str = "XCVR_REFCLK_DIV2"

    def __init__(self, platform: str | None = None, kernel_path: str | None = None):
        """Initialize board with platform selection and optional kernel path.

        If the subclass defines ``PLATFORM_CONFIGS``, the *platform* argument
        is validated against it and used to derive template/output filenames.

        Kernel-path resolution and validation only run when the selected
        platform config contains an ``"arch"`` key (FPGA boards).  Boards
        that don't need a kernel tree (RPi, simple SPI) can omit ``"arch"``
        and will not be affected.

        Args:
            platform: Target platform name (must be a key in ``PLATFORM_CONFIGS``).
            kernel_path: Explicit path to Linux kernel source tree. When
                *None*, falls back to ``LINUX_KERNEL_PATH`` env var, then
                ``DEFAULT_KERNEL_PATH``.

        Raises:
            ValueError: If *platform* is not in ``PLATFORM_CONFIGS``.
            FileNotFoundError: If an explicitly-provided kernel path is
                invalid or the required base DTS file is missing.
        """
        platform_configs = getattr(self, "PLATFORM_CONFIGS", None)

        if platform_configs is not None and platform is not None:
            if platform not in platform_configs:
                supported = ", ".join(platform_configs.keys())
                raise ValueError(
                    f"Platform '{platform}' not supported. "
                    f"Supported platforms: {supported}"
                )

            self.platform = platform
            self.platform_config = platform_configs[platform]

            # Derive template filename from config
            self.template_filename = self.platform_config["template_filename"]

            # Derive output filename: {ClassName}_{platform}.dts
            class_name = type(self).__name__
            base_name = f"{class_name}_{platform}.dts"
            output_dir = self.platform_config.get("output_dir")
            if output_dir is not None:
                self.output_filename = os.path.join(output_dir, base_name)
            else:
                self.output_filename = base_name

            # Kernel path resolution only applies when config has "arch"
            if "arch" in self.platform_config:
                self._kernel_path_explicit = kernel_path is not None
                self._kernel_path_from_env = kernel_path is None and bool(
                    os.environ.get("LINUX_KERNEL_PATH")
                )

                self.kernel_path = self._resolve_kernel_path(kernel_path)

                if self._kernel_path_explicit:
                    self._validate_kernel_path()
                elif self._kernel_path_from_env:
                    self._validate_kernel_path()
                elif os.path.exists(self.kernel_path):
                    try:
                        self._validate_kernel_path()
                    except FileNotFoundError:
                        pass

    def _resolve_kernel_path(self, kernel_path: str | None = None) -> str:
        """Resolve kernel source path using 3-tier priority system.

        Priority:
        1. Argument passed to ``__init__`` (highest)
        2. ``LINUX_KERNEL_PATH`` environment variable
        3. ``DEFAULT_KERNEL_PATH`` class constant (lowest)

        Args:
            kernel_path: Explicit kernel path.

        Returns:
            Resolved absolute kernel path.
        """
        if kernel_path:
            return os.path.abspath(kernel_path)

        env_path = os.environ.get("LINUX_KERNEL_PATH")
        if env_path:
            return os.path.abspath(env_path)

        return os.path.abspath(self.DEFAULT_KERNEL_PATH)

    def _validate_kernel_path(self) -> None:
        """Validate that kernel path exists and contains required DTS file.

        Skips base DTS validation when ``base_dts_file`` is ``None`` (e.g.
        VCU118 where the generated DTS is placed directly in the kernel tree).

        Raises:
            FileNotFoundError: If kernel path or base DTS file not found.
        """
        class_name = type(self).__name__
        if not os.path.exists(self.kernel_path):
            raise FileNotFoundError(
                f"Kernel source path not found: {self.kernel_path}\n"
                f"Set kernel path via:\n"
                f"  1. Pass kernel_path parameter to {class_name}()\n"
                f"  2. Set LINUX_KERNEL_PATH environment variable\n"
                f"  3. Clone kernel source to {self.DEFAULT_KERNEL_PATH}"
            )

        base_dts_file = self.platform_config.get("base_dts_file")
        if base_dts_file is None:
            return

        base_dts_path = os.path.join(self.kernel_path, base_dts_file)
        if not os.path.exists(base_dts_path):
            raise FileNotFoundError(
                f"Base DTS file not found: {base_dts_path}\n"
                f"Platform '{self.platform}' requires: {base_dts_file}"
            )

    def get_dtc_include_paths(self) -> list[str]:
        """Get list of include paths for dtc compilation.

        Returns:
            Include paths for the ``dtc -i`` option.
        """
        arch = self.platform_config["arch"]
        paths = [
            os.path.join(self.kernel_path, f"arch/{arch}/boot/dts"),
            os.path.join(self.kernel_path, f"arch/{arch}/boot/dts/xilinx"),
            os.path.join(self.kernel_path, "include"),
        ]
        return paths

    @staticmethod
    def make_ints(cfg: dict, keys: list[str]) -> dict:
        """Convert float-valued keys that are whole numbers to int in-place.

        Args:
            cfg: Configuration dict.
            keys: Keys to convert.

        Returns:
            The same dict with whole-number floats replaced by ints.
        """
        for key in keys:
            if key in cfg and isinstance(cfg[key], float) and cfg[key].is_integer():
                cfg[key] = int(cfg[key])
        return cfg

    def gen_dt_preprocess(self, **kwargs: Any) -> dict[str, Any]:
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

    def gen_dt_from_model(self, model, config_source="board_model"):
        """Render a :class:`~adidt.model.board_model.BoardModel` to a DTS file.

        This is the BoardModel-based alternative to :meth:`gen_dt`.  It renders
        the model via :class:`~adidt.model.renderer.BoardModelRenderer` and
        writes a standalone DTS file with SPDX header and metadata.

        Args:
            model: A :class:`~adidt.model.board_model.BoardModel` instance.
            config_source: Config source string for the metadata header.

        Returns:
            str: Path to the generated DTS file.
        """
        if not self.output_filename:
            raise Exception("No output file specified")

        nodes = BoardModelRenderer().render(model)
        all_nodes = []
        for key in ("clkgens", "jesd204_rx", "jesd204_tx", "converters"):
            all_nodes.extend(nodes.get(key, []))

        platform = getattr(self, "platform", "unknown")
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        base_include = ""
        if (
            hasattr(self, "platform_config")
            and "base_dts_include" in self.platform_config
        ):
            base_include = self.platform_config["base_dts_include"]

        lines = [
            "// SPDX-License-Identifier: GPL-2.0",
            f"// AUTOGENERATED BY PYADI-DT {date}",
            "/*",
            f" * Platform: {platform}",
            f" * Generated from: {config_source}",
            f" * Board model: {model.name}",
            " * Copyright (C) 2024 Analog Devices Inc.",
            " */",
            "",
        ]

        if self.use_plugin_mode:
            lines.extend(["/dts-v1/;", "/plugin/;", ""])
        elif base_include:
            lines.extend([f'#include "{base_include}"', ""])

        lines.append("\n\n".join(all_nodes))
        lines.append("")

        with open(self.output_filename, "w") as f:
            f.write("\n".join(lines))

        return self.output_filename

    def gen_dt_from_config(self, cfg, config_source="jif_solver"):
        """Generate DTS from raw solver config via BoardModel.

        Convenience method that calls :meth:`to_board_model` then
        :meth:`gen_dt_from_model`.  Subclasses must implement
        ``to_board_model(cfg)``.

        Args:
            cfg: Raw JIF solver configuration dict.
            config_source: Config source string for metadata.

        Returns:
            str: Path to the generated DTS file.
        """
        if not isinstance(cfg, dict):
            raise TypeError(f"cfg must be a dict, got {type(cfg).__name__}")
        cfg = self.validate_and_default_fpga_config(cfg)
        model = self.to_board_model(cfg)
        return self.gen_dt_from_model(model, config_source=config_source)

    def to_board_model(self, cfg: dict) -> "BoardModel":
        """Build a BoardModel from config. Subclasses must override."""
        raise NotImplementedError(
            f"{type(self).__name__} does not implement to_board_model()"
        )

    def validate_and_default_fpga_config(self, cfg: dict) -> dict:
        """Validate and apply platform defaults for FPGA configuration.

        Uses ``FPGA_LINK_KEYS`` and ``FPGA_DEFAULT_OUT_CLK`` class attributes
        to drive default population.  For each key in ``FPGA_LINK_KEYS``:

        * Ensures the key exists in *cfg* (creates an empty dict if missing).
        * Sets ``sys_clk_select`` from ``platform_config["default_fpga_{suffix}_pll"]``
          when not already present.
        * Sets ``out_clk_select`` to ``FPGA_DEFAULT_OUT_CLK`` when not already present.

        Returns *cfg* unchanged when ``FPGA_LINK_KEYS`` is empty (base default).
        """
        for key in self.FPGA_LINK_KEYS:
            if key not in cfg:
                cfg[key] = {}
            suffix = key.replace("fpga_", "")
            default_pll_key = f"default_fpga_{suffix}_pll"
            if (
                "sys_clk_select" not in cfg[key]
                and default_pll_key in self.platform_config
            ):
                cfg[key]["sys_clk_select"] = self.platform_config[default_pll_key]
            if "out_clk_select" not in cfg[key]:
                cfg[key]["out_clk_select"] = self.FPGA_DEFAULT_OUT_CLK
        return cfg

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
