"""
Device Tree Dependency Tree Structure

This module implements the tree data structure for managing and traversing
device tree dependencies.
"""

from typing import List, Optional, Set, Dict, Tuple
from .dependency_types import Dependency, MissingDependency, DependencyType


class DependencyNode:
    """
    Represents a node in the dependency tree.

    Attributes:
        name: The name/path of the file or resource
        path: Full filesystem path (if resolved)
        dependencies: List of dependencies from this node
        depth: Depth in the tree (0 for root)
        parent: Parent node reference
        children: List of child nodes
    """

    def __init__(self, name: str, path: Optional[str] = None, depth: int = 0):
        self.name = name
        self.path = path or name
        self.depth = depth
        self.dependencies: List[Dependency] = []
        self.parent: Optional['DependencyNode'] = None
        self.children: List['DependencyNode'] = []

    def add_dependency(self, dep: Dependency) -> None:
        """Add a dependency to this node."""
        self.dependencies.append(dep)

    def add_child(self, child: 'DependencyNode') -> None:
        """Add a child node."""
        child.parent = self
        child.depth = self.depth + 1
        self.children.append(child)

    def get_all_dependencies(self, dep_type: Optional[DependencyType] = None) -> List[Dependency]:
        """
        Get all dependencies, optionally filtered by type.

        Args:
            dep_type: Optional dependency type to filter by

        Returns:
            List of dependencies
        """
        if dep_type:
            return [d for d in self.dependencies if d.type == dep_type]
        return self.dependencies.copy()

    def __str__(self) -> str:
        return f"Node({self.name}, depth={self.depth}, deps={len(self.dependencies)})"

    def __repr__(self) -> str:
        return self.__str__()


class DependencyTree:
    """
    Manages a tree of dependencies with cycle detection and traversal.
    """

    def __init__(self, root_name: str, root_path: Optional[str] = None):
        """
        Initialize dependency tree.

        Args:
            root_name: Name of the root node
            root_path: Full path to root file
        """
        self.root = DependencyNode(root_name, root_path, depth=0)
        self.nodes: Dict[str, DependencyNode] = {root_name: self.root}
        self.missing_dependencies: List[MissingDependency] = []

    def add_node(self, name: str, path: Optional[str] = None, parent_name: Optional[str] = None) -> DependencyNode:
        """
        Add a node to the tree.

        Args:
            name: Node name/identifier
            path: Full path to file
            parent_name: Name of parent node

        Returns:
            The created or existing node
        """
        if name in self.nodes:
            return self.nodes[name]

        node = DependencyNode(name, path)

        if parent_name and parent_name in self.nodes:
            parent = self.nodes[parent_name]
            parent.add_child(node)

        self.nodes[name] = node
        return node

    def add_missing_dependency(self, missing: MissingDependency) -> None:
        """Track a missing dependency."""
        self.missing_dependencies.append(missing)

    def get_node(self, name: str) -> Optional[DependencyNode]:
        """Get a node by name."""
        return self.nodes.get(name)

    def detect_cycles(self) -> List[List[str]]:
        """
        Detect circular dependencies using DFS with three-color algorithm.

        Returns:
            List of cycles, where each cycle is a list of node names
        """
        # Three colors: white (unvisited), gray (in progress), black (complete)
        WHITE, GRAY, BLACK = 0, 1, 2
        colors = {name: WHITE for name in self.nodes}
        cycles = []
        path_stack = []

        def dfs(node_name: str) -> None:
            if colors[node_name] == BLACK:
                return

            if colors[node_name] == GRAY:
                # Found a cycle - extract it from the path stack
                cycle_start = path_stack.index(node_name)
                cycle = path_stack[cycle_start:] + [node_name]
                cycles.append(cycle)
                return

            colors[node_name] = GRAY
            path_stack.append(node_name)

            node = self.nodes[node_name]
            for dep in node.dependencies:
                if dep.resolved and dep.target in self.nodes:
                    dfs(dep.target)

            path_stack.pop()
            colors[node_name] = BLACK

        # Start DFS from root
        dfs(self.root.name)

        return cycles

    def get_resolution_order(self) -> List[str]:
        """
        Get the optimal resolution/build order using topological sort.

        Returns:
            List of node names in dependency order (dependencies first)
        """
        # Build adjacency list
        in_degree = {name: 0 for name in self.nodes}
        adjacency = {name: [] for name in self.nodes}

        for name, node in self.nodes.items():
            for dep in node.dependencies:
                if dep.resolved and dep.target in self.nodes:
                    adjacency[dep.target].append(name)
                    in_degree[name] += 1

        # Kahn's algorithm for topological sort
        queue = [name for name, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            current = queue.pop(0)
            result.append(current)

            for neighbor in adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # If result doesn't contain all nodes, there's a cycle
        if len(result) != len(self.nodes):
            # Return partial order with remaining nodes appended
            remaining = [n for n in self.nodes if n not in result]
            result.extend(remaining)

        return result

    def get_max_depth(self) -> int:
        """Get the maximum depth of the tree."""
        return max((node.depth for node in self.nodes.values()), default=0)

    def get_statistics(self) -> Dict[str, int]:
        """
        Get tree statistics.

        Returns:
            Dictionary with statistics
        """
        total_deps = sum(len(node.dependencies) for node in self.nodes.values())
        resolved_deps = sum(
            len([d for d in node.dependencies if d.resolved])
            for node in self.nodes.values()
        )

        return {
            "total_nodes": len(self.nodes),
            "total_dependencies": total_deps,
            "resolved_dependencies": resolved_deps,
            "missing_dependencies": len(self.missing_dependencies),
            "max_depth": self.get_max_depth(),
        }

    def traverse_dfs(self) -> List[DependencyNode]:
        """
        Traverse tree in depth-first order.

        Returns:
            List of nodes in DFS order
        """
        result = []
        visited = set()

        def dfs(node: DependencyNode):
            if node.name in visited:
                return
            visited.add(node.name)
            result.append(node)
            for child in node.children:
                dfs(child)

        dfs(self.root)
        return result

    def traverse_bfs(self) -> List[DependencyNode]:
        """
        Traverse tree in breadth-first order.

        Returns:
            List of nodes in BFS order
        """
        result = []
        queue = [self.root]
        visited = {self.root.name}

        while queue:
            node = queue.pop(0)
            result.append(node)
            for child in node.children:
                if child.name not in visited:
                    visited.add(child.name)
                    queue.append(child)

        return result
