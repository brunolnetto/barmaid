import pytest
from unittest.mock import patch, mock_open, MagicMock
import sys
from pathlib import Path
from io import StringIO
from barmaid.cli import (
    parse_migration_file,
    sanitize_node_id,
    generate_mermaid_diagram,
    main,
    __version__
)

# --- Test Data ---

MIGRATION_CONTENT_SIMPLE = """
\"\"\"create user table\"\"\"
revision = '1a2b3c'
down_revision = '4d5e6f'
branch_labels = None
depends_on = None
"""

MIGRATION_CONTENT_MERGE = """
\"\"\"merge heads\"\"\"
revision = '9h8g7f'
down_revision = ('1a2b3c', 'xyz123')
branch_labels = None
"""

MIGRATION_CONTENT_BRANCH = """
\"\"\"add features\"\"\"
revision = 'feature1'
down_revision = '1a2b3c'
branch_labels = ('new_feature',)
"""

MIGRATION_CONTENT_NO_REV = """
\"\"\"empty migration\"\"\"
# revision will be parsed from filename
down_revision = None
"""

# --- Unit Tests ---

def test_sanitize_node_id():
    assert sanitize_node_id("123-456") == "123_456"
    assert sanitize_node_id("1.2.3") == "1_2_3"
    assert sanitize_node_id("abc") == "abc"

def test_parse_migration_file_simple():
    with patch("builtins.open", mock_open(read_data=MIGRATION_CONTENT_SIMPLE)):
        path = Path("versions/1a2b3c_create_user.py")
        result = parse_migration_file(path)
        assert result['revision'] == '1a2b3c'
        assert result['down_revisions'] == ['4d5e6f']
        assert result['branch_labels'] == []
        assert result['message'] == 'create user table'
        assert result['filename'] == "1a2b3c_create_user.py"

def test_parse_migration_file_merge():
    with patch("builtins.open", mock_open(read_data=MIGRATION_CONTENT_MERGE)):
        path = Path("versions/merge.py")
        result = parse_migration_file(path)
        assert result['revision'] == '9h8g7f'
        assert set(result['down_revisions']) == {'1a2b3c', 'xyz123'}

def test_parse_migration_file_branch_labels():
    with patch("builtins.open", mock_open(read_data=MIGRATION_CONTENT_BRANCH)):
        path = Path("versions/feature.py")
        result = parse_migration_file(path)
        assert result['branch_labels'] == ['new_feature']

def test_parse_migration_file_filename_fallback():
    with patch("builtins.open", mock_open(read_data=MIGRATION_CONTENT_NO_REV)):
        path = Path("versions/1234567890ab_migration.py")
        result = parse_migration_file(path)
        assert result['revision'] == '1234567890ab'

def test_generate_mermaid_diagram():
    migrations = [
        {
            'revision': 'rev2',
            'down_revisions': ['rev1'],
            'branch_labels': [],
            'message': 'second',
            'filename': '2.py'
        },
        {
            'revision': 'rev1',
            'down_revisions': [], # root
            'branch_labels': ['root_branch'],
            'message': 'first',
            'filename': '1.py'
        }
    ]
    diagram = generate_mermaid_diagram(migrations, direction="LR", show_orphans=False)
    assert "graph LR" in diagram
    assert 'rev2["rev2<br/>second"]' in diagram
    assert 'rev1["rev1<br/>first<br/>[root_branch]"]' in diagram
    assert "rev1 --> rev2" in diagram

def test_generate_mermaid_diagram_with_orphans():
    migrations = [
        {
            'revision': 'rev1',
            'down_revisions': ['missing_parent'],
            'branch_labels': [],
            'message': 'orphan child',
            'filename': '1.py'
        }
    ]
    diagram = generate_mermaid_diagram(migrations, show_orphans=True)
    assert 'missing_parent["missing_parent<br/>(missing)"]' in diagram
    assert 'style missing_parent' in diagram
    assert 'missing_parent --> rev1' in diagram

    # Test without orphans
    diagram_no_orphans = generate_mermaid_diagram(migrations, show_orphans=False)
    assert 'missing_parent' not in diagram_no_orphans

def test_generate_mermaid_diagram_hash_truncation():
    migrations = [{
        'revision': '0123456789abcdef', # 16 chars hex
        'down_revisions': [],
        'branch_labels': [],
        'message': '',
        'filename': 'hash.py'
    }]
    diagram = generate_mermaid_diagram(migrations)
    # Should truncate to 8 chars AND include the styling block
    node_str = '0123456789abcdef["01234567"]' 
    assert node_str in diagram

def test_generate_mermaid_diagram_long_name_truncation():
    long_name = "z" * 40 # Use 'z' so it's not treated as hex
    migrations = [{
        'revision': long_name,
        'down_revisions': [],
        'branch_labels': [],
        'message': '',
        'filename': 'long.py'
    }]
    diagram = generate_mermaid_diagram(migrations)
    expected_label = long_name[:30] + "..."
    # The revisions is the full name, the label is truncated
    node_str = f'{long_name}["{expected_label}"]'
    assert node_str in diagram

# --- Integration Tests (Main) ---

@pytest.fixture
def mock_versions_dir():
    with patch("pathlib.Path.is_dir", return_value=True), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.glob") as mock_glob:
        
        # Setup mock files
        file1 = MagicMock()
        file1.name = "rev1.py"
        file1.__lt__.return_value = True # Allow sorting
        
        file2 = MagicMock()
        file2.name = "__init__.py" # Should be skipped
        file2.__lt__.return_value = False # Allow sorting
        
        # We need to make sure sorted() works on these mocks.
        # sorted() compares items.
        
        mock_glob.return_value = [file1, file2]
        yield mock_glob

@patch("barmaid.cli.parse_migration_file")
@patch("sys.stdout", new_callable=StringIO)
def test_main_defaults(mock_stdout, mock_parse, mock_versions_dir):
    # Mock return of parse
    mock_parse.return_value = {
        'revision': 'rev1',
        'down_revisions': [],
        'branch_labels': [],
        'message': 'msg',
        'filename': 'rev1.py'
    }
    
    with patch("sys.argv", ["barmaid"]):
        # Mock default path search to find something
        with patch("pathlib.Path.exists", side_effect=[True, False, False]): 
             with patch("pathlib.Path.is_dir", return_value=True):
                main()
    
    output = mock_stdout.getvalue()
    assert "graph TD" in output
    assert 'rev1["rev1<br/>msg"]' in output

@patch("barmaid.cli.parse_migration_file")
def test_main_custom_path(mock_parse):
    mock_parse.return_value = {'revision': '1', 'down_revisions': [], 'branch_labels': [], 'message': '', 'filename': '1.py'}
    
    with patch("sys.argv", ["barmaid", "custom/path", "--debug"]), \
         patch("pathlib.Path.is_dir", return_value=True), \
         patch("pathlib.Path.glob", return_value=[MagicMock(name="1.py")]), \
         patch("sys.stderr", new_callable=StringIO) as mock_stderr:
        
        main()
        
        assert "Scanning directory" in mock_stderr.getvalue()
        assert "✓" in mock_stderr.getvalue()

@patch("barmaid.cli.parse_migration_file")
def test_main_output_file(mock_parse):
    mock_parse.return_value = {'revision': '1', 'down_revisions': [], 'branch_labels': [], 'message': '', 'filename': '1.py'}
    
    with patch("sys.argv", ["barmaid", "path", "-o", "out.mmd"]), \
         patch("pathlib.Path.is_dir", return_value=True), \
         patch("pathlib.Path.glob", return_value=[MagicMock(name="1.py")]), \
         patch("builtins.open", mock_open()) as mock_file_write, \
         patch("sys.stderr", new_callable=StringIO) as mock_stderr:
        
        main()
        
        mock_file_write.assert_called_with("out.mmd", "w")
        assert "Diagram saved to out.mmd" in mock_stderr.getvalue()

def test_main_no_dir_found():
    with patch("sys.argv", ["barmaid"]), \
         patch("pathlib.Path.exists", return_value=False), \
         patch("sys.stderr", new_callable=StringIO) as mock_stderr:
        
        with pytest.raises(SystemExit) as e:
            main()
        assert e.value.code == 1
        assert "Error: Could not find versions directory" in mock_stderr.getvalue()

def test_main_invalid_dir():
    with patch("sys.argv", ["barmaid", "invalid_path"]), \
         patch("pathlib.Path.is_dir", return_value=False), \
         patch("sys.stderr", new_callable=StringIO) as mock_stderr:
        
        with pytest.raises(SystemExit) as e:
            main()
        assert e.value.code == 1
        assert "is not a directory" in mock_stderr.getvalue()

def test_main_no_migrations_found():
    with patch("sys.argv", ["barmaid", "path"]), \
         patch("pathlib.Path.is_dir", return_value=True), \
         patch("pathlib.Path.glob", return_value=[]), \
         patch("sys.stderr", new_callable=StringIO) as mock_stderr:
        
        with pytest.raises(SystemExit) as e:
            main()
        assert e.value.code == 1
        assert "No migrations found!" in mock_stderr.getvalue()

@patch("barmaid.cli.parse_migration_file")
def test_main_parsing_errors(mock_parse):
    # Mock parse raising error then success
    mock_parse.side_effect = Exception("Parse Error")
    
    file_mock = MagicMock()
    file_mock.name = "bad_file.py"
    
    with patch("sys.argv", ["barmaid", "path"]), \
         patch("pathlib.Path.is_dir", return_value=True), \
         patch("pathlib.Path.glob", return_value=[file_mock]), \
         patch("sys.stderr", new_callable=StringIO) as mock_stderr:
        
        with pytest.raises(SystemExit): # Will exit because no valid migrations found
            main()
        
        assert "Warning: Could not parse bad_file.py" in mock_stderr.getvalue()

@patch("barmaid.cli.parse_migration_file")
def test_main_skipped_files(mock_parse):
    # First file is valid, second has no revision
    mock_parse.side_effect = [
        {'revision': 'rev1', 'down_revisions': [], 'branch_labels': [], 'message': 'msg', 'filename': 'rev1.py'},
        {'revision': None, 'down_revisions': [], 'branch_labels': [], 'message': '', 'filename': 'skipped.py'}
    ]
    
    file1 = MagicMock()
    file1.name = "rev1.py"
    file1.__lt__.return_value = True
    
    file2 = MagicMock()
    file2.name = "skipped.py"
    file2.__lt__.return_value = False

    with patch("sys.argv", ["barmaid", "path", "--debug"]), \
         patch("pathlib.Path.is_dir", return_value=True), \
         patch("pathlib.Path.glob", return_value=[file1, file2]), \
         patch("sys.stderr", new_callable=StringIO) as mock_stderr:
        
        main()
        
        # Check that we hit the skipped block
        output = mock_stderr.getvalue()
        assert "✗ skipped.py: No revision found" in output
        assert "# Skipped 1 files" in output
        assert "#   - skipped.py" in output

@patch("barmaid.cli.parse_migration_file")
def test_main_missing_parent_revisions(mock_parse):
    # Migration references phantom parent
    mock_parse.return_value = {
        'revision': 'rev1', 
        'down_revisions': ['phantom_parent'], 
        'branch_labels': [], 
        'message': 'msg', 
        'filename': 'rev1.py'
    }
    
    file1 = MagicMock()
    file1.name = "rev1.py"

    with patch("sys.argv", ["barmaid", "path"]), \
         patch("pathlib.Path.is_dir", return_value=True), \
         patch("pathlib.Path.glob", return_value=[file1]), \
         patch("sys.stderr", new_callable=StringIO) as mock_stderr:
        
        main()
        
        output = mock_stderr.getvalue()
        # Should print warning (since 'missing' set is not empty)
        assert "# Warning: 1 missing parent revisions:" in output
        assert "#   - phantom_parent" in output

def test_main_version_flag():
    # This might catch SystemExit or print version
    with patch("sys.argv", ["barmaid", "--version"]), \
         patch("sys.stdout", new_callable=StringIO) as mock_stdout:
        
        with pytest.raises(SystemExit):
            main()
        assert __version__ in mock_stdout.getvalue()

def test_script_execution():
    """Test that the script runs when executed directly"""
    file_path = Path(__file__).parent.parent / "barmaid" / "cli.py"
    
    # We run the script largely unmocked, so we expect it to fail finding directories
    # and exit with status 1. This confirms the __main__ block executed main().
    with patch.object(sys, 'argv', ["barmaid"]):
        with pytest.raises(SystemExit) as e:
            import runpy
            runpy.run_path(str(file_path), run_name="__main__")
        assert e.value.code == 1
