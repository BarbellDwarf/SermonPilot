"""
Configuration Management UI for Sermon Audio Processor

Provides web interface for SQL-based configuration management with
import/export, history, and template functionality.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import io
import tempfile
from pathlib import Path
import sys
import os

# Add src directory to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

try:
    from config_migration import ConfigMigrationManager
    from config_management import SQLConfigManager, ConfigBackupManager
    SQL_CONFIG_AVAILABLE = True
except ImportError as e:
    st.error(f"SQL Configuration system not available: {e}")
    SQL_CONFIG_AVAILABLE = False


def show_config_management_page():
    """Configuration management interface - redirects to Settings."""
    from ui.pages import settings as settings_page
    st.title("⚙️ Configuration Management")
    st.info("Configuration management has been moved to the **Settings** page.")
    if st.button("📋 Go to Settings", type="primary"):
        st.switch_page(settings_page)


def show_database_setup(db_path: str):
    """Setup interface for creating new configuration database."""
    st.subheader("🔧 Database Setup")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Create New Database**")
        
        # Look for existing YAML config
        yaml_configs = list(Path(".").glob("*.yaml"))
        if yaml_configs:
            st.write("Found YAML configuration files:")
            for config_file in yaml_configs:
                st.write(f"  - {config_file}")
            
            selected_yaml = st.selectbox(
                "Select YAML config to migrate",
                options=yaml_configs,
                format_func=lambda x: str(x)
            )
            
            if st.button("🔄 Migrate YAML to SQL"):
                try:
                    with st.spinner("Migrating configuration..."):
                        with ConfigMigrationManager(db_path) as manager:
                            manager.create_schema()
                            manager.migrate_yaml_to_sql(selected_yaml)
                            
                            status = manager.get_migration_status()
                    
                    st.success("✅ Migration completed successfully!")
                    st.info(f"📊 Categories: {status['categories']} | 🔑 Keys: {status['keys']} | 💾 Values: {status['values']}")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Migration failed: {e}")
        else:
            st.info("No YAML configuration files found in current directory")
    
    with col2:
        st.write("**Import from File**")
        
        uploaded_file = st.file_uploader(
            "Upload configuration file",
            type=['yaml', 'yml', 'json']
        )
        
        if uploaded_file:
            file_type = uploaded_file.name.split('.')[-1].lower()
            if file_type in ['yml']:
                file_type = 'yaml'
            
            if st.button("📤 Import and Create Database"):
                try:
                    with st.spinner("Creating database from uploaded file..."):
                        # Save uploaded file temporarily
                        with tempfile.NamedTemporaryFile(mode='w', suffix=f'.{file_type}', delete=False) as temp_file:
                            content = uploaded_file.getvalue().decode('utf-8')
                            temp_file.write(content)
                            temp_path = temp_file.name
                        
                        # Create database and migrate
                        with ConfigMigrationManager(db_path) as manager:
                            manager.create_schema()
                            if file_type == 'yaml':
                                manager.migrate_yaml_to_sql(Path(temp_path))
                            else:
                                # For JSON, use SQL config manager import
                                with SQLConfigManager(db_path) as config_manager:
                                    config_manager.import_config(content, file_type, "ui_import", True)
                        
                        # Clean up temp file
                        os.unlink(temp_path)
                        
                        status_manager = ConfigMigrationManager(db_path)
                        status = status_manager.get_migration_status()
                        status_manager.close()
                    
                    st.success("✅ Database created successfully!")
                    st.info(f"📊 Categories: {status['categories']} | 🔑 Keys: {status['keys']} | 💾 Values: {status['values']}")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"❌ Import failed: {e}")


def show_config_editor(db_path: str):
    """Configuration editor interface."""
    st.header("Configuration Editor")
    
    try:
        with SQLConfigManager(db_path) as config_manager:
            # Get configuration keys by category
            keys = config_manager.get_configuration_keys()
            
            if not keys:
                st.warning("No configuration keys found in database")
                return
            
            # Group keys by category
            categories = {}
            for key in keys:
                cat = key['category_name']
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(key)
            
            # Category selection
            selected_category = st.selectbox(
                "Configuration Category", 
                list(categories.keys())
            )
            
            if selected_category and selected_category in categories:
                show_category_editor(config_manager, selected_category, categories[selected_category])
    
    except Exception as e:
        st.error(f"❌ Failed to load configuration: {e}")


def show_category_editor(config_manager: SQLConfigManager, category: str, keys: list):
    """Edit configuration for a specific category."""
    st.subheader(f"{category.title()} Configuration")
    
    # Filter to only leaf nodes (not object types)
    editable_keys = [k for k in keys if k['data_type'] != 'object']
    
    if not editable_keys:
        st.info("No editable configuration keys in this category")
        return
    
    with st.form(f"config_form_{category}"):
        changes = {}
        
        for key in editable_keys:
            key_path = key['key_path']
            data_type = key['data_type']
            is_secret = key['is_secret']
            is_required = key['is_required']
            description = key['description'] or f"Configuration for {key['key_name']}"
            
            # Get current value
            try:
                current_value = config_manager.get_config(key_path)
            except:
                current_value = key['default_value']
            
            # Create appropriate input widget
            label = key['key_name']
            if is_required:
                label += " *"
            if is_secret:
                label += " 🔒"
            
            if data_type == 'boolean':
                new_value = st.checkbox(
                    label,
                    value=bool(current_value) if current_value is not None else False,
                    help=description
                )
            elif data_type == 'integer':
                new_value = st.number_input(
                    label,
                    value=int(current_value) if current_value is not None else 0,
                    step=1,
                    help=description
                )
            elif data_type == 'float':
                new_value = st.number_input(
                    label,
                    value=float(current_value) if current_value is not None else 0.0,
                    help=description
                )
            elif data_type == 'json':
                new_value = st.text_area(
                    label,
                    value=str(current_value) if current_value is not None else "{}",
                    help=f"{description} (JSON format)"
                )
            else:  # string
                if is_secret:
                    new_value = st.text_input(
                        label,
                        value=str(current_value) if current_value is not None else "",
                        type='password',
                        help=description
                    )
                else:
                    new_value = st.text_input(
                        label,
                        value=str(current_value) if current_value is not None else "",
                        help=description
                    )
            
            # Track changes
            if new_value != current_value:
                changes[key_path] = new_value
        
        # Form submission
        col1, col2 = st.columns([3, 1])
        with col2:
            submitted = st.form_submit_button("💾 Save Changes", width='stretch')
        
        with col1:
            change_reason = st.text_input("Change Reason (optional)", placeholder="Describe why you made these changes")
        
        if submitted and changes:
            try:
                changed_by = st.session_state.get('user_name', 'streamlit_user')
                
                for key_path, value in changes.items():
                    config_manager.set_config(key_path, value, changed_by, change_reason)
                
                st.success(f"✅ Updated {len(changes)} configuration value(s)")
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ Error saving configuration: {str(e)}")
        
        elif submitted and not changes:
            st.info("No changes detected")


def show_import_export(db_path: str):
    """Import/Export interface."""
    st.header("Configuration Import/Export")
    
    col1, col2 = st.columns(2)
    
    with col1:
        show_import_section(db_path)
    
    with col2:
        show_export_section(db_path)


def show_import_section(db_path: str):
    """Configuration import section."""
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
            
            with SQLConfigManager(db_path) as config_manager:
                config_manager.import_config(
                    config_data, 
                    upload_format, 
                    st.session_state.get('user_name', 'streamlit_user'), 
                    overwrite_existing
                )
            
            st.success("✅ Configuration imported successfully!")
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ Import failed: {str(e)}")


def show_export_section(db_path: str):
    """Configuration export section."""
    st.subheader("📤 Export Configuration")
    
    export_format = st.selectbox("Export Format", ['yaml', 'json', 'env'])
    template_name = st.text_input("Template Name (optional)")
    
    if st.button("📋 Generate Export"):
        try:
            with SQLConfigManager(db_path) as config_manager:
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


def show_config_history(db_path: str):
    """Configuration change history."""
    st.header("Configuration History")
    
    try:
        with SQLConfigManager(db_path) as config_manager:
            # Filter options
            col1, col2 = st.columns(2)
            
            with col1:
                key_filter = st.text_input("Filter by key path (optional)")
            
            with col2:
                limit = st.number_input("Number of records", min_value=10, max_value=1000, value=100)
            
            # Get history
            if key_filter:
                history = config_manager.get_configuration_history(key_filter, limit)
            else:
                history = config_manager.get_configuration_history(limit=limit)
            
            if history:
                df = pd.DataFrame(history)
                
                # Mask sensitive values
                for idx, row in df.iterrows():
                    key_path = row['key_path']
                    if any(secret in key_path.lower() for secret in ['key', 'password', 'secret']):
                        if row['old_value']:
                            df.at[idx, 'old_value'] = '***MASKED***'
                        if row['new_value']:
                            df.at[idx, 'new_value'] = '***MASKED***'
                
                # Rename columns for display
                df = df.rename(columns={
                    'key_path': 'Configuration Key',
                    'old_value': 'Old Value',
                    'new_value': 'New Value',
                    'changed_by': 'Changed By',
                    'change_reason': 'Reason',
                    'changed_at': 'Changed At'
                })
                
                st.dataframe(df, width='stretch')
            else:
                st.info("No configuration changes recorded yet.")
    
    except Exception as e:
        st.error(f"❌ Failed to load history: {e}")


def show_config_templates(db_path: str):
    """Configuration templates management."""
    st.header("Configuration Templates")
    
    try:
        with SQLConfigManager(db_path) as config_manager:
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
                col1, col2 = st.columns(2)
                
                with col1:
                    new_template_name = st.text_input("Template Name")
                
                with col2:
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
    
    except Exception as e:
        st.error(f"❌ Failed to load templates: {e}")


def show_backup_restore(db_path: str):
    """Backup and restore interface."""
    st.header("💾 Backup & Restore")
    
    backup_manager = ConfigBackupManager(db_path)
    
    col1, col2 = st.columns(2)
    
    with col1:
        show_backup_section(backup_manager)
    
    with col2:
        show_restore_section(backup_manager)


def show_backup_section(backup_manager: ConfigBackupManager):
    """Backup creation section."""
    st.subheader("💾 Create Backup")
    
    backup_name = st.text_input(
        "Backup Name (optional)",
        placeholder="Leave empty for auto-generated name"
    )
    
    if st.button("🔄 Create Backup"):
        try:
            with st.spinner("Creating backup..."):
                backup_file = backup_manager.create_backup(backup_name if backup_name else None)
            
            st.success(f"✅ Backup created: {backup_file.name}")
            
            # Show backup info
            backup_info = backup_manager.get_backup_info(backup_file)
            st.info(f"📊 Size: {backup_info['file_size']:,} bytes")
            
        except Exception as e:
            st.error(f"❌ Backup failed: {e}")
    
    # List existing backups
    st.subheader("📂 Available Backups")
    
    try:
        backups = backup_manager.list_backups()
        
        if backups:
            for backup in backups:
                with st.expander(f"📁 {backup['name']}"):
                    col1, col2, col3 = st.columns([2, 1, 1])
                    
                    with col1:
                        st.write(f"**Created:** {backup['created_at']}")
                        st.write(f"**Size:** {backup['size']:,} bytes")
                        st.write(f"**Database:** {backup['database_path']}")
                    
                    with col2:
                        if st.button("📋 Info", key=f"info_{backup['name']}"):
                            show_backup_info(backup_manager, backup['file'])
                    
                    with col3:
                        if st.button("🗑️ Delete", key=f"del_{backup['name']}"):
                            if backup_manager.delete_backup(backup['file']):
                                st.success("✅ Backup deleted")
                                st.rerun()
                            else:
                                st.error("❌ Failed to delete backup")
        else:
            st.info("No backups available")
    
    except Exception as e:
        st.error(f"❌ Failed to list backups: {e}")


def show_restore_section(backup_manager: ConfigBackupManager):
    """Restore from backup section."""
    st.subheader("🔄 Restore from Backup")
    
    try:
        backups = backup_manager.list_backups()
        
        if backups:
            # Select backup to restore
            backup_options = {f"{b['name']} ({b['created_at']})": b for b in backups}
            selected_backup_key = st.selectbox(
                "Select backup to restore",
                list(backup_options.keys())
            )
            
            if selected_backup_key:
                selected_backup = backup_options[selected_backup_key]
                
                # Show backup verification
                verification = backup_manager.verify_backup(selected_backup['file'])
                
                if verification['is_valid']:
                    st.success("✅ Backup file is valid")
                    
                    # Show backup stats
                    if verification['stats']:
                        st.write("**Backup Contents:**")
                        for table, count in verification['stats'].items():
                            st.write(f"  - {table}: {count} records")
                else:
                    st.error("❌ Backup file is invalid")
                    for error in verification['errors']:
                        st.error(f"  - {error}")
                
                if verification['warnings']:
                    for warning in verification['warnings']:
                        st.warning(f"⚠️ {warning}")
                
                # Confirmation and restore
                st.warning("⚠️ **Warning:** Restoring will replace all current configuration data!")
                
                confirm_restore = st.checkbox("I understand that this will replace all current configuration")
                
                if confirm_restore and st.button("🔄 Restore Configuration"):
                    try:
                        with st.spinner("Restoring configuration..."):
                            restoration_point = backup_manager.restore_backup(
                                selected_backup['file'], 
                                confirm=True
                            )
                        
                        st.success("✅ Configuration restored successfully!")
                        st.info(f"📁 Restoration point created: {restoration_point.name}")
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"❌ Restore failed: {e}")
        else:
            st.info("No backups available for restore")
    
    except Exception as e:
        st.error(f"❌ Failed to load restore options: {e}")


def show_backup_info(backup_manager: ConfigBackupManager, backup_file: Path):
    """Show detailed backup information."""
    try:
        backup_info = backup_manager.get_backup_info(backup_file)
        
        if backup_info['is_valid']:
            st.success("✅ Valid backup file")
            
            metadata = backup_info['metadata']
            st.write("**Metadata:**")
            for key, value in metadata.items():
                st.write(f"  - {key}: {value}")
            
            st.write("**Data Statistics:**")
            for table, count in backup_info['data_stats'].items():
                st.write(f"  - {table}: {count} records")
            
            st.write(f"**File Size:** {backup_info['file_size']:,} bytes")
        else:
            st.error("❌ Invalid backup file")
            if 'error' in backup_info:
                st.error(f"Error: {backup_info['error']}")
    
    except Exception as e:
        st.error(f"❌ Failed to get backup info: {e}")


def show_database_management(db_path: str):
    """Database management tools."""
    st.header("Database Management")
    
    try:
        with ConfigMigrationManager(db_path) as manager:
            status = manager.get_migration_status()
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📊 Database Statistics")
            st.metric("Categories", status['categories'])
            st.metric("Configuration Keys", status['keys'])
            st.metric("Configuration Values", status['values'])
            st.metric("Recent Changes (24h)", status['recent_changes'])
        
        with col2:
            st.subheader("🛠️ Maintenance Tools")
            
            if st.button("🔄 Refresh Statistics"):
                st.rerun()
            
            st.warning("⚠️ Advanced Operations")
            
            if st.button("🗑️ Clear All History", help="Remove all configuration change history"):
                if st.session_state.get('confirm_clear_history'):
                    try:
                        with SQLConfigManager(db_path) as config_manager:
                            cursor = config_manager.connection.cursor()
                            cursor.execute("DELETE FROM configuration_history")
                            config_manager.connection.commit()
                        st.success("✅ Configuration history cleared")
                        st.session_state.confirm_clear_history = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed to clear history: {e}")
                else:
                    st.session_state.confirm_clear_history = True
                    st.warning("Click again to confirm clearing all history")
            
            if st.session_state.get('confirm_clear_history', False):
                if st.button("❌ Cancel"):
                    st.session_state.confirm_clear_history = False
                    st.rerun()
    
    except Exception as e:
        st.error(f"❌ Failed to load database information: {e}")


if __name__ == "__main__":
    show_config_management_page()