#!/usr/bin/env python3
"""
Convenience script to run description validation from the project root.
"""
import subprocess
import sys
from pathlib import Path

def main():
    """Run the validation script from src folder."""
    # Get the path to the validation script
    script_path = Path(__file__).parent / "src" / "validate_descriptions.py"
    
    # Run the script with all passed arguments
    cmd = [sys.executable, str(script_path)] + sys.argv[1:]
    return subprocess.run(cmd).returncode

if __name__ == "__main__":
    sys.exit(main())