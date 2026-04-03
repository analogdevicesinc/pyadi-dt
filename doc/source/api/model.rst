Board Model Module
==================

The ``adidt.model`` package provides the unified ``BoardModel`` abstraction
that both the manual board-class workflow and the XSA pipeline produce.
A single ``BoardModelRenderer`` renders any ``BoardModel`` to DTS using
per-component Jinja2 templates.

.. automodule:: adidt.model
   :members:
   :undoc-members:
   :show-inheritance:

Board Model
-----------

.. automodule:: adidt.model.board_model
   :members:
   :undoc-members:
   :show-inheritance:

Renderer
--------

.. automodule:: adidt.model.renderer
   :members:
   :undoc-members:
   :show-inheritance:

Context Builders
----------------

Shared functions that produce template context dicts.  Each function
corresponds to a Jinja2 template in ``adidt/templates/xsa/`` and returns
a flat dict whose keys match the template variables.

.. automodule:: adidt.model.contexts
   :members:
   :undoc-members:
   :show-inheritance:
