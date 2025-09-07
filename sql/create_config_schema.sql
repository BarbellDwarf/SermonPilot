-- Configuration Database Schema
-- SQL-based configuration management for Sermon Audio Processor

-- Configuration Categories Table
-- Organizes configuration keys into logical groups
CREATE TABLE IF NOT EXISTS configuration_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Configuration Keys Table  
-- Defines the structure and metadata for each configuration option
CREATE TABLE IF NOT EXISTS configuration_keys (
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

-- Configuration Values Table
-- Stores the actual configuration values for different environments
CREATE TABLE IF NOT EXISTS configuration_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_id INTEGER REFERENCES configuration_keys(id),
    value TEXT,
    environment VARCHAR(50) DEFAULT 'production', -- production, staging, development
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    UNIQUE(key_id, environment)
);

-- Configuration History Table
-- Maintains audit trail of all configuration changes
CREATE TABLE IF NOT EXISTS configuration_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_id INTEGER REFERENCES configuration_keys(id),
    old_value TEXT,
    new_value TEXT,
    environment VARCHAR(50),
    changed_by VARCHAR(100),
    change_reason TEXT,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Configuration Exports Table
-- Tracks exported configuration templates and downloads
CREATE TABLE IF NOT EXISTS configuration_exports (
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

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_config_keys_category ON configuration_keys(category_id);
CREATE INDEX IF NOT EXISTS idx_config_keys_path ON configuration_keys(key_path);
CREATE INDEX IF NOT EXISTS idx_config_values_key_env ON configuration_values(key_id, environment);
CREATE INDEX IF NOT EXISTS idx_config_history_key ON configuration_history(key_id);
CREATE INDEX IF NOT EXISTS idx_config_history_changed_at ON configuration_history(changed_at);
CREATE INDEX IF NOT EXISTS idx_config_exports_template ON configuration_exports(is_template);

-- Triggers to update timestamps
CREATE TRIGGER IF NOT EXISTS update_category_timestamp 
    AFTER UPDATE ON configuration_categories
    BEGIN
        UPDATE configuration_categories 
        SET updated_at = CURRENT_TIMESTAMP 
        WHERE id = NEW.id;
    END;