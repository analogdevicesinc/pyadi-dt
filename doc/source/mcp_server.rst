MCP Server
==========

pyadi-dt includes an `MCP <https://modelcontextprotocol.io/>`_ server
(``adidt-mcp``) that exposes device tree generation, linting, and
inspection tools to AI assistants like Claude and Cursor.

Installation
------------

Install with the ``mcp`` extra:

.. code-block:: bash

   pip install "adidt[mcp]"

This pulls in `FastMCP <https://github.com/jlowin/fastmcp>`_ as the
server framework.

Running the server
------------------

Start the server directly:

.. code-block:: bash

   adidt-mcp

Or configure it in your Claude Desktop / Cursor MCP settings:

.. code-block:: json

   {
     "mcpServers": {
       "pyadi-dt": {
         "command": "adidt-mcp"
       }
     }
   }

For Claude Code, add to ``.claude/settings.json``:

.. code-block:: json

   {
     "mcpServers": {
       "pyadi-dt": {
         "command": "adidt-mcp"
       }
     }
   }

Available tools
---------------

generate_devicetree
~~~~~~~~~~~~~~~~~~~

Generate a complete device tree from a Vivado XSA archive.  Runs the
full XSA pipeline: sdtgen, topology parse, node build, merge, and
optional visualization.

**Parameters:**

.. list-table::
   :widths: 25 15 60
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``xsa_path``
     - str (required)
     - Path to the Vivado ``.xsa`` archive.
   * - ``output_dir``
     - str (required)
     - Directory where output files are written.
   * - ``config_json``
     - str
     - JSON string with JESD, clock, and datapath configuration.
       Typically from ``pyadi-jif`` solver output.  Defaults to ``"{}"``.
   * - ``profile``
     - str
     - Built-in profile name (e.g. ``"ad9081_zcu102"``,
       ``"fmcdaq2_zc706"``).  Auto-detected when omitted.
   * - ``output_format``
     - str
     - ``"default"`` for overlay + merged DTS, or ``"petalinux"`` to
       additionally generate ``system-user.dtsi`` and
       ``device-tree.bbappend``.
   * - ``emit_report``
     - bool
     - Generate an HTML topology report.  Default ``True``.
   * - ``emit_clock_graphs``
     - bool
     - Generate DOT/D2 clock-tree diagrams.  Default ``True``.
   * - ``sdtgen_timeout``
     - int
     - Max seconds for sdtgen.  Default ``300``.
   * - ``lint``
     - bool
     - Run structural DTS linter.  Default ``False``.
   * - ``strict_lint``
     - bool
     - Fail on lint errors.  Default ``False``.
   * - ``reference_dts``
     - str
     - Path to a reference DTS for parity checking.
   * - ``strict_parity``
     - bool
     - Fail on missing roles/links/properties.  Default ``False``.

**Returns:** Dict with paths to generated artifacts:

- ``overlay`` — ``.dtso`` overlay file
- ``merged`` — merged ``.dts`` file
- ``dts_path`` — alias for ``merged``
- ``report`` — HTML topology report (when ``emit_report=True``)
- ``clock_dot``, ``clock_d2`` — clock-tree diagrams
- ``pl_dtsi_path`` — path to sdtgen-generated ``pl.dtsi``
- ``system_user_dtsi`` — PetaLinux dtsi (when ``output_format="petalinux"``)
- ``diagnostics`` — lint JSON (when ``lint=True``)

**Example:**

.. code-block:: json

   {
     "xsa_path": "/path/to/design.xsa",
     "output_dir": "/tmp/dt_output",
     "profile": "fmcdaq2_zc706",
     "config_json": "{\"jesd\": {\"rx\": {\"L\": 4, \"M\": 2}}}"
   }

list_xsa_profiles
~~~~~~~~~~~~~~~~~

List all available built-in XSA board profiles.

**Parameters:** None.

**Returns:** Sorted list of profile name strings.

**Example response:**

.. code-block:: json

   ["ad9081_zcu102", "ad9084_vcu118", "adrv9009_zc706", "fmcdaq2_zc706"]

show_xsa_profile
~~~~~~~~~~~~~~~~

Show the full configuration for a named profile.

**Parameters:**

- ``name`` (str, required) — Profile name from ``list_xsa_profiles``.

**Returns:** Profile dict with ``defaults`` key containing board
configuration, clock settings, and JESD parameters.

read_dt_property
~~~~~~~~~~~~~~~~

Read a device tree property from a DTS/DTB file or the running system.

**Parameters:**

.. list-table::
   :widths: 25 15 60
   :header-rows: 1

   * - Parameter
     - Type
     - Description
   * - ``node_name``
     - str (required)
     - Node name or compatible string to look up.
   * - ``property_name``
     - str
     - Specific property to read.  All properties returned when omitted.
   * - ``filepath``
     - str
     - Path to a ``.dts`` or ``.dtb`` file.  Reads from the running
       system (local sysfs) when omitted.

**Returns:** Dict with property values, or all properties when
``property_name`` is omitted.

lint_devicetree
~~~~~~~~~~~~~~~

Run the structural DTS linter on a generated DTS file.  Checks for
unresolved phandle references, clock-cell mismatches, duplicate SPI
chip selects, and missing compatible strings.

**Parameters:**

- ``dts_path`` (str, required) — Path to the ``.dts`` file to lint.

**Returns:** Dict with ``diagnostics`` list and ``summary`` counts by
severity (error, warning, info).

**Example response:**

.. code-block:: json

   {
     "diagnostics": [
       {
         "severity": "warning",
         "rule": "unresolved_phandle",
         "node": "/axi/spi@e0006000/ad9680@2",
         "message": "Reference to non-existent label 'gpio'"
       }
     ],
     "summary": {"errors": 0, "warnings": 1, "info": 0, "total": 1}
   }

Workflow examples
-----------------

Generate a device tree with Claude
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When the MCP server is configured, you can ask Claude:

   *"Generate a device tree for my AD9081 + ZCU102 design.  The XSA
   is at /home/user/vivado/design.xsa and the pyadi-jif config is
   in /home/user/cfg.json."*

Claude will call ``generate_devicetree`` with the appropriate
parameters and return the paths to the generated DTS, overlay, and
HTML report.

PetaLinux workflow
~~~~~~~~~~~~~~~~~~

   *"Generate a system-user.dtsi for my FMCDAQ3 ZC706 design for
   PetaLinux."*

Claude will call ``generate_devicetree`` with
``output_format="petalinux"`` and return the path to the generated
``system-user.dtsi`` ready for the PetaLinux project.

Inspect and lint
~~~~~~~~~~~~~~~~

   *"Lint the device tree I just generated at /tmp/dt_output/merged.dts."*

Claude will call ``lint_devicetree`` and report any structural issues.

API reference
-------------

.. automodule:: adidt.mcp_server
   :members:
   :undoc-members:
