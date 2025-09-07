# SQL Configuration Migration Plan

## Executive Summary

This plan outlines the migration from YAML-based configuration to a SQL-based configuration system with downloadable config export functionality. This approach provides better scalability, audit trails, and easier management for enterprise deployments.

## Current State Analysis

### Existing YAML Configuration
- Single `config.yaml` file with nested structure
- Environment variable substitution
- No versioning or audit trail
- Manual backup and restoration
- Limited validation and schema enforcement

### Target SQL Configuration Architecture

```sql
-- Configuration Schema Design
CREATE TABLE configuration_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE configuration_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER REFERENCES configuration_categories(id),
    key_name VARCHAR(200) NOT NULL,
    key_path VARCHAR(500) NOT NULL, -- e.g., 'llm.primary.ollama.host'
    data_type VARCHAR(20) DEFAULT 'string', -- string, integer, float, boolean, json
    is_secret BOOLEAN DEFAULT FALSE,
    is_required BOOLEAN DEFAULT FALSE,
    default_value TEXT,
    validation_regex TEXT,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(key_path)
);

CREATE TABLE configuration_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_id INTEGER REFERENCES configuration_keys(id),
    value TEXT,
    environment VARCHAR(50) DEFAULT 'production', -- production, staging, development
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    UNIQUE(key_id, environment)
);

CREATE TABLE configuration_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_id INTEGER REFERENCES configuration_keys(id),
    old_value TEXT,
    new_value TEXT,
    environment VARCHAR(50),
    changed_by VARCHAR(100),
    change_reason TEXT,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE configuration_exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    export_name VARCHAR(200) NOT NULL,
    environment VARCHAR(50),
    config_data TEXT, -- JSON or YAML format
    export_format VARCHAR(20) DEFAULT 'yaml', -- yaml, json, env
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    download_count INTEGER DEFAULT 0,
    is_template BOOLEAN DEFAULT FALSE
);
```

## Phase 1: Database Schema Implementation (Week 1)

### 1.1 Migration Scripts

Create database migration system:

```python
# src/config_migration/migration_manager.py
from pathlib import Path
import sqlite3
from typing import List, Dict, Any
import yaml
import json
from datetime import datetime

class ConfigMigrationManager:
    """Manages migration from YAML to SQL configuration."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection = sqlite3.connect(db_path)
        self.connection.row_factory = sqlite3.Row
    
    def create_schema(self):
        """Create the configuration schema."""
        with open('sql/create_config_schema.sql', 'r') as f:
            schema_sql = f.read()
        
        self.connection.executescript(schema_sql)
        self.connection.commit()
    
    def migrate_yaml_to_sql(self, yaml_file: Path):
        """Migrate existing YAML configuration to SQL."""
        with open(yaml_file, 'r') as f:
            config_data = yaml.safe_load(f)
        
        self._create_categories()
        self._migrate_config_structure(config_data)
        self._populate_default_values(config_data)
    
    def _create_categories(self):
        """Create default configuration categories."""
        categories = [
            ('api', 'SermonAudio API Configuration'),
            ('llm', 'Language Model Configuration'),
            ('audio', 'Audio Processing Configuration'),
            ('database', 'Database Configuration'),
            ('embeddings', 'Embedding Model Configuration'),
            ('system', 'System and Debug Configuration')
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
            category_id = cursor.execute(
                "SELECT id FROM configuration_categories WHERE name = ?",
                (category_name,)
            ).fetchone()[0]
            
            if isinstance(value, dict):
                # Create parent key entry
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
                    (category_id, key_name, key_path, data_type, is_secret, is_required, default_value)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (category_id, key, current_path, data_type, is_secret, is_required, str(value)))
        
        self.connection.commit()
    
    def _determine_category(self, key_path: str) -> str:
        """Determine category based on key path."""
        if key_path.startswith('api_key') or key_path.startswith('broadcaster_id'):
            return 'api'
        elif key_path.startswith('llm'):
            return 'llm'
        elif key_path.startswith('audio'):
            return 'audio'
        elif key_path.startswith('embeddings'):
            return 'embeddings'
        elif key_path.startswith('debug') or key_path.startswith('dry_run'):
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
```

### 1.2 Configuration Management API

```python
# src/config_management/config_manager.py
import sqlite3
import json
import yaml
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

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
                    env_lines.append(f"{full_path}={value}")
        
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
```

## Phase 2: Web Interface Integration (Week 2)

### 2.1 Configuration Management UI

```python
# ui_pages/config_management.py
import streamlit as st
import pandas as pd
from config_management.config_manager import SQLConfigManager
from datetime import datetime
import io

def show_config_management_page():
    """Configuration management interface."""
    st.title("⚙️ Configuration Management")
    
    # Initialize config manager
    config_manager = SQLConfigManager("sermon_processor.db")
    
    # Tabs for different operations
    tab1, tab2, tab3, tab4 = st.tabs([
        "📝 Edit Configuration", 
        "📥 Import/Export", 
        "📊 Configuration History", 
        "🔧 Templates"
    ])
    
    with tab1:
        show_config_editor(config_manager)
    
    with tab2:
        show_import_export(config_manager)
    
    with tab3:
        show_config_history(config_manager)
    
    with tab4:
        show_config_templates(config_manager)

def show_config_editor(config_manager: SQLConfigManager):
    """Configuration editor interface."""
    st.header("Configuration Editor")
    
    # Get current configuration
    current_config = config_manager.get_config()
    
    # Category selection
    categories = ['api', 'llm', 'audio', 'embeddings', 'system']
    selected_category = st.selectbox("Configuration Category", categories)
    
    # Dynamic form generation based on category
    with st.form(f"config_form_{selected_category}"):
        st.subheader(f"{selected_category.upper()} Configuration")
        
        if selected_category == 'api':
            api_key = st.text_input(
                "SermonAudio API Key", 
                value=current_config.get('api_key', ''),
                type='password'
            )
            broadcaster_id = st.text_input(
                "Broadcaster ID",
                value=current_config.get('broadcaster_id', '')
            )
            
        elif selected_category == 'llm':
            llm_config = current_config.get('llm', {})
            
            # Primary LLM Configuration
            st.write("**Primary LLM Provider**")
            primary_provider = st.selectbox(
                "Provider",
                ['ollama', 'openai', 'anthropic', 'xai', 'groq'],
                index=0 if not llm_config.get('primary', {}).get('provider') else 
                      ['ollama', 'openai', 'anthropic', 'xai', 'groq'].index(llm_config['primary']['provider'])
            )
            
            if primary_provider == 'ollama':
                ollama_host = st.text_input(
                    "Ollama Host",
                    value=llm_config.get('primary', {}).get('ollama', {}).get('host', 'http://localhost:11434')
                )
                ollama_model = st.text_input(
                    "Ollama Model",
                    value=llm_config.get('primary', {}).get('ollama', {}).get('model', 'llama3.2:latest')
                )
            elif primary_provider == 'openai':
                openai_api_key = st.text_input(
                    "OpenAI API Key",
                    value=llm_config.get('primary', {}).get('openai', {}).get('api_key', ''),
                    type='password'
                )
                openai_model = st.text_input(
                    "OpenAI Model",
                    value=llm_config.get('primary', {}).get('openai', {}).get('model', 'gpt-4')
                )
        
        # Form submission
        submitted = st.form_submit_button("💾 Save Configuration")
        
        if submitted:
            # Save configuration changes
            change_reason = st.text_input("Change Reason (optional)")
            changed_by = st.text_input("Changed By", value="admin")
            
            try:
                if selected_category == 'api':
                    config_manager.set_config('api_key', api_key, changed_by, change_reason)
                    config_manager.set_config('broadcaster_id', broadcaster_id, changed_by, change_reason)
                elif selected_category == 'llm':
                    config_manager.set_config('llm.primary.provider', primary_provider, changed_by, change_reason)
                    if primary_provider == 'ollama':
                        config_manager.set_config('llm.primary.ollama.host', ollama_host, changed_by, change_reason)
                        config_manager.set_config('llm.primary.ollama.model', ollama_model, changed_by, change_reason)
                
                st.success("✅ Configuration saved successfully!")
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ Error saving configuration: {str(e)}")

def show_import_export(config_manager: SQLConfigManager):
    """Import/Export interface."""
    st.header("Configuration Import/Export")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📥 Import Configuration")
        
        upload_format = st.selectbox("Import Format", ['yaml', 'json'])
        uploaded_file = st.file_uploader(
            f"Choose {upload_format.upper()} file",
            type=[upload_format]
        )
        
        overwrite_existing = st.checkbox("Overwrite existing values")
        
        if uploaded_file and st.button("🔄 Import Configuration"):
            try:
                config_data = uploaded_file.getvalue().decode('utf-8')
                config_manager.import_config(config_data, upload_format, "admin", overwrite_existing)
                st.success("✅ Configuration imported successfully!")
            except Exception as e:
                st.error(f"❌ Import failed: {str(e)}")
    
    with col2:
        st.subheader("📤 Export Configuration")
        
        export_format = st.selectbox("Export Format", ['yaml', 'json', 'env'])
        template_name = st.text_input("Template Name (optional)")
        
        if st.button("📋 Generate Export"):
            try:
                config_str = config_manager.export_config(export_format, template_name)
                
                # Download button
                st.download_button(
                    label=f"💾 Download {export_format.upper()} Config",
                    data=config_str,
                    file_name=f"sermon_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{export_format}",
                    mime=f"text/{export_format}"
                )
                
                # Preview
                st.text_area("Configuration Preview", config_str, height=300)
                
            except Exception as e:
                st.error(f"❌ Export failed: {str(e)}")

def show_config_history(config_manager: SQLConfigManager):
    """Configuration change history."""
    st.header("Configuration History")
    
    # Get configuration history
    cursor = config_manager.connection.cursor()
    history = cursor.execute("""
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
        LIMIT 100
    """, (config_manager.environment,)).fetchall()
    
    if history:
        df = pd.DataFrame(history, columns=[
            'Configuration Key', 'Old Value', 'New Value', 
            'Changed By', 'Reason', 'Changed At'
        ])
        
        # Mask sensitive values
        for idx, row in df.iterrows():
            if any(secret in row['Configuration Key'].lower() for secret in ['key', 'password', 'secret']):
                df.at[idx, 'Old Value'] = '***MASKED***' if row['Old Value'] else ''
                df.at[idx, 'New Value'] = '***MASKED***' if row['New Value'] else ''
        
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No configuration changes recorded yet.")

def show_config_templates(config_manager: SQLConfigManager):
    """Configuration templates management."""
    st.header("Configuration Templates")
    
    # Get saved templates
    cursor = config_manager.connection.cursor()
    templates = cursor.execute("""
        SELECT export_name, export_format, created_at, download_count
        FROM configuration_exports
        WHERE is_template = 1
        ORDER BY created_at DESC
    """).fetchall()
    
    if templates:
        st.subheader("Available Templates")
        
        for template in templates:
            with st.expander(f"📋 {template['export_name']} ({template['export_format'].upper()})"):
                col1, col2, col3 = st.columns([2, 1, 1])
                
                with col1:
                    st.write(f"**Created:** {template['created_at']}")
                    st.write(f"**Downloads:** {template['download_count']}")
                
                with col2:
                    if st.button(f"📥 Download", key=f"download_{template['export_name']}"):
                        # Get template data and provide download
                        template_data = cursor.execute("""
                            SELECT config_data FROM configuration_exports 
                            WHERE export_name = ? AND is_template = 1
                        """, (template['export_name'],)).fetchone()
                        
                        if template_data:
                            st.download_button(
                                label="💾 Save File",
                                data=template_data['config_data'],
                                file_name=f"{template['export_name']}.{template['export_format']}",
                                mime=f"text/{template['export_format']}"
                            )
                            
                            # Update download count
                            cursor.execute("""
                                UPDATE configuration_exports 
                                SET download_count = download_count + 1
                                WHERE export_name = ? AND is_template = 1
                            """, (template['export_name'],))
                            config_manager.connection.commit()
                
                with col3:
                    if st.button(f"🗑️ Delete", key=f"delete_{template['export_name']}"):
                        cursor.execute("""
                            DELETE FROM configuration_exports 
                            WHERE export_name = ? AND is_template = 1
                        """, (template['export_name'],))
                        config_manager.connection.commit()
                        st.rerun()
    
    else:
        st.info("No configuration templates saved yet.")
    
    # Create new template
    st.subheader("Create New Template")
    with st.form("new_template_form"):
        new_template_name = st.text_input("Template Name")
        new_template_format = st.selectbox("Format", ['yaml', 'json', 'env'])
        
        if st.form_submit_button("🔧 Create Template"):
            if new_template_name:
                try:
                    config_manager.export_config(new_template_format, new_template_name)
                    st.success(f"✅ Template '{new_template_name}' created successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Failed to create template: {str(e)}")
            else:
                st.error("Please provide a template name.")
```

## Phase 3: Backup and Migration Tools (Week 3)

### 3.1 Configuration Backup System

```python
# tools/config_backup.py
import sqlite3
import json
import gzip
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

class ConfigBackupManager:
    """Automated configuration backup and restoration."""
    
    def __init__(self, db_path: str, backup_dir: str = "config_backups"):
        self.db_path = db_path
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(exist_ok=True)
    
    def create_backup(self, backup_name: str = None) -> Path:
        """Create a complete configuration backup."""
        if not backup_name:
            backup_name = f"config_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        backup_data = {
            'metadata': {
                'backup_name': backup_name,
                'created_at': datetime.now().isoformat(),
                'database_path': self.db_path,
                'backup_version': '1.0'
            },
            'schema': self._export_schema(),
            'data': self._export_all_data()
        }
        
        backup_file = self.backup_dir / f"{backup_name}.json.gz"
        
        with gzip.open(backup_file, 'wt', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2)
        
        return backup_file
    
    def restore_backup(self, backup_file: Path, confirm: bool = False):
        """Restore configuration from backup."""
        if not confirm:
            raise ValueError("Backup restoration requires explicit confirmation")
        
        with gzip.open(backup_file, 'rt', encoding='utf-8') as f:
            backup_data = json.load(f)
        
        # Validate backup format
        if 'metadata' not in backup_data or 'data' not in backup_data:
            raise ValueError("Invalid backup file format")
        
        # Create restoration point before restore
        restoration_point = self.create_backup(f"pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
        try:
            self._restore_data(backup_data['data'])
            return restoration_point
        except Exception as e:
            raise Exception(f"Backup restoration failed: {str(e)}. Restoration point saved at: {restoration_point}")
    
    def _export_schema(self) -> Dict[str, Any]:
        """Export database schema."""
        connection = sqlite3.connect(self.db_path)
        cursor = connection.cursor()
        
        schema = {}
        
        # Export table schemas
        tables = cursor.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='table' AND name LIKE 'configuration_%'"
        ).fetchall()
        
        for table_name, create_sql in tables:
            schema[table_name] = create_sql
        
        connection.close()
        return schema
    
    def _export_all_data(self) -> Dict[str, Any]:
        """Export all configuration data."""
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        cursor = connection.cursor()
        
        data = {}
        
        # Export all configuration tables
        tables = ['configuration_categories', 'configuration_keys', 'configuration_values', 'configuration_history']
        
        for table in tables:
            rows = cursor.execute(f"SELECT * FROM {table}").fetchall()
            data[table] = [dict(row) for row in rows]
        
        connection.close()
        return data
    
    def _restore_data(self, backup_data: Dict[str, Any]):
        """Restore data from backup."""
        connection = sqlite3.connect(self.db_path)
        cursor = connection.cursor()
        
        try:
            # Clear existing data
            for table in ['configuration_values', 'configuration_history', 'configuration_keys', 'configuration_categories']:
                cursor.execute(f"DELETE FROM {table}")
            
            # Restore data in correct order (respecting foreign keys)
            restore_order = ['configuration_categories', 'configuration_keys', 'configuration_values', 'configuration_history']
            
            for table in restore_order:
                if table in backup_data:
                    for row in backup_data[table]:
                        columns = ', '.join(row.keys())
                        placeholders = ', '.join(['?' for _ in row.keys()])
                        
                        cursor.execute(
                            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                            list(row.values())
                        )
            
            connection.commit()
            
        except Exception as e:
            connection.rollback()
            raise e
        finally:
            connection.close()
    
    def list_backups(self) -> List[Dict[str, Any]]:
        """List available backups."""
        backups = []
        
        for backup_file in self.backup_dir.glob("*.json.gz"):
            try:
                with gzip.open(backup_file, 'rt', encoding='utf-8') as f:
                    metadata = json.load(f)['metadata']
                
                backups.append({
                    'file': backup_file,
                    'name': metadata['backup_name'],
                    'created_at': metadata['created_at'],
                    'size': backup_file.stat().st_size
                })
            except Exception:
                # Skip corrupted backup files
                continue
        
        return sorted(backups, key=lambda x: x['created_at'], reverse=True)
```

## Phase 4: Testing and Validation (Week 4)

### 4.1 Migration Testing Suite

```python
# tests/test_sql_config_migration.py
import pytest
import tempfile
import sqlite3
from pathlib import Path
import yaml
import json

from config_migration.migration_manager import ConfigMigrationManager
from config_management.config_manager import SQLConfigManager

class TestSQLConfigMigration:
    """Test suite for SQL configuration migration."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_db = self.temp_dir / "test_config.db"
        self.test_yaml = self.temp_dir / "test_config.yaml"
        
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
                }
            },
            'debug': False
        }
        
        with open(self.test_yaml, 'w') as f:
            yaml.dump(test_config, f)
    
    def test_schema_creation(self):
        """Test database schema creation."""
        manager = ConfigMigrationManager(str(self.test_db))
        manager.create_schema()
        
        # Verify tables were created
        connection = sqlite3.connect(self.test_db)
        cursor = connection.cursor()
        
        tables = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'configuration_%'"
        ).fetchall()
        
        expected_tables = {'configuration_categories', 'configuration_keys', 'configuration_values', 'configuration_history'}
        actual_tables = {table[0] for table in tables}
        
        assert actual_tables == expected_tables
        connection.close()
    
    def test_yaml_migration(self):
        """Test YAML to SQL migration."""
        manager = ConfigMigrationManager(str(self.test_db))
        manager.create_schema()
        manager.migrate_yaml_to_sql(self.test_yaml)
        
        # Verify migration
        config_manager = SQLConfigManager(str(self.test_db))
        migrated_config = config_manager.get_config()
        
        assert migrated_config['api_key'] == 'test-api-key'
        assert migrated_config['broadcaster_id'] == 'test-broadcaster'
        assert migrated_config['llm']['primary']['provider'] == 'ollama'
        assert migrated_config['debug'] == False
    
    def test_config_export_import(self):
        """Test configuration export and import."""
        manager = ConfigMigrationManager(str(self.test_db))
        manager.create_schema()
        manager.migrate_yaml_to_sql(self.test_yaml)
        
        config_manager = SQLConfigManager(str(self.test_db))
        
        # Test YAML export
        yaml_export = config_manager.export_config('yaml')
        exported_config = yaml.safe_load(yaml_export)
        
        assert exported_config['api_key'] == 'test-api-key'
        
        # Test JSON export
        json_export = config_manager.export_config('json')
        json_config = json.loads(json_export)
        
        assert json_config['broadcaster_id'] == 'test-broadcaster'
        
        # Test environment file export
        env_export = config_manager.export_config('env')
        assert 'API_KEY=test-api-key' in env_export
    
    def test_configuration_updates(self):
        """Test configuration updates with audit trail."""
        manager = ConfigMigrationManager(str(self.test_db))
        manager.create_schema()
        manager.migrate_yaml_to_sql(self.test_yaml)
        
        config_manager = SQLConfigManager(str(self.test_db))
        
        # Update configuration
        config_manager.set_config('api_key', 'new-api-key', 'test_user', 'Testing update')
        
        # Verify update
        updated_config = config_manager.get_config()
        assert updated_config['api_key'] == 'new-api-key'
        
        # Verify audit trail
        connection = sqlite3.connect(self.test_db)
        cursor = connection.cursor()
        
        history = cursor.execute("""
            SELECT old_value, new_value, changed_by, change_reason
            FROM configuration_history
            WHERE key_id = (SELECT id FROM configuration_keys WHERE key_path = 'api_key')
        """).fetchone()
        
        assert history[0] == 'test-api-key'  # old value
        assert history[1] == 'new-api-key'   # new value
        assert history[2] == 'test_user'     # changed by
        assert history[3] == 'Testing update'  # reason
        
        connection.close()
```

## Implementation Timeline

### Week 1: Database Foundation
- [ ] Create SQL schema for configuration storage
- [ ] Implement migration manager for YAML to SQL conversion
- [ ] Basic configuration CRUD operations
- [ ] Data validation and type checking

### Week 2: Web Interface
- [ ] Configuration management UI pages
- [ ] Import/export functionality
- [ ] Configuration history viewer
- [ ] Template management system

### Week 3: Advanced Features
- [ ] Automated backup system
- [ ] Environment-specific configurations
- [ ] Bulk configuration operations
- [ ] Configuration validation rules

### Week 4: Testing and Deployment
- [ ] Comprehensive test suite
- [ ] Performance optimization
- [ ] Documentation and user guides
- [ ] Production deployment procedures

## Benefits of SQL Configuration

### Scalability
- **Multi-environment support**: Development, staging, production configurations
- **Team collaboration**: Multiple users can manage configuration safely
- **Audit compliance**: Complete change history for regulatory requirements

### Security
- **Encrypted sensitive data**: Secure storage of API keys and credentials
- **Access control**: Role-based configuration management
- **Change tracking**: Who changed what and when

### Reliability
- **Atomic updates**: Configuration changes are transactional
- **Backup and restore**: Automated backup with point-in-time recovery
- **Validation**: Schema-enforced data integrity

### Usability
- **Web interface**: User-friendly configuration management
- **Export flexibility**: YAML, JSON, and environment file formats
- **Template system**: Reusable configuration templates

This migration plan ensures a smooth transition from file-based to database-driven configuration management while maintaining all existing functionality and adding enterprise-grade features.
