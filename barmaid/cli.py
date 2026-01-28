import argparse
import os
import re
import sys
from pathlib import Path

__version__ = "0.1.0"


def parse_migration_file(filepath):
    """Extract revision info from an Alembic migration file."""
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Extract revision ID from file content (with or without type annotations)
    revision_match = re.search(r"revision\s*(?::\s*\w+\s*)?=\s*['\"]([^'\"]+)['\"]", content)
    revision = revision_match.group(1) if revision_match else None
    
    # If no revision found in file, try to extract from filename
    # Format: {revision}_{description}.py
    if not revision:
        filename_match = re.match(r"^([a-f0-9_]+)_.*\.py$", filepath.name)
        if filename_match:
            revision = filename_match.group(1)
    
    # Extract down_revision (can be None, a string, or tuple, with or without type annotations)
    down_rev_match = re.search(r"down_revision\s*(?::\s*[^=]+)?\s*=\s*(.+?)(?:\n|$)", content)
    down_revisions = []
    
    if down_rev_match:
        down_rev_str = down_rev_match.group(1).strip()
        if down_rev_str != "None":
            # Handle tuples for branch merges
            if down_rev_str.startswith('('):
                # Extract all quoted strings from tuple
                down_revisions = re.findall(r"['\"]([^'\"]+)['\"]", down_rev_str)
            else:
                # Single revision
                single_match = re.search(r"['\"]([^'\"]+)['\"]", down_rev_str)
                if single_match:
                    down_revisions = [single_match.group(1)]
    
    # Extract branch labels if present (with or without type annotations)
    branch_match = re.search(r"branch_labels\s*(?::\s*[^=]+)?\s*=\s*(.+?)(?:\n|$)", content)
    branch_labels = []
    if branch_match:
        branch_str = branch_match.group(1).strip()
        if branch_str != "None":
            branch_labels = re.findall(r"['\"]([^'\"]+)['\"]", branch_str)
    
    # Extract message/description
    message_match = re.search(r"\"\"\"(.+?)\"\"\"", content, re.DOTALL)
    message = message_match.group(1).strip() if message_match else ""
    message = message.split('\n')[0][:60]  # First line, max 60 chars
    
    return {
        'revision': revision,
        'down_revisions': down_revisions,
        'branch_labels': branch_labels,
        'message': message,
        'filename': filepath.name
    }


def sanitize_node_id(revision):
    """Sanitize revision ID for use as Mermaid node ID."""
    # Replace characters that might cause issues in Mermaid
    return revision.replace('-', '_').replace('.', '_')


def generate_mermaid_diagram(migrations, direction="TD", show_orphans=True):
    """Generate Mermaid flowchart from migration data."""
    lines = [f"graph {direction}"]
    
    # Build a set of all known revisions
    all_revisions = {mig['revision'] for mig in migrations}
    
    # Track which revisions are referenced
    referenced_revisions = set()
    for mig in migrations:
        referenced_revisions.update(mig['down_revisions'])
    
    # Find orphaned references (down_revisions that don't exist)
    orphaned_refs = referenced_revisions - all_revisions
    
    # Create nodes for actual migrations
    for mig in migrations:
        rev = mig['revision']
        node_id = sanitize_node_id(rev)
        
        # Create a readable label
        if len(rev) == 12 and all(c in '0123456789abcdef' for c in rev):
            # It's a hash-like revision
            label = rev[:8]
        else:
            # It's a descriptive revision - use it as-is but truncate if too long
            label = rev[:30] + "..." if len(rev) > 30 else rev
        
        if mig['message']:
            label += f"<br/>{mig['message']}"
        if mig['branch_labels']:
            label += f"<br/>[{', '.join(mig['branch_labels'])}]"
        
        lines.append(f'    {node_id}["{label}"]')
    
    # Create placeholder nodes for orphaned references if requested
    if show_orphans:
        for orphan in orphaned_refs:
            node_id = sanitize_node_id(orphan)
            label = f"{orphan[:30]}...<br/>(missing)" if len(orphan) > 30 else f"{orphan}<br/>(missing)"
            lines.append(f'    {node_id}["{label}"]')
            lines.append(f'    style {node_id} fill:#ffcccc,stroke:#cc0000,stroke-width:2px,stroke-dasharray: 5 5')
    
    # Create edges
    for mig in migrations:
        rev = mig['revision']
        rev_id = sanitize_node_id(rev)
        for down_rev in mig['down_revisions']:
            # Only create edge if the down_revision exists or we're showing orphans
            if down_rev in all_revisions or (show_orphans and down_rev in orphaned_refs):
                down_id = sanitize_node_id(down_rev)
                lines.append(f"    {down_id} --> {rev_id}")
    
    # Add styling
    lines.append("")
    lines.append("    classDef default fill:#f9f9f9,stroke:#333,stroke-width:2px")
    
    return '\n'.join(lines)

def main():
    parser = argparse.ArgumentParser(
        description="Convert Alembic migration history to a Mermaid diagram.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "-v", "--version", 
        action="version", 
        version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "path", 
        nargs="?", 
        help="Path to the alembic 'versions' directory. If not provided, common locations will be searched."
    )
    parser.add_argument(
        "-o", "--output", 
        help="Save the diagram to a file instead of printing to stdout."
    )
    parser.add_argument(
        "-d", "--direction", 
        choices=["TD", "LR", "BT", "RL"], 
        default="TD", 
        help="The direction of the flowchart (TD = Top-Down, LR = Left-to-Right)."
    )
    parser.add_argument(
        "--no-orphans", 
        action="store_false", 
        dest="show_orphans",
        help="Don't show missing parent revisions as nodes."
    )
    parser.add_argument(
        "--debug", 
        action="store_true", 
        help="Enable debug output to stderr."
    )

    args = parser.parse_args()

    # Get versions directory path
    if args.path:
        versions_dir = Path(args.path)
    else:
        # Try common locations
        search_paths = [
            Path('alembic/versions'),
            Path('versions'),
            Path('src/backend/alembic/versions'),
            Path('backend/alembic/versions'),
        ]
        versions_dir = None
        for p in search_paths:
            if p.exists() and p.is_dir():
                versions_dir = p
                break
        
        if not versions_dir:
            print("Error: Could not find versions directory in common locations.", file=sys.stderr)
            print("Please provide the path as an argument: barmaid [path/to/versions]", file=sys.stderr)
            sys.exit(1)
    
    if not versions_dir.is_dir():
        print(f"Error: {versions_dir} is not a directory", file=sys.stderr)
        sys.exit(1)
    
    if args.debug:
        print(f"Scanning directory: {versions_dir.absolute()}", file=sys.stderr)
    
    # Parse all migration files
    migrations = []
    skipped = []
    
    for filepath in sorted(versions_dir.glob('*.py')):
        if filepath.name == '__init__.py':
            continue
        try:
            mig = parse_migration_file(filepath)
            if mig['revision']:
                migrations.append(mig)
                if args.debug:
                    print(f"✓ {filepath.name}: {mig['revision']}", file=sys.stderr)
            else:
                skipped.append(filepath.name)
                if args.debug:
                    print(f"✗ {filepath.name}: No revision found", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Could not parse {filepath.name}: {e}", file=sys.stderr)
            skipped.append(filepath.name)
    
    if not migrations:
        print("No migrations found!", file=sys.stderr)
        sys.exit(1)
    
    # Generate Mermaid diagram
    diagram = generate_mermaid_diagram(
        migrations, 
        direction=args.direction, 
        show_orphans=args.show_orphans
    )
    
    # Output result
    if args.output:
        with open(args.output, 'w') as f:
            f.write(diagram)
        print(f"Diagram saved to {args.output}", file=sys.stderr)
    else:
        print(diagram)
    
    # Print summary to stderr
    all_revisions = {mig['revision'] for mig in migrations}
    referenced = set()
    for mig in migrations:
        referenced.update(mig['down_revisions'])
    missing = referenced - all_revisions
    
    if args.debug or missing or not args.output:
        print(f"\n# Found {len(migrations)} migrations", file=sys.stderr)
        if skipped:
            print(f"# Skipped {len(skipped)} files (no revision found):", file=sys.stderr)
            for s in skipped[:5]:
                print(f"#   - {s}", file=sys.stderr)
        if missing:
            print(f"# Warning: {len(missing)} missing parent revisions:", file=sys.stderr)
            for m in sorted(missing):
                print(f"#   - {m}", file=sys.stderr)


if __name__ == "__main__":
    main()
