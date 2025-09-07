#!/usr/bin/env python3
"""
Test script for configuration backup and restore functionality.
"""

import tempfile
import sqlite3
from pathlib import Path
import yaml
import json
import sys
import os

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config_migration import ConfigMigrationManager
from config_management import SQLConfigManager, ConfigBackupManager


def test_backup_creation():
    """Test backup creation functionality."""
    print("💾 Testing backup creation...")
    
    # Create test configuration database
    test_config = {
        'api_key': 'test-backup-key',
        'broadcaster_id': 'test-backup-broadcaster',
        'debug': True
    }
    
    with tempfile.NamedTemporaryFile(suffix='.yaml', mode='w', delete=False) as temp_yaml:
        yaml.dump(test_config, temp_yaml)
        yaml_path = temp_yaml.name
    
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
        db_path = temp_db.name
    
    try:
        # Create and populate database
        with ConfigMigrationManager(db_path) as manager:
            manager.create_schema()
            manager.migrate_yaml_to_sql(Path(yaml_path))
        
        # Create backup
        with tempfile.TemporaryDirectory() as backup_dir:
            backup_manager = ConfigBackupManager(db_path, backup_dir)
            backup_file = backup_manager.create_backup("test_backup")
            
            if backup_file.exists() and backup_file.stat().st_size > 0:
                print("✅ Backup creation successful")
                return True
            else:
                print("❌ Backup creation failed - file not created or empty")
                return False
    
    finally:
        # Clean up
        for path in [yaml_path, db_path]:
            if os.path.exists(path):
                os.unlink(path)


def test_backup_restore():
    """Test backup and restore functionality."""
    print("🔄 Testing backup and restore...")
    
    # Create test configuration database
    test_config = {
        'api_key': 'original-key',
        'broadcaster_id': 'original-broadcaster',
        'debug': False
    }
    
    with tempfile.NamedTemporaryFile(suffix='.yaml', mode='w', delete=False) as temp_yaml:
        yaml.dump(test_config, temp_yaml)
        yaml_path = temp_yaml.name
    
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
        db_path = temp_db.name
    
    try:
        # Create and populate database
        with ConfigMigrationManager(db_path) as manager:
            manager.create_schema()
            manager.migrate_yaml_to_sql(Path(yaml_path))
        
        # Create backup
        with tempfile.TemporaryDirectory() as backup_dir:
            backup_manager = ConfigBackupManager(db_path, backup_dir)
            backup_file = backup_manager.create_backup("restore_test")
            
            # Modify configuration
            with SQLConfigManager(db_path) as config_manager:
                # Add a test configuration key for modification
                cursor = config_manager.connection.cursor()
                
                cursor.execute(
                    "INSERT INTO configuration_categories (name, description) VALUES (?, ?)",
                    ('test', 'Test Configuration')
                )
                category_id = cursor.lastrowid
                
                cursor.execute("""
                    INSERT INTO configuration_keys 
                    (category_id, key_name, key_path, data_type)
                    VALUES (?, ?, ?, ?)
                """, (category_id, 'test_setting', 'test.setting', 'string'))
                
                config_manager.connection.commit()
                
                config_manager.set_config('test.setting', 'modified_value', 'test_user', 'Test modification')
            
            # Restore from backup
            restoration_point = backup_manager.restore_backup(backup_file, confirm=True)
            
            # Verify restoration
            with SQLConfigManager(db_path) as config_manager:
                try:
                    # This should fail because the test key was added after backup
                    config_manager.get_config('test.setting')
                    print("❌ Restore failed - modified data still present")
                    return False
                except KeyError:
                    # This is expected - the key should not exist after restore
                    pass
                
                # Check original data is restored
                restored_config = config_manager.get_config()
                if (restored_config.get('api_key') == 'original-key' and
                    restored_config.get('broadcaster_id') == 'original-broadcaster'):
                    print("✅ Backup and restore successful")
                    return True
                else:
                    print("❌ Restore failed - original data not restored correctly")
                    return False
    
    finally:
        # Clean up
        for path in [yaml_path, db_path]:
            if os.path.exists(path):
                os.unlink(path)


def test_backup_verification():
    """Test backup verification functionality."""
    print("🔍 Testing backup verification...")
    
    # Create test configuration database
    test_config = {
        'api_key': 'verify-test-key',
        'debug': True
    }
    
    with tempfile.NamedTemporaryFile(suffix='.yaml', mode='w', delete=False) as temp_yaml:
        yaml.dump(test_config, temp_yaml)
        yaml_path = temp_yaml.name
    
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
        db_path = temp_db.name
    
    try:
        # Create and populate database
        with ConfigMigrationManager(db_path) as manager:
            manager.create_schema()
            manager.migrate_yaml_to_sql(Path(yaml_path))
        
        # Create backup
        with tempfile.TemporaryDirectory() as backup_dir:
            backup_manager = ConfigBackupManager(db_path, backup_dir)
            backup_file = backup_manager.create_backup("verify_test")
            
            # Verify backup
            verification = backup_manager.verify_backup(backup_file)
            
            if (verification['is_valid'] and 
                'configuration_categories' in verification['stats'] and
                verification['stats']['configuration_categories'] > 0):
                print("✅ Backup verification successful")
                return True
            else:
                print(f"❌ Backup verification failed: {verification}")
                return False
    
    finally:
        # Clean up
        for path in [yaml_path, db_path]:
            if os.path.exists(path):
                os.unlink(path)


def test_backup_listing():
    """Test backup listing functionality."""
    print("📂 Testing backup listing...")
    
    # Create test configuration database
    test_config = {'api_key': 'list-test-key'}
    
    with tempfile.NamedTemporaryFile(suffix='.yaml', mode='w', delete=False) as temp_yaml:
        yaml.dump(test_config, temp_yaml)
        yaml_path = temp_yaml.name
    
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
        db_path = temp_db.name
    
    try:
        # Create and populate database
        with ConfigMigrationManager(db_path) as manager:
            manager.create_schema()
            manager.migrate_yaml_to_sql(Path(yaml_path))
        
        # Create multiple backups
        with tempfile.TemporaryDirectory() as backup_dir:
            backup_manager = ConfigBackupManager(db_path, backup_dir)
            
            backup1 = backup_manager.create_backup("list_test_1")
            backup2 = backup_manager.create_backup("list_test_2")
            
            # List backups
            backups = backup_manager.list_backups()
            
            if (len(backups) == 2 and
                all(b['name'] in ['list_test_1', 'list_test_2'] for b in backups)):
                print("✅ Backup listing successful")
                return True
            else:
                print(f"❌ Backup listing failed. Found {len(backups)} backups: {[b['name'] for b in backups]}")
                return False
    
    finally:
        # Clean up
        for path in [yaml_path, db_path]:
            if os.path.exists(path):
                os.unlink(path)


def main():
    """Run all backup tests."""
    print("🧪 Starting Configuration Backup Tests")
    print("=" * 50)
    
    tests = [
        test_backup_creation,
        test_backup_restore,
        test_backup_verification,
        test_backup_listing
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
            results.append(False)
        print()
    
    print("=" * 50)
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"🎉 All backup tests passed! ({passed}/{total})")
        return True
    else:
        print(f"❌ {total - passed} backup tests failed. ({passed}/{total} passed)")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)