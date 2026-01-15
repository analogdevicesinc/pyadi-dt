"""
Tests for DTS parser module
"""

import pytest
import os
from adidt.utils.parsers.parsers.dts_parser import DTSParser, IncludeStatement
from adidt.utils.parsers.dependency_types import Dependency, DependencyType


class TestIncludeStatement:
    """Test IncludeStatement class"""

    def test_create_include_statement(self):
        """Test creating an include statement"""
        inc = IncludeStatement("test.dtsi", 10, "local")
        assert inc.file == "test.dtsi"
        assert inc.line_number == 10
        assert inc.include_type == "local"

    def test_include_statement_repr(self):
        """Test include statement representation"""
        inc = IncludeStatement("common.dtsi", 5, "system")
        repr_str = repr(inc)
        assert "common.dtsi" in repr_str
        assert "line=5" in repr_str
        assert "system" in repr_str


class TestDTSParser:
    """Test DTSParser class"""

    @pytest.fixture
    def parser(self):
        """Create a parser instance"""
        return DTSParser()

    @pytest.fixture
    def fixtures_dir(self):
        """Get fixtures directory path"""
        return os.path.join(os.path.dirname(__file__), 'fixtures')

    def test_parse_system_include(self, parser):
        """Test parsing system include statements"""
        content = '#include <dt-bindings/clock/xlnx-zynqmp-clk.h>'
        includes = parser.parse_content(content)

        assert len(includes) == 1
        assert includes[0].file == 'dt-bindings/clock/xlnx-zynqmp-clk.h'
        assert includes[0].include_type == 'system'
        assert includes[0].line_number == 1

    def test_parse_local_include(self, parser):
        """Test parsing local include statements"""
        content = '#include "board-config.dtsi"'
        includes = parser.parse_content(content)

        assert len(includes) == 1
        assert includes[0].file == 'board-config.dtsi'
        assert includes[0].include_type == 'local'

    def test_parse_legacy_include(self, parser):
        """Test parsing legacy /include/ format"""
        content = '/include/ "legacy-file.dtsi"'
        includes = parser.parse_content(content)

        assert len(includes) == 1
        assert includes[0].file == 'legacy-file.dtsi'
        assert includes[0].include_type == 'legacy'

    def test_parse_multiple_includes(self, parser):
        """Test parsing multiple include statements"""
        content = '''
#include <dt-bindings/gpio/gpio.h>
#include "common.dtsi"
/include/ "legacy.dtsi"
#include <dt-bindings/clock/clock.h>
'''
        includes = parser.parse_content(content)

        assert len(includes) == 4
        assert includes[0].include_type == 'system'
        assert includes[1].include_type == 'local'
        assert includes[2].include_type == 'legacy'
        assert includes[3].include_type == 'system'

    def test_parse_with_whitespace(self, parser):
        """Test parsing includes with various whitespace"""
        content = '''
    #include   <dt-bindings/test.h>
		#include  "test.dtsi"
  /include/   "test2.dtsi"
'''
        includes = parser.parse_content(content)

        assert len(includes) == 3

    def test_parse_skip_comments(self, parser):
        """Test that commented includes are skipped"""
        content = '''
// #include "commented-out.dtsi"
/* #include "block-commented.dtsi" */
#include "real-include.dtsi"
'''
        includes = parser.parse_content(content)

        assert len(includes) == 1
        assert includes[0].file == 'real-include.dtsi'

    def test_parse_line_numbers(self, parser):
        """Test that line numbers are correctly tracked"""
        content = '''/dts-v1/;

#include <line3.h>
// Comment
#include "line5.dtsi"

#include "line7.dtsi"
'''
        includes = parser.parse_content(content)

        assert includes[0].line_number == 3
        assert includes[1].line_number == 5
        assert includes[2].line_number == 7

    def test_parse_file_simple(self, parser, fixtures_dir):
        """Test parsing a simple DTS file"""
        file_path = os.path.join(fixtures_dir, 'simple.dts')
        includes = parser.parse_file(file_path)

        # simple.dts has no includes
        assert len(includes) == 0

    def test_parse_file_with_includes(self, parser, fixtures_dir):
        """Test parsing a file with various includes"""
        file_path = os.path.join(fixtures_dir, 'with_includes.dts')
        includes = parser.parse_file(file_path)

        # Should find multiple includes
        assert len(includes) > 0

        # Check for specific includes
        include_files = [inc.file for inc in includes]
        assert 'dt-bindings/clock/xlnx-zynqmp-clk.h' in include_files
        assert 'includes/common.dtsi' in include_files

    def test_parse_file_not_found(self, parser):
        """Test parsing non-existent file raises error"""
        with pytest.raises(FileNotFoundError):
            parser.parse_file('/nonexistent/file.dts')

    def test_parse_nested_includes(self, parser, fixtures_dir):
        """Test parsing file with nested includes"""
        file_path = os.path.join(fixtures_dir, 'nested_includes.dts')
        includes = parser.parse_file(file_path)

        assert len(includes) >= 2

    def test_extract_includes_as_dependencies(self, parser, fixtures_dir):
        """Test extracting includes as Dependency objects"""
        file_path = os.path.join(fixtures_dir, 'with_includes.dts')
        deps = parser.extract_includes_as_dependencies(file_path, 'with_includes.dts')

        assert len(deps) > 0
        assert all(isinstance(dep, Dependency) for dep in deps)
        assert all(dep.type == DependencyType.FILE_INCLUDE for dep in deps)
        assert all(dep.source_file == 'with_includes.dts' for dep in deps)

    def test_dependency_has_line_numbers(self, parser, fixtures_dir):
        """Test that dependencies include line numbers"""
        file_path = os.path.join(fixtures_dir, 'with_includes.dts')
        deps = parser.extract_includes_as_dependencies(file_path, 'with_includes.dts')

        # Check that at least some have line numbers
        assert any(dep.line_number is not None for dep in deps)

    def test_dependency_has_metadata(self, parser, fixtures_dir):
        """Test that dependencies include metadata"""
        file_path = os.path.join(fixtures_dir, 'with_includes.dts')
        deps = parser.extract_includes_as_dependencies(file_path, 'with_includes.dts')

        # Check metadata exists
        assert all(dep.metadata is not None for dep in deps)
        assert all('include_type' in dep.metadata for dep in deps)

    def test_is_system_include(self, parser):
        """Test system include detection"""
        assert parser.is_system_include('dt-bindings/clock/test.h') is True
        assert parser.is_system_include('linux/kernel.h') is True
        assert parser.is_system_include('asm/types.h') is True
        assert parser.is_system_include('board-config.dtsi') is False
        assert parser.is_system_include('common.dtsi') is False

    def test_normalize_path(self, parser):
        """Test path normalization"""
        # Test whitespace removal
        assert parser.normalize_path('  test.dtsi  ') == 'test.dtsi'

        # Test backslash to forward slash
        assert parser.normalize_path('path\\to\\file.dtsi') == 'path/to/file.dtsi'

        # Test double slash removal
        assert parser.normalize_path('path//to//file.dtsi') == 'path/to/file.dtsi'

        # Test combined
        assert parser.normalize_path(' path\\\\to//file.dtsi ') == 'path/to/file.dtsi'

    def test_parse_empty_file(self, parser):
        """Test parsing empty content"""
        content = ''
        includes = parser.parse_content(content)
        assert len(includes) == 0

    def test_parse_no_includes(self, parser):
        """Test parsing file with no includes"""
        content = '''
/dts-v1/;

/ {
    compatible = "test,board";
    model = "Test Board";
};
'''
        includes = parser.parse_content(content)
        assert len(includes) == 0

    def test_parse_includes_in_nodes(self, parser):
        """Test parsing includes that appear within node definitions"""
        content = '''
/ {
    #include "includes/memory.dtsi"

    soc {
        #include "includes/peripherals.dtsi"
    };
};
'''
        includes = parser.parse_content(content)
        assert len(includes) == 2
        assert 'includes/memory.dtsi' in [inc.file for inc in includes]
        assert 'includes/peripherals.dtsi' in [inc.file for inc in includes]

    def test_parse_mixed_quote_styles(self, parser):
        """Test parsing includes with different quote styles"""
        content = '''
#include <system/header.h>
#include "local/file.dtsi"
/include/ "legacy-style.dtsi"
'''
        includes = parser.parse_content(content)

        assert len(includes) == 3
        types = [inc.include_type for inc in includes]
        assert 'system' in types
        assert 'local' in types
        assert 'legacy' in types

    def test_circular_dependencies_files_exist(self, fixtures_dir):
        """Test that circular dependency test files exist"""
        circular_a = os.path.join(fixtures_dir, 'circular_a.dts')
        circular_b = os.path.join(fixtures_dir, 'circular_b.dts')

        assert os.path.exists(circular_a)
        assert os.path.exists(circular_b)

    def test_parse_with_missing_deps_file(self, parser, fixtures_dir):
        """Test parsing file that references missing dependencies"""
        file_path = os.path.join(fixtures_dir, 'with_missing.dts')
        includes = parser.parse_file(file_path)

        # Should still parse and return includes, even for missing files
        assert len(includes) > 0

        # Check for the missing includes
        include_files = [inc.file for inc in includes]
        assert 'missing_file.dtsi' in include_files
        assert 'dt-bindings/missing/nonexistent.h' in include_files
