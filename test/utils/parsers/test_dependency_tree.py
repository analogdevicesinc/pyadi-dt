"""
Tests for dependency_tree module
"""

import pytest
from adidt.utils.parsers.dependency_tree import DependencyNode, DependencyTree
from adidt.utils.parsers.dependency_types import (
    Dependency,
    MissingDependency,
    DependencyType
)


class TestDependencyNode:
    """Test DependencyNode class"""

    def test_create_node(self):
        """Test creating a dependency node"""
        node = DependencyNode("test.dts", "/path/to/test.dts", depth=0)
        assert node.name == "test.dts"
        assert node.path == "/path/to/test.dts"
        assert node.depth == 0
        assert len(node.dependencies) == 0
        assert len(node.children) == 0
        assert node.parent is None

    def test_create_node_default_path(self):
        """Test creating node with default path"""
        node = DependencyNode("test.dts")
        assert node.path == "test.dts"

    def test_add_dependency(self):
        """Test adding a dependency to a node"""
        node = DependencyNode("test.dts")
        dep = Dependency(
            target="common.dtsi",
            type=DependencyType.FILE_INCLUDE,
            source_file="test.dts"
        )
        node.add_dependency(dep)
        assert len(node.dependencies) == 1
        assert node.dependencies[0].target == "common.dtsi"

    def test_add_child(self):
        """Test adding a child node"""
        parent = DependencyNode("parent.dts", depth=0)
        child = DependencyNode("child.dtsi")

        parent.add_child(child)

        assert len(parent.children) == 1
        assert child.parent == parent
        assert child.depth == 1

    def test_add_multiple_children(self):
        """Test adding multiple children"""
        parent = DependencyNode("parent.dts", depth=0)
        child1 = DependencyNode("child1.dtsi")
        child2 = DependencyNode("child2.dtsi")

        parent.add_child(child1)
        parent.add_child(child2)

        assert len(parent.children) == 2
        assert child1.depth == 1
        assert child2.depth == 1

    def test_get_all_dependencies(self):
        """Test getting all dependencies"""
        node = DependencyNode("test.dts")
        dep1 = Dependency(
            target="file1.dtsi",
            type=DependencyType.FILE_INCLUDE,
            source_file="test.dts"
        )
        dep2 = Dependency(
            target="file2.dtsi",
            type=DependencyType.FILE_INCLUDE,
            source_file="test.dts"
        )
        node.add_dependency(dep1)
        node.add_dependency(dep2)

        deps = node.get_all_dependencies()
        assert len(deps) == 2

    def test_get_dependencies_by_type(self):
        """Test filtering dependencies by type"""
        node = DependencyNode("test.dts")
        dep1 = Dependency(
            target="file.dtsi",
            type=DependencyType.FILE_INCLUDE,
            source_file="test.dts"
        )
        dep2 = Dependency(
            target="node",
            type=DependencyType.PHANDLE_REF,
            source_file="test.dts"
        )
        node.add_dependency(dep1)
        node.add_dependency(dep2)

        includes = node.get_all_dependencies(DependencyType.FILE_INCLUDE)
        assert len(includes) == 1
        assert includes[0].type == DependencyType.FILE_INCLUDE

    def test_node_string_representation(self):
        """Test node string representation"""
        node = DependencyNode("test.dts", depth=2)
        str_repr = str(node)
        assert "test.dts" in str_repr
        assert "depth=2" in str_repr


class TestDependencyTree:
    """Test DependencyTree class"""

    def test_create_tree(self):
        """Test creating a dependency tree"""
        tree = DependencyTree("root.dts", "/path/to/root.dts")
        assert tree.root.name == "root.dts"
        assert tree.root.path == "/path/to/root.dts"
        assert tree.root.depth == 0
        assert len(tree.nodes) == 1
        assert "root.dts" in tree.nodes

    def test_add_node(self):
        """Test adding a node to the tree"""
        tree = DependencyTree("root.dts")
        node = tree.add_node("child.dtsi", "/path/child.dtsi", "root.dts")

        assert len(tree.nodes) == 2
        assert "child.dtsi" in tree.nodes
        assert node.parent == tree.root
        assert len(tree.root.children) == 1

    def test_add_node_without_parent(self):
        """Test adding orphan node"""
        tree = DependencyTree("root.dts")
        node = tree.add_node("orphan.dtsi")

        assert len(tree.nodes) == 2
        assert node.parent is None

    def test_add_duplicate_node(self):
        """Test adding duplicate node returns existing"""
        tree = DependencyTree("root.dts")
        node1 = tree.add_node("child.dtsi", "/path/child.dtsi", "root.dts")
        node2 = tree.add_node("child.dtsi", "/another/path.dtsi", "root.dts")

        assert node1 is node2
        assert len(tree.nodes) == 2

    def test_get_node(self):
        """Test getting a node by name"""
        tree = DependencyTree("root.dts")
        tree.add_node("child.dtsi", "/path/child.dtsi", "root.dts")

        node = tree.get_node("child.dtsi")
        assert node is not None
        assert node.name == "child.dtsi"

    def test_get_nonexistent_node(self):
        """Test getting a non-existent node"""
        tree = DependencyTree("root.dts")
        node = tree.get_node("nonexistent.dtsi")
        assert node is None

    def test_add_missing_dependency(self):
        """Test tracking missing dependencies"""
        tree = DependencyTree("root.dts")
        missing = MissingDependency(
            file="missing.dtsi",
            referenced_by="root.dts",
            line=10
        )
        tree.add_missing_dependency(missing)

        assert len(tree.missing_dependencies) == 1
        assert tree.missing_dependencies[0].file == "missing.dtsi"

    def test_detect_cycles_no_cycle(self):
        """Test cycle detection with no cycles"""
        tree = DependencyTree("root.dts")
        child = tree.add_node("child.dtsi", parent_name="root.dts")

        # Add dependencies
        dep = Dependency(
            target="child.dtsi",
            type=DependencyType.FILE_INCLUDE,
            source_file="root.dts",
            resolved=True
        )
        tree.root.add_dependency(dep)

        cycles = tree.detect_cycles()
        assert len(cycles) == 0

    def test_detect_cycles_simple_cycle(self):
        """Test detecting a simple cycle"""
        tree = DependencyTree("a.dts")
        b_node = tree.add_node("b.dts", parent_name="a.dts")

        # Create cycle: a -> b -> a
        dep_ab = Dependency(
            target="b.dts",
            type=DependencyType.FILE_INCLUDE,
            source_file="a.dts",
            resolved=True
        )
        dep_ba = Dependency(
            target="a.dts",
            type=DependencyType.FILE_INCLUDE,
            source_file="b.dts",
            resolved=True
        )

        tree.root.add_dependency(dep_ab)
        b_node.add_dependency(dep_ba)

        cycles = tree.detect_cycles()
        assert len(cycles) > 0

    def test_get_resolution_order_simple(self):
        """Test getting resolution order"""
        tree = DependencyTree("main.dts")
        child = tree.add_node("common.dtsi", parent_name="main.dts")

        dep = Dependency(
            target="common.dtsi",
            type=DependencyType.FILE_INCLUDE,
            source_file="main.dts",
            resolved=True
        )
        tree.root.add_dependency(dep)

        order = tree.get_resolution_order()
        assert len(order) == 2
        # common.dtsi should come before main.dts (dependency first)
        assert order.index("common.dtsi") < order.index("main.dts")

    def test_get_resolution_order_complex(self):
        """Test resolution order with complex dependencies"""
        tree = DependencyTree("main.dts")
        common = tree.add_node("common.dtsi", parent_name="main.dts")
        board = tree.add_node("board.dtsi", parent_name="main.dts")
        clock = tree.add_node("clock.dtsi", parent_name="board.dtsi")

        # main depends on common and board
        # board depends on clock
        dep1 = Dependency("common.dtsi", DependencyType.FILE_INCLUDE, "main.dts", resolved=True)
        dep2 = Dependency("board.dtsi", DependencyType.FILE_INCLUDE, "main.dts", resolved=True)
        dep3 = Dependency("clock.dtsi", DependencyType.FILE_INCLUDE, "board.dtsi", resolved=True)

        tree.root.add_dependency(dep1)
        tree.root.add_dependency(dep2)
        board.add_dependency(dep3)

        order = tree.get_resolution_order()

        # clock should come before board, both should come before main
        assert order.index("clock.dtsi") < order.index("board.dtsi")
        assert order.index("board.dtsi") < order.index("main.dts")

    def test_get_max_depth(self):
        """Test getting maximum tree depth"""
        tree = DependencyTree("root.dts")
        level1 = tree.add_node("level1.dtsi", parent_name="root.dts")
        level2 = tree.add_node("level2.dtsi", parent_name="level1.dtsi")

        assert tree.get_max_depth() == 2

    def test_get_statistics(self):
        """Test getting tree statistics"""
        tree = DependencyTree("root.dts")
        child = tree.add_node("child.dtsi", parent_name="root.dts")

        dep = Dependency(
            target="child.dtsi",
            type=DependencyType.FILE_INCLUDE,
            source_file="root.dts",
            resolved=True
        )
        tree.root.add_dependency(dep)

        missing = MissingDependency(
            file="missing.dtsi",
            referenced_by="root.dts"
        )
        tree.add_missing_dependency(missing)

        stats = tree.get_statistics()
        assert stats["total_nodes"] == 2
        assert stats["total_dependencies"] == 1
        assert stats["resolved_dependencies"] == 1
        assert stats["missing_dependencies"] == 1
        assert stats["max_depth"] == 1

    def test_traverse_dfs(self):
        """Test depth-first traversal"""
        tree = DependencyTree("root.dts")
        child1 = tree.add_node("child1.dtsi", parent_name="root.dts")
        child2 = tree.add_node("child2.dtsi", parent_name="root.dts")
        grandchild = tree.add_node("grandchild.dtsi", parent_name="child1.dtsi")

        nodes = tree.traverse_dfs()
        assert len(nodes) == 4
        assert nodes[0] == tree.root

    def test_traverse_bfs(self):
        """Test breadth-first traversal"""
        tree = DependencyTree("root.dts")
        child1 = tree.add_node("child1.dtsi", parent_name="root.dts")
        child2 = tree.add_node("child2.dtsi", parent_name="root.dts")
        grandchild = tree.add_node("grandchild.dtsi", parent_name="child1.dtsi")

        nodes = tree.traverse_bfs()
        assert len(nodes) == 4
        assert nodes[0] == tree.root
        # Children should come before grandchildren in BFS
        child_indices = [i for i, n in enumerate(nodes) if n in [child1, child2]]
        grandchild_index = nodes.index(grandchild)
        assert all(idx < grandchild_index for idx in child_indices)
