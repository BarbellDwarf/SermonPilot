"""
SQL-based Configuration Management for Sermon Audio Processor

Provides CRUD operations for configuration stored in SQLite database.
"""

import sqlite3
import json
import yaml
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class SQLConfigManager:
    """SQL-based configuration management system."""
    
    def __init__(self, db_path: str, environment: str = 'production'):
        self.db_path = db_path
        self.environment = environment
        self.connection = sqlite3.connect(db_path)
        self.connection.row_factory = sqlite3.Row
    
    def get_config(self, key_path: str = None) -> Dict[str, Any]:
        """Get configuration values."""
        if key_path:
            return self._get_single_config(key_path)
        else:
            return self._get_full_config()
    
    def set_config(self, key_path: str, value: Any, changed_by: str, reason: str = None):
        """Set configuration value with audit trail."""
        cursor = self.connection.cursor()
        
        # Get key info
        key_info = cursor.execute("""
            SELECT k.id, k.data_type, v.value as current_value
            FROM configuration_keys k
            LEFT JOIN configuration_values v ON k.id = v.key_id AND v.environment = ? AND v.is_active = 1
            WHERE k.key_path = ?
        """, (self.environment, key_path)).fetchone()
        
        if not key_info:
            raise ValueError(f"Configuration key '{key_path}' not found")
        
        key_id = key_info['id']
        current_value = key_info['current_value']
        
        # Validate value type
        validated_value = self._validate_value(value, key_info['data_type'])
        
        # Record change in history
        cursor.execute("""
            INSERT INTO configuration_history 
            (key_id, old_value, new_value, environment, changed_by, change_reason)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (key_id, current_value, validated_value, self.environment, changed_by, reason))
        
        # Update or insert current value
        cursor.execute("""
            INSERT OR REPLACE INTO configuration_values 
            (key_id, value, environment, created_by, is_active)
            VALUES (?, ?, ?, ?, 1)
        """, (key_id, validated_value, self.environment, changed_by))
        
        self.connection.commit()
        logger.info(f"Configuration '{key_path}' updated by {changed_by}")
    
    def export_config(self, format: str = 'yaml', template_name: str = None) -> str:
        """Export configuration in specified format."""
        config_data = self._get_full_config()
        
        if format == 'yaml':
            config_str = yaml.dump(config_data, default_flow_style=False, sort_keys=False)
        elif format == 'json':
            config_str = json.dumps(config_data, indent=2)
        elif format == 'env':
            config_str = self._export_as_env_file(config_data)
        else:
            raise ValueError(f"Unsupported export format: {format}")
        
        # Save export record
        if template_name:
            self._save_export_record(template_name, config_str, format)
        
        return config_str
    
    def import_config(self, config_data: str, format: str, imported_by: str, overwrite: bool = False):
        """Import configuration from string data."""
        if format == 'yaml':
            data = yaml.safe_load(config_data)
        elif format == 'json':
            data = json.loads(config_data)
        else:
            raise ValueError(f"Unsupported import format: {format}")
        
        self._import_config_recursive(data, "", imported_by, overwrite)
    
    def get_configuration_history(self, key_path: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get configuration change history."""
        cursor = self.connection.cursor()
        
        if key_path:
            rows = cursor.execute("""
                SELECT 
                    k.key_path,
                    h.old_value,
                    h.new_value,
                    h.changed_by,
                    h.change_reason,
                    h.changed_at
                FROM configuration_history h
                JOIN configuration_keys k ON h.key_id = k.id
                WHERE k.key_path = ? AND h.environment = ?
                ORDER BY h.changed_at DESC
                LIMIT ?
            """, (key_path, self.environment, limit)).fetchall()
        else:
            rows = cursor.execute("""
                SELECT 
                    k.key_path,
                    h.old_value,
                    h.new_value,
                    h.changed_by,
                    h.change_reason,
                    h.changed_at
                FROM configuration_history h
                JOIN configuration_keys k ON h.key_id = k.id
                WHERE h.environment = ?
                ORDER BY h.changed_at DESC
                LIMIT ?
            """, (self.environment, limit)).fetchall()
        
        return [dict(row) for row in rows]
    
    def get_configuration_keys(self, category: str = None) -> List[Dict[str, Any]]:
        """Get configuration keys with metadata."""
        cursor = self.connection.cursor()
        
        if category:
            rows = cursor.execute("""
                SELECT 
                    k.key_path,
                    k.key_name,
                    k.data_type,
                    k.is_secret,
                    k.is_required,
                    k.default_value,
                    k.description,
                    c.name as category_name
                FROM configuration_keys k
                JOIN configuration_categories c ON k.category_id = c.id
                WHERE c.name = ?
                ORDER BY k.key_path
            """, (category,)).fetchall()
        else:
            rows = cursor.execute("""
                SELECT 
                    k.key_path,
                    k.key_name,
                    k.data_type,
                    k.is_secret,
                    k.is_required,
                    k.default_value,
                    k.description,
                    c.name as category_name
                FROM configuration_keys k
                JOIN configuration_categories c ON k.category_id = c.id
                ORDER BY c.name, k.key_path
            """).fetchall()
        
        return [dict(row) for row in rows]
    
    def _get_single_config(self, key_path: str) -> Any:
        """Get a single configuration value."""
        cursor = self.connection.cursor()
        
        row = cursor.execute("""
            SELECT k.data_type, COALESCE(v.value, k.default_value) as value
            FROM configuration_keys k
            LEFT JOIN configuration_values v ON k.id = v.key_id AND v.environment = ? AND v.is_active = 1
            WHERE k.key_path = ?
        """, (self.environment, key_path)).fetchone()
        
        if not row:
            raise KeyError(f"Configuration key '{key_path}' not found")
        
        return self._parse_value(row['value'], row['data_type'])
    
    def _get_full_config(self) -> Dict[str, Any]:
        """Get complete configuration as nested dictionary."""
        cursor = self.connection.cursor()
        
        rows = cursor.execute("""
            SELECT k.key_path, k.data_type, COALESCE(v.value, k.default_value) as value
            FROM configuration_keys k
            LEFT JOIN configuration_values v ON k.id = v.key_id AND v.environment = ? AND v.is_active = 1
            WHERE k.data_type != 'object'
            ORDER BY k.key_path
        """, (self.environment,)).fetchall()
        
        config = {}
        for row in rows:
            if row['value'] is not None:
                self._set_nested_value(config, row['key_path'], self._parse_value(row['value'], row['data_type']))
        
        return config
    
    def _set_nested_value(self, config: Dict, path: str, value: Any):
        """Set value in nested dictionary using dot notation."""
        keys = path.split('.')
        current = config
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = value
    
    def _parse_value(self, value_str: str, data_type: str) -> Any:
        """Parse string value to appropriate type."""
        if value_str is None:
            return None
        
        if data_type == 'boolean':
            return value_str.lower() in ('true', '1', 'yes', 'on')
        elif data_type == 'integer':
            return int(value_str)
        elif data_type == 'float':
            return float(value_str)
        elif data_type == 'json':
            return json.loads(value_str)
        else:
            return value_str
    
    def _validate_value(self, value: Any, data_type: str) -> str:
        """Validate and convert value to string for storage."""
        if data_type == 'boolean' and not isinstance(value, bool):
            raise ValueError(f"Expected boolean value, got {type(value)}")
        elif data_type == 'integer' and not isinstance(value, int):
            raise ValueError(f"Expected integer value, got {type(value)}")
        elif data_type == 'float' and not isinstance(value, (int, float)):
            raise ValueError(f"Expected numeric value, got {type(value)}")
        elif data_type == 'json' and not isinstance(value, (list, dict)):
            raise ValueError(f"Expected JSON object/array, got {type(value)}")
        
        if data_type == 'json':
            return json.dumps(value)
        else:
            return str(value)
    
    def _export_as_env_file(self, config: Dict[str, Any], prefix: str = "") -> str:
        """Export configuration as environment variable file."""
        env_lines = []
        
        def flatten_config(obj, path=""):
            for key, value in obj.items():
                full_path = f"{path}_{key}".upper() if path else key.upper()
                
                if isinstance(value, dict):
                    flatten_config(value, full_path)
                else:
                    # Escape special characters for shell
                    if isinstance(value, str) and (' ' in value or '"' in value):
                        escaped_value = f'"{value.replace('"', '\\"')}"'
                    else:
                        escaped_value = str(value)
                    env_lines.append(f"{full_path}={escaped_value}")
        
        flatten_config(config)
        return "\n".join(sorted(env_lines))
    
    def _save_export_record(self, template_name: str, config_data: str, format: str):
        """Save export record for download tracking."""
        cursor = self.connection.cursor()
        cursor.execute("""
            INSERT INTO configuration_exports 
            (export_name, environment, config_data, export_format, created_by, is_template)
            VALUES (?, ?, ?, ?, 'system', 1)
        """, (template_name, self.environment, config_data, format))
        self.connection.commit()
    
    def _import_config_recursive(self, data: Dict[str, Any], parent_path: str, imported_by: str, overwrite: bool):
        """Recursively import configuration data."""
        for key, value in data.items():
            current_path = f"{parent_path}.{key}" if parent_path else key
            
            if isinstance(value, dict):
                # Recursively process nested configuration
                self._import_config_recursive(value, current_path, imported_by, overwrite)
            else:
                # Check if key exists
                cursor = self.connection.cursor()
                key_exists = cursor.execute(
                    "SELECT id FROM configuration_keys WHERE key_path = ?",
                    (current_path,)
                ).fetchone()
                
                if key_exists:
                    # Check if value already exists for this environment
                    value_exists = cursor.execute("""
                        SELECT id FROM configuration_values 
                        WHERE key_id = ? AND environment = ? AND is_active = 1
                    """, (key_exists[0], self.environment)).fetchone()
                    
                    if not value_exists or overwrite:
                        self.set_config(current_path, value, imported_by, "Imported from file")
                else:
                    logger.warning(f"Configuration key '{current_path}' not found in schema, skipping")
    
    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()