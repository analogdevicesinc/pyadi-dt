"""
Device Tree Dependency Parser

Main parser orchestrating dependency analysis for device tree files.
"""

import os
from pathlib import Path
from typing import List, Optional, Dict, Set
from .dependency_types import (
    Dependency,
    MissingDependency,
    DependencyType,
)
from .dependency_tree import DependencyTree, DependencyNode
from .parsers.dts_parser import DTSParser


class DTDependencyParser:
    """
    Main device tree dependency parser.

    This class orchestrates parsing of DTS/DTSI files, builds dependency trees,
    tracks missing dependencies, detects circular dependencies, and provides
    multiple output formats.

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

    def __init__(self, search_paths: Optional[List[str]] = None):
        """
        Initialize dependency parser.

        Args:
            search_paths: Additional search paths for resolving includes
        """
        self.tree: Optional[DependencyTree] = None
        self.dts_parser = DTSParser()
        self.visited_files: Set[str] = set()
        self.search_paths = search_paths or []
        self.project_root = self._find_project_root()

        # Build default search paths
        self.default_search_paths = [
            os.path.join(self.project_root, "adidt", "templates"),
            "/usr/include",
            "/usr/src/linux/include",
        ]

    def _find_project_root(self) -> str:
        """Find the project root directory."""
        current = Path.cwd()
        # Look for pyproject.toml or setup.py
        while current != current.parent:
            if (current / "pyproject.toml").exists() or (current / "setup.py").exists():
                return str(current)
            current = current.parent
        return str(Path.cwd())

    def parse(self, file_path: str) -> DependencyTree:
        """
        Parse a device tree file and build the dependency tree.

        Args:
            file_path: Path to the DTS/DTSI file to parse

        Returns:
            DependencyTree object with all dependencies

        Raises:
            FileNotFoundError: If the file doesn't exist
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Device tree file not found: {file_path}")

        abs_path = os.path.abspath(file_path)
        file_name = os.path.basename(file_path)

        # Initialize tree with root
        self.tree = DependencyTree(file_name, abs_path)
        self.visited_files.clear()

        # Start recursive parsing
        self._parse_recursive(abs_path, file_name, None)

        return self.tree

    def _parse_recursive(
        self, file_path: str, node_name: str, parent_name: Optional[str]
    ) -> None:
        """
        Recursively parse a file and its includes.

        Args:
            file_path: Full path to the file
            node_name: Name of the node in the tree
            parent_name: Name of the parent node
        """
        # Avoid infinite loops
        if file_path in self.visited_files:
            return

        self.visited_files.add(file_path)

        # Add node to tree
        if parent_name:
            self.tree.add_node(node_name, file_path, parent_name)

        # Get the node
        node = self.tree.get_node(node_name)
        if not node:
            return

        # Parse the file for includes
        try:
            includes = self.dts_parser.parse_file(file_path)
        except (FileNotFoundError, IOError):
            # File can't be read, but we already added it
            return

        # Process each include
        base_dir = os.path.dirname(file_path)

        for inc in includes:
            # Create dependency
            dep = Dependency(
                target=inc.file,
                type=DependencyType.FILE_INCLUDE,
                source_file=node_name,
                line_number=inc.line_number,
                metadata={"include_type": inc.include_type},
            )

            # Try to resolve the include path
            resolved_path = self.resolve_include_path(inc.file, base_dir)

            if resolved_path:
                dep.resolved = True
                node.add_dependency(dep)

                # Recursively parse the included file
                included_name = inc.file
                self._parse_recursive(resolved_path, included_name, node_name)
            else:
                # Track as missing dependency
                dep.resolved = False
                node.add_dependency(dep)

                missing = MissingDependency(
                    file=inc.file,
                    referenced_by=node_name,
                    line=inc.line_number,
                    include_type=inc.include_type,
                    searched_paths=self._get_search_paths(base_dir),
                )
                self.tree.add_missing_dependency(missing)

    def resolve_include_path(self, include_file: str, base_path: str) -> Optional[str]:
        """
        Resolve an include path with comprehensive search and missing tracking.

        Args:
            include_file: The include file path from the include statement
            base_path: The base directory to search from

        Returns:
            Full resolved path or None if not found
        """
        # Normalize the include path
        include_file = self.dts_parser.normalize_path(include_file)

        # Build search paths list
        search_paths = self._get_search_paths(base_path)

        # Search each path
        for search_dir in search_paths:
            full_path = os.path.join(search_dir, include_file)
            if os.path.exists(full_path):
                return os.path.abspath(full_path)

        return None

    def _get_search_paths(self, base_path: str) -> List[str]:
        """
        Get the ordered list of search paths.

        Args:
            base_path: The base directory

        Returns:
            List of search paths in priority order
        """
        paths = [
            base_path,  # Current directory
            os.path.dirname(base_path),  # Parent directory
        ]

        # Add user-configured paths
        paths.extend(self.search_paths)

        # Add default paths
        paths.extend(self.default_search_paths)

        return paths

    def detect_circular_dependencies(self) -> List[List[str]]:
        """
        Detect circular dependencies in the parsed tree.

        Returns:
            List of cycles, where each cycle is a list of node names
        """
        if not self.tree:
            return []

        return self.tree.detect_cycles()

    def get_resolution_order(self) -> List[str]:
        """
        Get the optimal resolution/build order.

        Returns:
            List of node names in dependency order (dependencies first)
        """
        if not self.tree:
            return []

        return self.tree.get_resolution_order()

    def get_missing_dependencies(self) -> List[MissingDependency]:
        """
        Get list of missing dependencies.

        Returns:
            List of MissingDependency objects
        """
        if not self.tree:
            return []

        return self.tree.missing_dependencies

    def render_tree(
        self, max_depth: Optional[int] = None, show_missing: bool = True
    ) -> str:
        """
        Generate ASCII tree visualization.

        Args:
            max_depth: Maximum depth to display (None for unlimited)
            show_missing: Whether to show missing dependencies section

        Returns:
            ASCII art tree representation
        """
        if not self.tree:
            return "No dependency tree parsed yet."

        lines = []
        lines.append(self.tree.root.name)

        # Render tree structure
        self._render_node(self.tree.root, "", True, lines, max_depth, 0)

        # Add legend
        lines.append("")
        lines.append("Legend: [I]=Include, [P]=Phandle, [C]=Compatible, [O]=Optional")

        # Add missing dependencies section
        if show_missing and self.tree.missing_dependencies:
            lines.append("")
            lines.append("Missing Dependencies:")
            for missing in self.tree.missing_dependencies:
                ref = (
                    f"{missing.referenced_by}:{missing.line}"
                    if missing.line
                    else missing.referenced_by
                )
                lines.append(f"- {missing.file} (referenced at {ref})")

        # Add statistics
        stats = self.tree.get_statistics()
        lines.append("")
        lines.append(
            f"Statistics: {stats['total_nodes']} nodes, "
            f"{stats['resolved_dependencies']} resolved, "
            f"{stats['missing_dependencies']} missing, "
            f"max depth: {stats['max_depth']}"
        )

        return "\n".join(lines)

    def _render_node(
        self,
        node: DependencyNode,
        prefix: str,
        is_last: bool,
        lines: List[str],
        max_depth: Optional[int],
        current_depth: int,
    ) -> None:
        """Recursively render a node and its children."""
        if max_depth is not None and current_depth >= max_depth:
            return

        for i, child in enumerate(node.children):
            is_last_child = i == len(node.children) - 1

            # Determine line characters
            if is_last_child:
                line_char = "└── "
                new_prefix = prefix + "    "
            else:
                line_char = "├── "
                new_prefix = prefix + "│   "

            # Get dependency info for this child
            dep_info = ""
            for dep in node.dependencies:
                if dep.target == child.name:
                    status = "✓" if dep.resolved else "✗"
                    dep_info = f" [{status} I]"
                    break

            lines.append(f"{prefix}{line_char}{child.name}{dep_info}")

            # Recursively render children
            self._render_node(
                child, new_prefix, is_last_child, lines, max_depth, current_depth + 1
            )

    def export_dot(self, show_missing: bool = True) -> str:
        """
        Generate GraphViz DOT format output.

        Args:
            show_missing: Whether to include missing dependencies

        Returns:
            DOT format string
        """
        if not self.tree:
            return ""

        dot_lines = [
            "digraph dt_dependencies {",
            "    rankdir=TB;",
            "    node [shape=box];",
            "",
        ]

        # Style root node
        dot_lines.append(
            f'    "{self.tree.root.name}" [style=filled, fillcolor=lightblue];'
        )
        dot_lines.append("")

        # Add edges for resolved dependencies
        for node_name, node in self.tree.nodes.items():
            for dep in node.dependencies:
                if dep.resolved:
                    label = dep.type.value
                    dot_lines.append(
                        f'    "{node_name}" -> "{dep.target}" [label="{label}"];'
                    )

        # Add missing dependencies with dashed red edges
        if show_missing and self.tree.missing_dependencies:
            dot_lines.append("")
            dot_lines.append("    // Missing dependencies")
            for missing in self.tree.missing_dependencies:
                dot_lines.append(
                    f'    "{missing.referenced_by}" -> "{missing.file}" '
                    f'[style=dashed, color=red, label="missing"];'
                )
                dot_lines.append(
                    f'    "{missing.file}" [shape=ellipse, style=filled, fillcolor=pink];'
                )

        dot_lines.append("}")
        return "\n".join(dot_lines)

    def export_json(self) -> Dict:
        """
        Export dependency tree as JSON structure.

        Returns:
            Dictionary suitable for JSON serialization
        """
        if not self.tree:
            return {}

        nodes_data = {}
        for name, node in self.tree.nodes.items():
            nodes_data[name] = {
                "type": "file",
                "path": node.path,
                "depth": node.depth,
                "dependencies": [dep.to_dict() for dep in node.dependencies],
            }

        cycles = self.detect_circular_dependencies()

        return {
            "root": self.tree.root.name,
            "nodes": nodes_data,
            "resolution_order": self.get_resolution_order(),
            "missing_dependencies": [
                m.to_dict() for m in self.tree.missing_dependencies
            ],
            "cycles": cycles,
            "statistics": self.tree.get_statistics(),
        }
