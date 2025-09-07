"""
Configuration Migration Manager for Sermon Audio Processor

Handles migration from YAML-based configuration to SQL-based storage.
"""

from pathlib import Path
import sqlite3
from typing import List, Dict, Any
import yaml
import json
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ConfigMigrationManager:
    """Manages migration from YAML to SQL configuration."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection = sqlite3.connect(db_path)
        self.connection.row_factory = sqlite3.Row
    
    def create_schema(self):
        """Create the configuration schema."""
        schema_file = Path(__file__).parent.parent.parent / "sql" / "create_config_schema.sql"
        
        if not schema_file.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_file}")
        
        with open(schema_file, 'r') as f:
            schema_sql = f.read()
        
        self.connection.executescript(schema_sql)
        self.connection.commit()
        logger.info("Configuration database schema created successfully")
    
    def migrate_yaml_to_sql(self, yaml_file: Path):
        """Migrate existing YAML configuration to SQL."""
        if not yaml_file.exists():
            raise FileNotFoundError(f"YAML configuration file not found: {yaml_file}")
        
        with open(yaml_file, 'r') as f:
            config_data = yaml.safe_load(f)
        
        if not config_data:
            logger.warning("YAML configuration file is empty or invalid")
            return
        
        self._create_categories()
        self._migrate_config_structure(config_data)
        self._populate_default_values(config_data)
        
        logger.info(f"Successfully migrated configuration from {yaml_file}")
    
    def _create_categories(self):
        """Create default configuration categories."""
        categories = [
            ('api', 'SermonAudio API Configuration'),
            ('llm', 'Language Model Configuration'),
            ('audio', 'Audio Processing Configuration'),
            ('database', 'Database Configuration'),
            ('embeddings', 'Embedding Model Configuration'),
            ('system', 'System and Debug Configuration'),
            ('web_ui', 'Web Interface Configuration'),
            ('metadata', 'Metadata Processing Configuration'),
            ('content', 'Content Management Configuration')
        ]
        
        cursor = self.connection.cursor()
        for name, description in categories:
            cursor.execute(
                "INSERT OR IGNORE INTO configuration_categories (name, description) VALUES (?, ?)",
                (name, description)
            )
        self.connection.commit()
    
    def _migrate_config_structure(self, config_data: Dict[str, Any], parent_path: str = ""):
        """Recursively migrate configuration structure."""
        cursor = self.connection.cursor()
        
        for key, value in config_data.items():
            current_path = f"{parent_path}.{key}" if parent_path else key
            category_name = self._determine_category(current_path)
            
            # Get category ID
            category_result = cursor.execute(
                "SELECT id FROM configuration_categories WHERE name = ?",
                (category_name,)
            ).fetchone()
            
            if not category_result:
                logger.warning(f"Category '{category_name}' not found for key '{current_path}'")
                continue
                
            category_id = category_result[0]
            
            if isinstance(value, dict):
                # Create parent key entry for nested objects
                cursor.execute("""
                    INSERT OR IGNORE INTO configuration_keys 
                    (category_id, key_name, key_path, data_type, description)
                    VALUES (?, ?, ?, 'object', ?)
                """, (category_id, key, current_path, f"Configuration group for {key}"))
                
                # Recursively process nested configuration
                self._migrate_config_structure(value, current_path)
            else:
                # Create leaf key entry
                data_type = self._determine_data_type(value)
                is_secret = self._is_secret_key(current_path)
                is_required = self._is_required_key(current_path)
                
                cursor.execute("""
                    INSERT OR IGNORE INTO configuration_keys 
                    (category_id, key_name, key_path, data_type, is_secret, is_required, default_value, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (category_id, key, current_path, data_type, is_secret, is_required, 
                     str(value), f"Configuration setting for {key}"))
        
        self.connection.commit()
    
    def _populate_default_values(self, config_data: Dict[str, Any], parent_path: str = "", environment: str = "production"):
        """Populate actual configuration values."""
        cursor = self.connection.cursor()
        
        for key, value in config_data.items():
            current_path = f"{parent_path}.{key}" if parent_path else key
            
            if isinstance(value, dict):
                # Recursively process nested values
                self._populate_default_values(value, current_path, environment)
            else:
                # Insert the actual value
                key_result = cursor.execute(
                    "SELECT id FROM configuration_keys WHERE key_path = ?",
                    (current_path,)
                ).fetchone()
                
                if key_result:
                    key_id = key_result[0]
                    
                    # Convert value to string for storage
                    if isinstance(value, (list, dict)):
                        value_str = json.dumps(value)
                    else:
                        value_str = str(value)
                    
                    cursor.execute("""
                        INSERT OR REPLACE INTO configuration_values 
                        (key_id, value, environment, created_by, is_active)
                        VALUES (?, ?, ?, 'migration', 1)
                    """, (key_id, value_str, environment))
        
        self.connection.commit()
    
    def _determine_category(self, key_path: str) -> str:
        """Determine category based on key path."""
        if any(pattern in key_path.lower() for pattern in ['api_key', 'broadcaster_id']):
            return 'api'
        elif key_path.startswith('llm'):
            return 'llm'
        elif key_path.startswith('audio') or key_path.startswith('use_audacity'):
            return 'audio'
        elif key_path.startswith('embeddings'):
            return 'embeddings'
        elif key_path.startswith('web_ui'):
            return 'web_ui'
        elif key_path.startswith('metadata_processing'):
            return 'metadata'
        elif key_path.startswith('content_management'):
            return 'content'
        elif any(pattern in key_path.lower() for pattern in ['debug', 'dry_run', 'output_directory', 'default_criteria']):
            return 'system'
        else:
            return 'system'
    
    def _determine_data_type(self, value: Any) -> str:
        """Determine SQL data type from Python value."""
        if isinstance(value, bool):
            return 'boolean'
        elif isinstance(value, int):
            return 'integer'
        elif isinstance(value, float):
            return 'float'
        elif isinstance(value, (list, dict)):
            return 'json'
        else:
            return 'string'
    
    def _is_secret_key(self, key_path: str) -> bool:
        """Determine if key contains sensitive data."""
        secret_patterns = [
            'api_key', 'password', 'secret', 'token', 'key'
        ]
        return any(pattern in key_path.lower() for pattern in secret_patterns)
    
    def _is_required_key(self, key_path: str) -> bool:
        """Determine if key is required for operation."""
        required_keys = [
            'api_key', 'broadcaster_id', 'llm.primary.provider'
        ]
        return key_path in required_keys
    
    def get_migration_status(self) -> Dict[str, Any]:
        """Get status of the migration."""
        cursor = self.connection.cursor()
        
        # Count categories
        categories_count = cursor.execute("SELECT COUNT(*) FROM configuration_categories").fetchone()[0]
        
        # Count keys
        keys_count = cursor.execute("SELECT COUNT(*) FROM configuration_keys").fetchone()[0]
        
        # Count values
        values_count = cursor.execute("SELECT COUNT(*) FROM configuration_values").fetchone()[0]
        
        # Get recent changes
        recent_changes = cursor.execute("""
            SELECT COUNT(*) FROM configuration_history 
            WHERE changed_at > datetime('now', '-1 day')
        """).fetchone()[0]
        
        return {
            'categories': categories_count,
            'keys': keys_count,
            'values': values_count,
            'recent_changes': recent_changes,
            'database_path': self.db_path
        }
    
    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()