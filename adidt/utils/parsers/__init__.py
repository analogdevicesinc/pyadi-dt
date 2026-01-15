"""
Device Tree Dependency Parser

This module provides tools for analyzing and visualizing dependencies
in device tree files, including file includes, phandle references,
and template variables.

Examples:
    Basic usage::

        from adidt.utils.parsers import DTDependencyParser

        parser = DTDependencyParser()
        parser.parse('/path/to/system.dts')

        # Check for circular dependencies
        cycles = parser.detect_circular_dependencies()

        # Get build order
        order = parser.get_resolution_order()

        # Visualize tree
        print(parser.render_tree())

    Export to JSON::

        data = parser.export_json()
        with open('deps.json', 'w') as f:
            json.dump(data, f, indent=2)
"""

from .dt_dependency_parser import DTDependencyParser
from .dependency_types import (
    DependencyType,
    Dependency,
    MissingDependency,
    DependencyFormat
)
from .dependency_tree import DependencyTree, DependencyNode

__all__ = [
    'DTDependencyParser',
    'DependencyType',
    'Dependency',
    'MissingDependency',
    'DependencyFormat',
    'DependencyTree',
    'DependencyNode',
]
