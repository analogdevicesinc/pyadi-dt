"""
Tests for dependency_types module
"""

import pytest
from adidt.utils.parsers.dependency_types import (
    DependencyType,
    Dependency,
    MissingDependency,
    DependencyFormat
)


class TestDependencyType:
    """Test DependencyType enum"""

    def test_dependency_types_exist(self):
        """Test that all expected dependency types exist"""
        assert DependencyType.FILE_INCLUDE
        assert DependencyType.PHANDLE_REF
        assert DependencyType.COMPATIBLE
        assert DependencyType.OVERLAY_BASE
        assert DependencyType.TEMPLATE_VAR

    def test_dependency_type_values(self):
        """Test dependency type string values"""
        assert DependencyType.FILE_INCLUDE.value == "file_include"
        assert DependencyType.PHANDLE_REF.value == "phandle_ref"
        assert DependencyType.COMPATIBLE.value == "compatible"


class TestDependency:
    """Test Dependency dataclass"""

    def test_create_basic_dependency(self):
        """Test creating a basic dependency"""
        dep = Dependency(
            target="test.dtsi",
            type=DependencyType.FILE_INCLUDE,
            source_file="main.dts"
        )
        assert dep.target == "test.dtsi"
        assert dep.type == DependencyType.FILE_INCLUDE
        assert dep.source_file == "main.dts"
        assert dep.resolved is False
        assert dep.optional is False

    def test_create_dependency_with_line_number(self):
        """Test creating dependency with line number"""
        dep = Dependency(
            target="common.dtsi",
            type=DependencyType.FILE_INCLUDE,
            source_file="board.dts",
            line_number=42
        )
        assert dep.line_number == 42

    def test_dependency_with_metadata(self):
        """Test dependency with metadata"""
        dep = Dependency(
            target="clock.h",
            type=DependencyType.FILE_INCLUDE,
            source_file="main.dts",
            metadata={"include_type": "system"}
        )
        assert dep.metadata["include_type"] == "system"

    def test_dependency_string_representation(self):
        """Test dependency string representation"""
        dep = Dependency(
            target="test.dtsi",
            type=DependencyType.FILE_INCLUDE,
            source_file="main.dts",
            line_number=10,
            resolved=True
        )
        str_repr = str(dep)
        assert "test.dtsi" in str_repr
        assert "main.dts" in str_repr
        assert "✓" in str_repr  # Resolved indicator

    def test_dependency_string_unresolved(self):
        """Test unresolved dependency string representation"""
        dep = Dependency(
            target="missing.dtsi",
            type=DependencyType.FILE_INCLUDE,
            source_file="main.dts",
            resolved=False
        )
        str_repr = str(dep)
        assert "✗" in str_repr  # Unresolved indicator

    def test_dependency_optional_flag(self):
        """Test optional dependency string representation"""
        dep = Dependency(
            target="optional.dtsi",
            type=DependencyType.FILE_INCLUDE,
            source_file="main.dts",
            optional=True
        )
        str_repr = str(dep)
        assert "(optional)" in str_repr

    def test_dependency_to_dict(self):
        """Test converting dependency to dictionary"""
        dep = Dependency(
            target="test.dtsi",
            type=DependencyType.FILE_INCLUDE,
            source_file="main.dts",
            line_number=15,
            resolved=True,
            metadata={"foo": "bar"}
        )
        dep_dict = dep.to_dict()
        assert dep_dict["target"] == "test.dtsi"
        assert dep_dict["type"] == "file_include"
        assert dep_dict["source_file"] == "main.dts"
        assert dep_dict["line_number"] == 15
        assert dep_dict["resolved"] is True
        assert dep_dict["metadata"]["foo"] == "bar"


class TestMissingDependency:
    """Test MissingDependency dataclass"""

    def test_create_missing_dependency(self):
        """Test creating a missing dependency"""
        missing = MissingDependency(
            file="missing.dtsi",
            referenced_by="main.dts"
        )
        assert missing.file == "missing.dtsi"
        assert missing.referenced_by == "main.dts"

    def test_missing_dependency_with_line(self):
        """Test missing dependency with line number"""
        missing = MissingDependency(
            file="notfound.dtsi",
            referenced_by="board.dts",
            line=25
        )
        assert missing.line == 25

    def test_missing_dependency_with_type(self):
        """Test missing dependency with include type"""
        missing = MissingDependency(
            file="system.h",
            referenced_by="main.dts",
            include_type="system"
        )
        assert missing.include_type == "system"

    def test_missing_dependency_with_search_paths(self):
        """Test missing dependency with searched paths"""
        paths = ["/usr/include", "/usr/local/include"]
        missing = MissingDependency(
            file="missing.h",
            referenced_by="main.dts",
            searched_paths=paths
        )
        assert missing.searched_paths == paths

    def test_missing_dependency_string_representation(self):
        """Test missing dependency string representation"""
        missing = MissingDependency(
            file="missing.dtsi",
            referenced_by="main.dts",
            line=10
        )
        str_repr = str(missing)
        assert "missing.dtsi" in str_repr
        assert "main.dts" in str_repr
        assert "10" in str_repr

    def test_missing_dependency_to_dict(self):
        """Test converting missing dependency to dictionary"""
        missing = MissingDependency(
            file="missing.dtsi",
            referenced_by="main.dts",
            line=20,
            include_type="local",
            searched_paths=["/path1", "/path2"]
        )
        miss_dict = missing.to_dict()
        assert miss_dict["file"] == "missing.dtsi"
        assert miss_dict["referenced_by"] == "main.dts"
        assert miss_dict["line"] == 20
        assert miss_dict["include_type"] == "local"
        assert len(miss_dict["searched_paths"]) == 2


class TestDependencyFormat:
    """Test DependencyFormat enum"""

    def test_format_types_exist(self):
        """Test that all format types exist"""
        assert DependencyFormat.TREE
        assert DependencyFormat.JSON
        assert DependencyFormat.DOT
        assert DependencyFormat.FLAT

    def test_format_values(self):
        """Test format enum values"""
        assert DependencyFormat.TREE.value == "tree"
        assert DependencyFormat.JSON.value == "json"
        assert DependencyFormat.DOT.value == "dot"
        assert DependencyFormat.FLAT.value == "flat"
