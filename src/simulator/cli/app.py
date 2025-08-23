from __future__ import annotations
import json
import sys
from pathlib import Path
from simulator.io.yaml_loader import load_object_types


def _kb_path(path: str | None) -> str:
    return path or str(Path.cwd() / "kb" / "objects")


def validate(path: str | None = None) -> None:
    """Validate all YAML object type files."""
    kb = _kb_path(path)
    try:
        reg = load_object_types(kb)
        types = list(reg.all())
        print(f"✅ Successfully loaded {len(types)} object type(s) from {kb}")
        for t in types:
            print(f"  - {t.name}@v{t.version} ({len(t.attributes)} attrs)")
    except Exception as e:
        print(f"❌ Validation failed: {e}")
        sys.exit(1)


def show_object(what: str, name: str, version: int, path: str | None = None) -> None:
    """Show an object type."""
    if what != "object":
        print("Only 'object' is supported in Phase 1")
        sys.exit(2)

    reg = load_object_types(_kb_path(path))
    obj = reg.get(name, version)

    print(f"\n{obj.name}@v{obj.version}")
    print("-" * 50)
    print(f"{'Attribute':<15} {'Space':<25} {'Mutable':<10} {'Default':<10}")
    print("-" * 50)
    for attr_name, attr in obj.attributes.items():
        space_str = ", ".join(attr.space.levels)
        print(f"{attr_name:<15} {space_str:<25} {str(attr.mutable):<10} {str(attr.default):<10}")

    # Also print default state as JSON
    print("\nDefault state:")
    # Create a simple state representation without using ObjectState
    default_values = {}
    for attr_name, attr in obj.attributes.items():
        if attr.default is None:
            # If no default, choose first in space
            default_values[attr_name] = attr.space.levels[0]
        else:
            default_values[attr_name] = attr.default
    print(json.dumps(default_values, indent=2))


def main():
    """Simple CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python -m simulator.cli.app <command> [args...]")
        print("Commands:")
        print("  validate [--path PATH]  - Validate all YAML object type files")
        print("  show object <name> --version <ver> [--path PATH] - Show object type details")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "validate":
        # Simple argument parsing for validate
        path = None
        if "--path" in sys.argv:
            idx = sys.argv.index("--path")
            if idx + 1 < len(sys.argv):
                path = sys.argv[idx + 1]
        validate(path)
        
    elif command == "show":
        # Simple argument parsing for show
        if len(sys.argv) < 4:
            print("Usage: show object <name> --version <ver> [--path PATH]")
            sys.exit(1)
        
        what = sys.argv[2]
        name = sys.argv[3]
        version = None
        path = None
        
        if "--version" in sys.argv:
            idx = sys.argv.index("--version")
            if idx + 1 < len(sys.argv):
                version = int(sys.argv[idx + 1])
        
        if "--path" in sys.argv:
            idx = sys.argv.index("--path")
            if idx + 1 < len(sys.argv):
                path = sys.argv[idx + 2]
        
        if version is None:
            print("Error: --version is required")
            sys.exit(1)
            
        show_object(what, name, version, path)
        
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()