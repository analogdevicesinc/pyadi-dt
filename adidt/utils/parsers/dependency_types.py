"""
Device Tree Dependency Type Definitions

This module defines the different types of dependencies that can exist
between device tree files and nodes.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, Any


class DependencyType(Enum):
    """Enumeration of different dependency relationship types."""

    FILE_INCLUDE = "file_include"  # #include statements in DTS files
    PHANDLE_REF = "phandle_ref"    # Runtime node references via phandles
    COMPATIBLE = "compatible"       # Device driver dependencies
    OVERLAY_BASE = "overlay_base"   # Base tree requirements for overlays
    TEMPLATE_VAR = "template_var"   # Jinja2 template variable dependencies


@dataclass
class Dependency:
    """
    Represents a single dependency relationship.

    Attributes:
        target: The target file or node that is depended upon
        type: The type of dependency relationship
        source_file: The file containing the dependency
        line_number: Line number where dependency appears (if applicable)
        resolved: Whether the dependency has been resolved
        optional: Whether this is an optional dependency
        metadata: Additional dependency-specific metadata
    """
    target: str
    type: DependencyType
    source_file: str
    line_number: Optional[int] = None
    resolved: bool = False
    optional: bool = False
    metadata: Optional[dict] = None

    def __str__(self) -> str:
        """String representation of the dependency."""
        status = "✓" if self.resolved else "✗"
        opt = " (optional)" if self.optional else ""
        line = f":{self.line_number}" if self.line_number else ""
        return f"[{status}] {self.type.value}: {self.target}{opt} ({self.source_file}{line})"

    def to_dict(self) -> dict:
        """Convert dependency to dictionary format."""
        return {
            "target": self.target,
            "type": self.type.value,
            "source_file": self.source_file,
            "line_number": self.line_number,
            "resolved": self.resolved,
            "optional": self.optional,
            "metadata": self.metadata or {}
        }


@dataclass
class MissingDependency:
    """
    Represents a dependency that could not be resolved.

    Attributes:
        file: The missing file or resource
        referenced_by: The file that references the missing dependency
        line: Line number where the reference appears
        include_type: Type of include (system/local)
        searched_paths: List of paths that were searched
    """
    file: str
    referenced_by: str
    line: Optional[int] = None
    include_type: str = "unknown"
    searched_paths: Optional[list] = None

    def __str__(self) -> str:
        """String representation of the missing dependency."""
        line_info = f" at line {self.line}" if self.line else ""
        return f"Missing: {self.file} (referenced by {self.referenced_by}{line_info})"

    def to_dict(self) -> dict:
        """Convert missing dependency to dictionary format."""
        return {
            "file": self.file,
            "referenced_by": self.referenced_by,
            "line": self.line,
            "include_type": self.include_type,
            "searched_paths": self.searched_paths or []
        }


class DependencyFormat(Enum):
    """Output format options for dependency visualization."""

    TREE = "tree"      # ASCII tree format
    JSON = "json"      # JSON format
    DOT = "dot"        # GraphViz DOT format
    FLAT = "flat"      # Flat list format