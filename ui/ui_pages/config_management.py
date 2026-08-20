"""
Configuration Management UI for Sermon Audio Processor

Provides web interface for SQL-based configuration management with
import/export and history functionality.
"""

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

# Add src directory to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

try:
    from config_management import SQLConfigManager
    from config_migration import ConfigMigrationManager
    SQL_CONFIG_AVAILABLE = True
except ImportError as e:
    st.error(f"SQL Configuration system not available: {e}")
    SQL_CONFIG_AVAILABLE = False


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

                    st.session_state['settings_feedback'] = (
                        "✅ Migration completed successfully!\n"
                        f"📊 Categories: {status['categories']} | 🔑 Keys: {status['keys']} "
                        f"| 💾 Values: {status['values']}"
                    )
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
                        with tempfile.NamedTemporaryFile(
                            mode='w', suffix=f'.{file_type}', delete=False
                        ) as temp_file:
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
                                    config_manager.import_config(
                                        content, file_type, "ui_import", True
                                    )

                        # Clean up temp file
                        os.unlink(temp_path)

                        status_manager = ConfigMigrationManager(db_path)
                        status = status_manager.get_migration_status()
                        status_manager.close()

                    st.session_state['settings_feedback'] = (
                        "✅ Database created successfully!\n"
                        f"📊 Categories: {status['categories']} | 🔑 Keys: {status['keys']} "
                        f"| 💾 Values: {status['values']}"
                    )
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
                show_category_editor(
                    config_manager, selected_category, categories[selected_category]
                )

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
            except Exception:
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
            change_reason = st.text_input(
                "Change Reason (optional)",
                placeholder="Describe why you made these changes",
            )

        if submitted and changes:
            try:
                changed_by = st.session_state.get('user_name', 'streamlit_user')

                for key_path, value in changes.items():
                    config_manager.set_config(key_path, value, changed_by, change_reason)

                st.session_state['settings_feedback'] = (
                    f"✅ Updated {len(changes)} configuration value(s)"
                )
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

            st.session_state['settings_feedback'] = "✅ Configuration imported successfully!"
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
                limit = st.number_input(
                    "Number of records", min_value=10, max_value=1000, value=100
                )

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
