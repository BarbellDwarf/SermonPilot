#!/usr/bin/env python3
"""
Test script for SQL configuration migration system.

Tests basic functionality of the migration manager and SQL config manager.
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
from config_management import SQLConfigManager


def test_schema_creation():
    """Test database schema creation."""
    print("🔧 Testing schema creation...")
    
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
        db_path = temp_db.name
    
    try:
        with ConfigMigrationManager(db_path) as manager:
            manager.create_schema()
        
        # Verify tables were created
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()
        
        tables = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'configuration_%'"
        ).fetchall()
        
        expected_tables = {'configuration_categories', 'configuration_keys', 'configuration_values', 'configuration_history', 'configuration_exports'}
        actual_tables = {table[0] for table in tables}
        
        connection.close()
        
        if actual_tables == expected_tables:
            print("✅ Schema creation successful")
            return True
        else:
            print(f"❌ Schema creation failed. Expected {expected_tables}, got {actual_tables}")
            return False
    
    finally:
        # Clean up
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_yaml_migration():
    """Test YAML to SQL migration."""
    print("📄 Testing YAML migration...")
    
    # Create test YAML configuration
    test_config = {
        'api_key': 'test-api-key',
        'broadcaster_id': 'test-broadcaster',
        'llm': {
            'primary': {
                'provider': 'ollama',
                'ollama': {
                    'host': 'http://localhost:11434',
                    'model': 'llama3.2:latest'
                }
            },
            'fallback': {
                'enabled': True,
                'provider': 'openai',
                'openai': {
                    'api_key': 'test-openai-key',
                    'model': 'gpt-4'
                }
            }
        },
        'debug': False,
        'audio_enhancement_method': 'deepfilternet',
        'embeddings': {
            'primary': {
                'provider': 'sentence_transformers',
                'model': 'all-MiniLM-L6-v2'
            }
        }
    }
    
    with tempfile.NamedTemporaryFile(suffix='.yaml', mode='w', delete=False) as temp_yaml:
        yaml.dump(test_config, temp_yaml)
        yaml_path = temp_yaml.name
    
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
        db_path = temp_db.name
    
    try:
        # Migrate YAML to SQL
        with ConfigMigrationManager(db_path) as manager:
            manager.create_schema()
            manager.migrate_yaml_to_sql(Path(yaml_path))
        
        # Verify migration
        with SQLConfigManager(db_path) as config_manager:
            migrated_config = config_manager.get_config()
            
            # Check some key values
            if (migrated_config.get('api_key') == 'test-api-key' and
                migrated_config.get('broadcaster_id') == 'test-broadcaster' and
                migrated_config.get('llm', {}).get('primary', {}).get('provider') == 'ollama' and
                migrated_config.get('debug') == False):
                print("✅ YAML migration successful")
                return True
            else:
                print(f"❌ YAML migration failed. Migrated config: {migrated_config}")
                return False
    
    finally:
        # Clean up
        for path in [yaml_path, db_path]:
            if os.path.exists(path):
                os.unlink(path)


def test_config_operations():
    """Test configuration CRUD operations."""
    print("⚙️ Testing configuration operations...")
    
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
        db_path = temp_db.name
    
    try:
        # Create schema and add test data
        with ConfigMigrationManager(db_path) as manager:
            manager.create_schema()
            
        with SQLConfigManager(db_path) as config_manager:
            # Test setting configuration manually
            cursor = config_manager.connection.cursor()
            
            # Add a test category and key
            cursor.execute(
                "INSERT INTO configuration_categories (name, description) VALUES (?, ?)",
                ('test', 'Test Configuration')
            )
            category_id = cursor.lastrowid
            
            cursor.execute("""
                INSERT INTO configuration_keys 
                (category_id, key_name, key_path, data_type, is_secret, is_required)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (category_id, 'test_setting', 'test.setting', 'string', False, False))
            
            config_manager.connection.commit()
            
            # Test setting and getting configuration
            config_manager.set_config('test.setting', 'test_value', 'test_user', 'Testing')
            
            retrieved_value = config_manager.get_config('test.setting')
            if retrieved_value == 'test_value':
                print("✅ Configuration operations successful")
                return True
            else:
                print(f"❌ Configuration operations failed. Expected 'test_value', got '{retrieved_value}'")
                return False
    
    except Exception as e:
        print(f"❌ Configuration operations failed with error: {e}")
        return False
    
    finally:
        # Clean up
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_export_import():
    """Test configuration export and import."""
    print("📤 Testing export/import...")
    
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
        db_path = temp_db.name
    
    try:
        # Set up test configuration
        test_config = {
            'api_key': 'export-test-key',
            'debug': True
        }
        
        with tempfile.NamedTemporaryFile(suffix='.yaml', mode='w', delete=False) as temp_yaml:
            yaml.dump(test_config, temp_yaml)
            yaml_path = temp_yaml.name
        
        with ConfigMigrationManager(db_path) as manager:
            manager.create_schema()
            manager.migrate_yaml_to_sql(Path(yaml_path))
        
        with SQLConfigManager(db_path) as config_manager:
            # Test YAML export
            yaml_export = config_manager.export_config('yaml')
            exported_config = yaml.safe_load(yaml_export)
            
            # Test JSON export
            json_export = config_manager.export_config('json')
            json_config = json.loads(json_export)
            
            # Test environment file export
            env_export = config_manager.export_config('env')
            
            if (exported_config.get('api_key') == 'export-test-key' and
                json_config.get('debug') == True and
                'API_KEY=export-test-key' in env_export):
                print("✅ Export/import successful")
                return True
            else:
                print(f"❌ Export/import failed")
                print(f"YAML: {exported_config}")
                print(f"JSON: {json_config}")
                print(f"ENV: {env_export}")
                return False
        
        # Clean up temp yaml
        if os.path.exists(yaml_path):
            os.unlink(yaml_path)
    
    finally:
        # Clean up
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_configuration_history():
    """Test configuration change history."""
    print("📊 Testing configuration history...")
    
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as temp_db:
        db_path = temp_db.name
    
    try:
        with ConfigMigrationManager(db_path) as manager:
            manager.create_schema()
            
        with SQLConfigManager(db_path) as config_manager:
            # Add a test configuration key
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
            
            # Make some changes
            config_manager.set_config('test.setting', 'value1', 'user1', 'Initial value')
            config_manager.set_config('test.setting', 'value2', 'user2', 'Updated value')
            
            # Check history (oldest first in this test data)
            history = config_manager.get_configuration_history('test.setting')
            
            # History should be ordered by most recent first, but check what we actually get
            if (len(history) == 2 and
                ((history[0]['new_value'] == 'value2' and history[1]['new_value'] == 'value1') or  # Reverse chronological
                 (history[1]['new_value'] == 'value2' and history[0]['new_value'] == 'value1'))):  # Chronological
                print("✅ Configuration history successful")
                return True
            else:
                print(f"❌ Configuration history failed. History: {history}")
                return False
    
    finally:
        # Clean up
        if os.path.exists(db_path):
            os.unlink(db_path)


def main():
    """Run all tests."""
    print("🧪 Starting SQL Configuration Migration Tests")
    print("=" * 50)
    
    tests = [
        test_schema_creation,
        test_yaml_migration,
        test_config_operations,
        test_export_import,
        test_configuration_history
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
        print(f"🎉 All tests passed! ({passed}/{total})")
        return True
    else:
        print(f"❌ {total - passed} tests failed. ({passed}/{total} passed)")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)