# SQL Configuration Migration Guide

## Overview

The SermonPilot now supports SQL-based configuration management, providing enhanced scalability, audit trails, and team collaboration capabilities compared to the traditional YAML-based approach.

## Key Features

- **🔄 Seamless Migration**: Automatic migration from existing YAML configurations
- **🌍 Multi-Environment Support**: Separate configurations for development, staging, and production
- **📊 Audit Trail**: Complete history of all configuration changes with timestamps and reasons
- **💾 Backup & Restore**: Automated backup system with point-in-time recovery
- **🔧 Web Interface**: Intuitive Streamlit-based configuration management UI
- **📤 Import/Export**: Support for YAML, JSON, and environment file formats
- **🔗 Template System**: Reusable configuration templates for common setups

## Architecture

### Database Schema

The SQL configuration system uses SQLite with the following tables:

- **`configuration_categories`**: Logical groupings (api, llm, audio, etc.)
- **`configuration_keys`**: Key definitions with metadata and validation rules
- **`configuration_values`**: Actual configuration values per environment
- **`configuration_history`**: Complete audit trail of changes
- **`configuration_exports`**: Saved templates and export tracking

### File Structure

```
SermonPilot/
├── sql/
│   └── create_config_schema.sql          # Database schema
├── src/
│   ├── config_migration/
│   │   ├── __init__.py
│   │   └── migration_manager.py          # YAML to SQL migration
│   └── config_management/
│       ├── __init__.py
│       ├── config_manager.py             # SQL config CRUD operations
│       └── backup_manager.py             # Backup and restore
├── tools/
│   └── config_migration_tool.py          # Command-line interface
├── ui/ui_pages/
│   └── config_management.py              # Web interface
└── tests/
    ├── test_sql_config_migration.py      # Migration tests
    └── test_config_backup.py             # Backup tests
```

## Getting Started

### 1. Migration from YAML

#### Command Line Migration

```bash
# Migrate existing config.yaml to SQL database
python tools/config_migration_tool.py --db sermon_config.db migrate config.yaml

# Force overwrite existing database
python tools/config_migration_tool.py --db sermon_config.db migrate config.yaml --force
```

#### Web Interface Migration

1. Launch the Streamlit app: `streamlit run streamlit_app.py`
2. Navigate to "🔧 Config Management" in the sidebar
3. If no database exists, use the "Database Setup" interface to:
   - Select an existing YAML file to migrate
   - Upload a configuration file for import

### 2. Using the Command Line Tool

#### Export Configuration

```bash
# Export to YAML
python tools/config_migration_tool.py --db sermon_config.db export --format yaml --output config_export.yaml

# Export to JSON
python tools/config_migration_tool.py --db sermon_config.db export --format json

# Export to environment file
python tools/config_migration_tool.py --db sermon_config.db export --format env --output .env
```

#### Import Configuration

```bash
# Import from JSON with overwrite
python tools/config_migration_tool.py --db sermon_config.db import new_config.json --format json --overwrite

# Import from YAML
python tools/config_migration_tool.py --db sermon_config.db import updated_config.yaml --format yaml
```

#### Database Status

```bash
# View database statistics and recent changes
python tools/config_migration_tool.py --db sermon_config.db status
```

### 3. Web Interface Usage

#### Configuration Editor

1. Navigate to "📝 Edit Configuration" tab
2. Select a configuration category (api, llm, audio, etc.)
3. Modify values using appropriate input widgets
4. Add change reason and save

#### Import/Export

1. Use "📥 Import/Export" tab for file operations
2. Import supports YAML and JSON formats
3. Export supports YAML, JSON, and environment file formats
4. Optional template saving for reuse

#### Configuration History

1. View complete audit trail in "📊 Configuration History" tab
2. Filter by specific configuration keys
3. Sensitive values (API keys, passwords) are automatically masked

#### Backup & Restore

1. Create backups in "💾 Backup & Restore" tab
2. List and manage existing backups
3. Verify backup integrity before restoration
4. Restore with automatic restoration point creation

## Configuration Categories

The system organizes configuration into logical categories:

### API Configuration (`api`)
- SermonAudio API credentials
- External service API keys
- Authentication tokens

### Language Model Configuration (`llm`)
- Primary, fallback, and validator LLM settings
- Provider configurations (OpenAI, Ollama, Anthropic, etc.)
- Model parameters and endpoints

### Audio Processing Configuration (`audio`)
- Enhancement methods and parameters
- Audacity integration settings
- Audio quality and normalization settings

### Database Configuration (`database`)
- Database connection settings
- Backup and maintenance parameters

### Embedding Configuration (`embeddings`)
- Vector embedding providers and models
- RAG system configuration

### System Configuration (`system`)
- Debug and logging settings
- Output directories and file management
- Default search criteria

### Web UI Configuration (`web_ui`)
- Interface preferences and limits
- Feature enablement flags

### Metadata Configuration (`metadata`)
- Description and hashtag processing rules
- Validation criteria and thresholds

## Advanced Features

### Multi-Environment Support

```python
# Create separate managers for different environments
production_config = SQLConfigManager("sermon_config.db", environment="production")
staging_config = SQLConfigManager("sermon_config.db", environment="staging")
dev_config = SQLConfigManager("sermon_config.db", environment="development")
```

### Programmatic Configuration Management

```python
from config_management import SQLConfigManager

# Initialize configuration manager
with SQLConfigManager("sermon_config.db") as config_manager:
    # Get configuration
    api_key = config_manager.get_config("api_key")
    llm_config = config_manager.get_config("llm")
    
    # Set configuration with audit trail
    config_manager.set_config(
        "llm.primary.model", 
        "llama3.2:latest", 
        "admin", 
        "Updated to latest model"
    )
    
    # Export current configuration
    yaml_config = config_manager.export_config("yaml")
```

### Backup Automation

```python
from config_management import ConfigBackupManager

# Automated backup with cleanup
backup_manager = ConfigBackupManager("sermon_config.db", "backups/")
backup_file = backup_manager.create_scheduled_backup(max_backups=10)
```

## Security Considerations

### Sensitive Data Handling
- API keys and passwords are automatically marked as secrets
- Sensitive values are masked in history and UI displays
- Backup files contain sensitive data and should be secured

### Access Control
- Database files should have appropriate file permissions
- Consider encryption for backup files containing sensitive data
- Audit trail tracks all changes with user attribution

## Best Practices

### Regular Backups
```bash
# Create daily backups via cron
0 2 * * * cd /path/to/sermon-processor && python tools/config_migration_tool.py --db sermon_config.db export --template "daily_$(date +%Y%m%d)"
```

### Change Management
1. Always provide meaningful change reasons
2. Test configuration changes in development environment first
3. Create backup before major changes
4. Use templates for consistent deployments

### Monitoring
- Monitor configuration history for unauthorized changes
- Set up alerts for critical configuration modifications
- Regular backup verification

## Migration Benefits

### Scalability
- **Multi-environment support**: Development, staging, production configurations
- **Team collaboration**: Multiple users can safely manage configuration
- **Change tracking**: Complete audit trail for compliance

### Reliability
- **Atomic updates**: All changes are transactional
- **Backup and restore**: Point-in-time recovery capabilities
- **Data validation**: Schema-enforced integrity

### Usability
- **Web interface**: User-friendly configuration management
- **Export flexibility**: Multiple output formats
- **Template system**: Reusable configurations

## Troubleshooting

### Common Issues

**Migration Fails**
```bash
# Check YAML file syntax
python -c "import yaml; yaml.safe_load(open('config.yaml'))"

# Enable debug logging
python tools/config_migration_tool.py --debug --db sermon_config.db migrate config.yaml
```

**Database Corruption**
```bash
# Verify database integrity
sqlite3 sermon_config.db "PRAGMA integrity_check;"

# Restore from backup
python tools/config_migration_tool.py --db sermon_config.db status
# Use backup restoration in web interface
```

**Import/Export Issues**
- Verify file format matches specified type
- Check file permissions and encoding
- Ensure all required fields are present

## Testing

Run the test suites to verify installation:

```bash
# Test migration system
python tests/test_sql_config_migration.py

# Test backup functionality
python tests/test_config_backup.py
```

Both test suites should report "All tests passed!"

## Support and Contributing

- Report issues on GitHub
- Submit feature requests for additional providers or functionality
- Contribute improvements to the configuration management system

The SQL configuration migration provides a robust foundation for managing complex sermon processing configurations at scale while maintaining backward compatibility with existing YAML-based setups.