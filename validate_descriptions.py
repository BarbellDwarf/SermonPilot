#!/usr/bin/env python3
"""
DEPRECATED: Description validation is now integrated into sermon_updater.py

This convenience script is deprecated. All validation functionality has been 
integrated into the main sermon_updater.py script. Please use:

For validation only:
    python sermon_updater.py --validate-descriptions --validation-report
    python sermon_updater.py --validate-descriptions --export-validation-csv results.csv

For validation with regeneration:
    python sermon_updater.py --validate-and-regenerate
    python sermon_updater.py --validate-and-regenerate --dry-run
    python sermon_updater.py --validate-and-regenerate --validation-sermon-ids 123,456,789

For help with all validation options:
    python sermon_updater.py --help
"""
import sys

def main():
    """Show deprecation message and provide alternatives."""
    print(__doc__)
    print("\n❌ This script is deprecated and no longer functional.")
    print("✅ Please use the integrated validation options in sermon_updater.py instead.")
    print("\nFor a quick migration guide:")
    print("  Old: python validate_descriptions.py --validate-all")
    print("  New: python sermon_updater.py --validate-descriptions")
    print()
    print("  Old: python validate_descriptions.py --validate-all --regenerate-failed")
    print("  New: python sermon_updater.py --validate-and-regenerate")
    print()
    print("  Old: python description_validator.py --local-sermons --detailed-report")
    print("  New: python sermon_updater.py --validate-descriptions --validation-report")
    return 1

if __name__ == "__main__":
    sys.exit(main())