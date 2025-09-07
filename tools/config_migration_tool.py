#!/usr/bin/env python3
"""
Configuration Migration Tool for Sermon Audio Processor

Command-line utility to migrate from YAML to SQL configuration and manage
SQL-based configuration system.
"""

import argparse
import sys
from pathlib import Path
import logging

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config_migration import ConfigMigrationManager
from config_management import SQLConfigManager


def setup_logging(debug: bool = False):
    """Set up logging configuration."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def migrate_yaml_to_sql(yaml_file: Path, db_path: Path, force: bool = False):
    """Migrate YAML configuration to SQL database."""
    if db_path.exists() and not force:
        print(f"❌ Database already exists: {db_path}")
        print("Use --force to overwrite existing database")
        return False
    
    if force and db_path.exists():
        print(f"🗑️ Removing existing database: {db_path}")
        db_path.unlink()
    
    print(f"📄 Migrating {yaml_file} to {db_path}...")
    
    try:
        with ConfigMigrationManager(str(db_path)) as manager:
            manager.create_schema()
            manager.migrate_yaml_to_sql(yaml_file)
            
            status = manager.get_migration_status()
            print(f"✅ Migration completed successfully!")
            print(f"   📊 Categories: {status['categories']}")
            print(f"   🔑 Keys: {status['keys']}")
            print(f"   💾 Values: {status['values']}")
            
        return True
    
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False


def export_config(db_path: Path, format: str, output_file: Path = None, template_name: str = None):
    """Export configuration from SQL database."""
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        return False
    
    try:
        with SQLConfigManager(str(db_path)) as config_manager:
            config_str = config_manager.export_config(format, template_name)
            
            if output_file:
                with open(output_file, 'w') as f:
                    f.write(config_str)
                print(f"✅ Configuration exported to {output_file}")
            else:
                print(f"📄 Configuration ({format.upper()}):")
                print("-" * 50)
                print(config_str)
            
        return True
    
    except Exception as e:
        print(f"❌ Export failed: {e}")
        return False


def import_config(db_path: Path, config_file: Path, format: str, overwrite: bool = False):
    """Import configuration to SQL database."""
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        return False
    
    if not config_file.exists():
        print(f"❌ Configuration file not found: {config_file}")
        return False
    
    try:
        with open(config_file, 'r') as f:
            config_data = f.read()
        
        with SQLConfigManager(str(db_path)) as config_manager:
            config_manager.import_config(config_data, format, "cli_import", overwrite)
            print(f"✅ Configuration imported from {config_file}")
            
        return True
    
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False


def show_status(db_path: Path):
    """Show configuration database status."""
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        return False
    
    try:
        with ConfigMigrationManager(str(db_path)) as manager:
            status = manager.get_migration_status()
        
        with SQLConfigManager(str(db_path)) as config_manager:
            keys = config_manager.get_configuration_keys()
            history = config_manager.get_configuration_history(limit=5)
        
        print(f"📊 Configuration Database Status")
        print("=" * 40)
        print(f"Database: {db_path}")
        print(f"Categories: {status['categories']}")
        print(f"Keys: {status['keys']}")
        print(f"Values: {status['values']}")
        print(f"Recent changes: {status['recent_changes']}")
        print()
        
        if keys:
            print("🔑 Configuration Keys by Category:")
            categories = {}
            for key in keys:
                cat = key['category_name']
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(key)
            
            for category, cat_keys in categories.items():
                print(f"  {category}:")
                for key in cat_keys[:5]:  # Show first 5 keys per category
                    secret_flag = " 🔒" if key['is_secret'] else ""
                    required_flag = " ⚠️" if key['is_required'] else ""
                    print(f"    - {key['key_path']}{secret_flag}{required_flag}")
                if len(cat_keys) > 5:
                    print(f"    ... and {len(cat_keys) - 5} more")
                print()
        
        if history:
            print("📈 Recent Changes:")
            for change in history:
                print(f"  {change['changed_at']} - {change['key_path']}")
                print(f"    Changed by: {change['changed_by']}")
                if change['change_reason']:
                    print(f"    Reason: {change['change_reason']}")
                print()
        
        return True
    
    except Exception as e:
        print(f"❌ Status check failed: {e}")
        return False


def main():
    """Main command-line interface."""
    parser = argparse.ArgumentParser(
        description="Configuration migration tool for Sermon Audio Processor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Migrate YAML to SQL
  python config_migration_tool.py migrate config.yaml --db sermon_config.db
  
  # Export configuration to YAML
  python config_migration_tool.py export --db sermon_config.db --format yaml --output exported_config.yaml
  
  # Import configuration from JSON
  python config_migration_tool.py import new_config.json --db sermon_config.db --format json --overwrite
  
  # Show database status
  python config_migration_tool.py status --db sermon_config.db
        """
    )
    
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--db', default='sermon_config.db', help='Database file path (default: sermon_config.db)')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Migrate command
    migrate_parser = subparsers.add_parser('migrate', help='Migrate YAML configuration to SQL')
    migrate_parser.add_argument('yaml_file', help='YAML configuration file to migrate')
    migrate_parser.add_argument('--force', action='store_true', help='Overwrite existing database')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export configuration from SQL database')
    export_parser.add_argument('--format', choices=['yaml', 'json', 'env'], default='yaml', help='Export format')
    export_parser.add_argument('--output', help='Output file (prints to console if not specified)')
    export_parser.add_argument('--template', help='Save as template with this name')
    
    # Import command
    import_parser = subparsers.add_parser('import', help='Import configuration to SQL database')
    import_parser.add_argument('config_file', help='Configuration file to import')
    import_parser.add_argument('--format', choices=['yaml', 'json'], required=True, help='Input format')
    import_parser.add_argument('--overwrite', action='store_true', help='Overwrite existing values')
    
    # Status command
    subparsers.add_parser('status', help='Show database status and information')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    setup_logging(args.debug)
    
    db_path = Path(args.db)
    
    if args.command == 'migrate':
        yaml_file = Path(args.yaml_file)
        success = migrate_yaml_to_sql(yaml_file, db_path, args.force)
        
    elif args.command == 'export':
        output_file = Path(args.output) if args.output else None
        success = export_config(db_path, args.format, output_file, args.template)
        
    elif args.command == 'import':
        config_file = Path(args.config_file)
        success = import_config(db_path, config_file, args.format, args.overwrite)
        
    elif args.command == 'status':
        success = show_status(db_path)
    
    else:
        parser.print_help()
        return 1
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())