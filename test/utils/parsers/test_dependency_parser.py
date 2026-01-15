"""
Tests for main dependency parser
"""

import pytest
import os
import json
from adidt.utils.parsers import DTDependencyParser
from adidt.utils.parsers.dependency_types import DependencyType


class TestDTDependencyParser:
    """Test DTDependencyParser class"""

    @pytest.fixture
    def parser(self):
        """Create a parser instance"""
        return DTDependencyParser()

    @pytest.fixture
    def fixtures_dir(self):
        """Get fixtures directory path"""
        return os.path.join(os.path.dirname(__file__), 'fixtures')

    def test_create_parser(self, parser):
        """Test creating a parser instance"""
        assert parser is not None
        assert parser.tree is None
        assert len(parser.visited_files) == 0

    def test_parse_simple_file(self, parser, fixtures_dir):
        """Test parsing a simple file with no includes"""
        file_path = os.path.join(fixtures_dir, 'simple.dts')
        tree = parser.parse(file_path)

        assert tree is not None
        assert tree.root.name == 'simple.dts'
        assert len(tree.nodes) == 1

    def test_parse_file_not_found(self, parser):
        """Test parsing non-existent file raises error"""
        with pytest.raises(FileNotFoundError):
            parser.parse('/nonexistent/file.dts')

    def test_parse_with_includes(self, parser, fixtures_dir):
        """Test parsing file with includes"""
        file_path = os.path.join(fixtures_dir, 'with_includes.dts')
        tree = parser.parse(file_path)

        assert tree is not None
        # Should have root plus included files
        assert len(tree.nodes) > 1

    def test_parse_nested_includes(self, parser, fixtures_dir):
        """Test parsing file with nested includes"""
        file_path = os.path.join(fixtures_dir, 'nested_includes.dts')
        tree = parser.parse(file_path)

        assert tree is not None
        # Should recursively parse nested includes
        assert len(tree.nodes) >= 3

    def test_resolve_include_path_found(self, parser, fixtures_dir):
        """Test resolving an include path that exists"""
        file_path = os.path.join(fixtures_dir, 'with_includes.dts')
        parser.parse(file_path)

        # Try to resolve a path that should exist
        base_dir = fixtures_dir
        resolved = parser.resolve_include_path('includes/common.dtsi', base_dir)

        assert resolved is not None
        assert os.path.exists(resolved)

    def test_resolve_include_path_not_found(self, parser, fixtures_dir):
        """Test resolving an include path that doesn't exist"""
        base_dir = fixtures_dir
        resolved = parser.resolve_include_path('nonexistent.dtsi', base_dir)

        assert resolved is None

    def test_missing_dependencies_tracked(self, parser, fixtures_dir):
        """Test that missing dependencies are properly tracked"""
        file_path = os.path.join(fixtures_dir, 'with_missing.dts')
        tree = parser.parse(file_path)

        missing = parser.get_missing_dependencies()
        assert len(missing) > 0

        # Check that specific missing files are tracked
        missing_files = [m.file for m in missing]
        assert 'missing_file.dtsi' in missing_files

    def test_missing_dependency_details(self, parser, fixtures_dir):
        """Test that missing dependency details are captured"""
        file_path = os.path.join(fixtures_dir, 'with_missing.dts')
        parser.parse(file_path)

        missing = parser.get_missing_dependencies()
        assert len(missing) > 0

        # Check details
        for m in missing:
            assert m.file is not None
            assert m.referenced_by is not None
            assert m.searched_paths is not None
            assert len(m.searched_paths) > 0

    def test_detect_circular_dependencies(self, parser, fixtures_dir):
        """Test detection of circular dependencies"""
        file_path = os.path.join(fixtures_dir, 'circular_a.dts')
        parser.parse(file_path)

        cycles = parser.detect_circular_dependencies()
        # circular_a includes circular_b which includes circular_a
        assert len(cycles) > 0

    def test_get_resolution_order(self, parser, fixtures_dir):
        """Test getting resolution order"""
        file_path = os.path.join(fixtures_dir, 'nested_includes.dts')
        parser.parse(file_path)

        order = parser.get_resolution_order()
        assert len(order) > 0

        # Dependencies should come before dependents
        # nested_includes.dts should be last (or near last)
        assert 'nested_includes.dts' in order

    def test_render_tree_basic(self, parser, fixtures_dir):
        """Test rendering tree as ASCII"""
        file_path = os.path.join(fixtures_dir, 'simple.dts')
        parser.parse(file_path)

        tree_str = parser.render_tree()
        assert tree_str is not None
        assert 'simple.dts' in tree_str
        assert 'Legend' in tree_str

    def test_render_tree_with_includes(self, parser, fixtures_dir):
        """Test rendering tree with includes"""
        file_path = os.path.join(fixtures_dir, 'with_includes.dts')
        parser.parse(file_path)

        tree_str = parser.render_tree()
        assert tree_str is not None
        assert 'with_includes.dts' in tree_str
        # Should show some included files
        assert '├──' in tree_str or '└──' in tree_str

    def test_render_tree_with_missing(self, parser, fixtures_dir):
        """Test rendering tree shows missing dependencies"""
        file_path = os.path.join(fixtures_dir, 'with_missing.dts')
        parser.parse(file_path)

        tree_str = parser.render_tree(show_missing=True)
        assert tree_str is not None
        assert 'Missing Dependencies' in tree_str

    def test_render_tree_hide_missing(self, parser, fixtures_dir):
        """Test rendering tree can hide missing dependencies"""
        file_path = os.path.join(fixtures_dir, 'with_missing.dts')
        parser.parse(file_path)

        tree_str = parser.render_tree(show_missing=False)
        assert tree_str is not None
        # Should not have missing section
        assert 'Missing Dependencies' not in tree_str or parser.tree.missing_dependencies == []

    def test_render_tree_max_depth(self, parser, fixtures_dir):
        """Test rendering tree with max depth limit"""
        file_path = os.path.join(fixtures_dir, 'nested_includes.dts')
        parser.parse(file_path)

        tree_str = parser.render_tree(max_depth=1)
        assert tree_str is not None

    def test_export_dot_basic(self, parser, fixtures_dir):
        """Test exporting to GraphViz DOT format"""
        file_path = os.path.join(fixtures_dir, 'simple.dts')
        parser.parse(file_path)

        dot = parser.export_dot()
        assert dot is not None
        assert 'digraph dt_dependencies' in dot
        assert 'simple.dts' in dot

    def test_export_dot_with_edges(self, parser, fixtures_dir):
        """Test DOT export includes edges"""
        file_path = os.path.join(fixtures_dir, 'with_includes.dts')
        parser.parse(file_path)

        dot = parser.export_dot()
        assert dot is not None
        # Should have edges (arrows)
        assert '->' in dot

    def test_export_dot_with_missing(self, parser, fixtures_dir):
        """Test DOT export shows missing dependencies"""
        file_path = os.path.join(fixtures_dir, 'with_missing.dts')
        parser.parse(file_path)

        dot = parser.export_dot(show_missing=True)
        assert dot is not None
        # Should have dashed edges for missing
        assert 'style=dashed' in dot or len(parser.get_missing_dependencies()) == 0

    def test_export_dot_hide_missing(self, parser, fixtures_dir):
        """Test DOT export can hide missing dependencies"""
        file_path = os.path.join(fixtures_dir, 'with_missing.dts')
        parser.parse(file_path)

        dot = parser.export_dot(show_missing=False)
        assert dot is not None

    def test_export_json_basic(self, parser, fixtures_dir):
        """Test exporting to JSON format"""
        file_path = os.path.join(fixtures_dir, 'simple.dts')
        parser.parse(file_path)

        json_data = parser.export_json()
        assert json_data is not None
        assert 'root' in json_data
        assert 'nodes' in json_data
        assert 'resolution_order' in json_data
        assert 'missing_dependencies' in json_data
        assert 'cycles' in json_data
        assert 'statistics' in json_data

    def test_export_json_structure(self, parser, fixtures_dir):
        """Test JSON export has correct structure"""
        file_path = os.path.join(fixtures_dir, 'with_includes.dts')
        parser.parse(file_path)

        json_data = parser.export_json()

        # Check root
        assert json_data['root'] == 'with_includes.dts'

        # Check nodes structure
        assert 'with_includes.dts' in json_data['nodes']
        node_data = json_data['nodes']['with_includes.dts']
        assert 'type' in node_data
        assert 'path' in node_data
        assert 'dependencies' in node_data

        # Check statistics
        stats = json_data['statistics']
        assert 'total_nodes' in stats
        assert 'missing_dependencies' in stats
        assert 'max_depth' in stats

    def test_export_json_serializable(self, parser, fixtures_dir):
        """Test that JSON export is actually serializable"""
        file_path = os.path.join(fixtures_dir, 'simple.dts')
        parser.parse(file_path)

        json_data = parser.export_json()

        # Should be able to serialize without error
        json_str = json.dumps(json_data)
        assert json_str is not None

        # Should be able to deserialize
        parsed = json.loads(json_str)
        assert parsed == json_data

    def test_parse_multiple_times(self, parser, fixtures_dir):
        """Test parsing multiple files with same parser"""
        file1 = os.path.join(fixtures_dir, 'simple.dts')
        file2 = os.path.join(fixtures_dir, 'with_includes.dts')

        tree1 = parser.parse(file1)
        assert tree1.root.name == 'simple.dts'

        tree2 = parser.parse(file2)
        assert tree2.root.name == 'with_includes.dts'

        # Should have new tree
        assert parser.tree.root.name == 'with_includes.dts'

    def test_visited_files_tracking(self, parser, fixtures_dir):
        """Test that visited files are tracked"""
        file_path = os.path.join(fixtures_dir, 'with_includes.dts')
        parser.parse(file_path)

        # Should have visited files
        assert len(parser.visited_files) > 0

    def test_statistics_accuracy(self, parser, fixtures_dir):
        """Test that statistics are accurate"""
        file_path = os.path.join(fixtures_dir, 'with_includes.dts')
        tree = parser.parse(file_path)

        stats = tree.get_statistics()

        # Verify counts make sense
        assert stats['total_nodes'] >= 1
        assert stats['total_dependencies'] >= 0
        assert stats['max_depth'] >= 0

    def test_custom_search_paths(self, fixtures_dir):
        """Test parser with custom search paths"""
        custom_paths = [fixtures_dir]
        parser = DTDependencyParser(search_paths=custom_paths)

        assert fixtures_dir in parser.search_paths

    def test_no_tree_before_parse(self, parser):
        """Test that operations before parse handle no tree gracefully"""
        # Should return empty results before parsing
        assert parser.detect_circular_dependencies() == []
        assert parser.get_resolution_order() == []
        assert parser.get_missing_dependencies() == []

    def test_render_tree_no_parse(self, parser):
        """Test rendering tree before parsing"""
        tree_str = parser.render_tree()
        assert 'No dependency tree parsed yet' in tree_str

    def test_export_dot_no_parse(self, parser):
        """Test DOT export before parsing"""
        dot = parser.export_dot()
        assert dot == ''

    def test_export_json_no_parse(self, parser):
        """Test JSON export before parsing"""
        json_data = parser.export_json()
        assert json_data == {}
