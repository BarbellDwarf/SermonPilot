"""
Configuration Backup and Restore Manager for Sermon Audio Processor

Provides automated backup and restoration capabilities for SQL configuration.
"""

import sqlite3
import json
import gzip
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


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
        
        logger.info(f"Configuration backup created: {backup_file}")
        return backup_file
    
    def restore_backup(self, backup_file: Path, confirm: bool = False):
        """Restore configuration from backup."""
        if not confirm:
            raise ValueError("Backup restoration requires explicit confirmation")
        
        if not backup_file.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_file}")
        
        with gzip.open(backup_file, 'rt', encoding='utf-8') as f:
            backup_data = json.load(f)
        
        # Validate backup format
        if 'metadata' not in backup_data or 'data' not in backup_data:
            raise ValueError("Invalid backup file format")
        
        # Create restoration point before restore
        restoration_point = self.create_backup(f"pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
        try:
            self._restore_data(backup_data['data'])
            logger.info(f"Configuration restored from {backup_file}")
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
        tables = ['configuration_categories', 'configuration_keys', 'configuration_values', 
                 'configuration_history', 'configuration_exports']
        
        for table in tables:
            try:
                rows = cursor.execute(f"SELECT * FROM {table}").fetchall()
                data[table] = [dict(row) for row in rows]
            except sqlite3.OperationalError:
                # Table might not exist
                data[table] = []
        
        connection.close()
        return data
    
    def _restore_data(self, backup_data: Dict[str, Any]):
        """Restore data from backup."""
        connection = sqlite3.connect(self.db_path)
        cursor = connection.cursor()
        
        try:
            # Clear existing data in reverse dependency order
            for table in ['configuration_exports', 'configuration_history', 'configuration_values', 
                         'configuration_keys', 'configuration_categories']:
                try:
                    cursor.execute(f"DELETE FROM {table}")
                except sqlite3.OperationalError:
                    # Table might not exist
                    pass
            
            # Restore data in correct order (respecting foreign keys)
            restore_order = ['configuration_categories', 'configuration_keys', 'configuration_values', 
                           'configuration_history', 'configuration_exports']
            
            for table in restore_order:
                if table in backup_data and backup_data[table]:
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
                    'size': backup_file.stat().st_size,
                    'database_path': metadata.get('database_path', 'unknown')
                })
            except Exception:
                # Skip corrupted backup files
                logger.warning(f"Skipping corrupted backup file: {backup_file}")
                continue
        
        return sorted(backups, key=lambda x: x['created_at'], reverse=True)
    
    def delete_backup(self, backup_file: Path) -> bool:
        """Delete a backup file."""
        try:
            if backup_file.exists():
                backup_file.unlink()
                logger.info(f"Backup deleted: {backup_file}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete backup {backup_file}: {e}")
            return False
    
    def get_backup_info(self, backup_file: Path) -> Dict[str, Any]:
        """Get detailed information about a backup file."""
        if not backup_file.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_file}")
        
        try:
            with gzip.open(backup_file, 'rt', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            metadata = backup_data['metadata']
            data_stats = {}
            
            # Count records in each table
            for table, records in backup_data['data'].items():
                data_stats[table] = len(records)
            
            return {
                'metadata': metadata,
                'file_size': backup_file.stat().st_size,
                'data_stats': data_stats,
                'is_valid': True
            }
            
        except Exception as e:
            return {
                'metadata': {},
                'file_size': backup_file.stat().st_size if backup_file.exists() else 0,
                'data_stats': {},
                'is_valid': False,
                'error': str(e)
            }
    
    def create_scheduled_backup(self, max_backups: int = 10) -> Path:
        """Create a scheduled backup and clean up old ones."""
        # Create backup
        backup_file = self.create_backup()
        
        # Clean up old backups if we exceed the limit
        backups = self.list_backups()
        
        if len(backups) > max_backups:
            # Sort by creation date and remove oldest
            sorted_backups = sorted(backups, key=lambda x: x['created_at'])
            for old_backup in sorted_backups[:-max_backups]:
                self.delete_backup(old_backup['file'])
                logger.info(f"Cleaned up old backup: {old_backup['name']}")
        
        return backup_file
    
    def verify_backup(self, backup_file: Path) -> Dict[str, Any]:
        """Verify the integrity of a backup file."""
        verification_result = {
            'is_valid': False,
            'errors': [],
            'warnings': [],
            'metadata': {},
            'stats': {}
        }
        
        try:
            # Check file exists and is readable
            if not backup_file.exists():
                verification_result['errors'].append("Backup file does not exist")
                return verification_result
            
            # Load and validate backup data
            with gzip.open(backup_file, 'rt', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            # Check required sections
            required_sections = ['metadata', 'data']
            for section in required_sections:
                if section not in backup_data:
                    verification_result['errors'].append(f"Missing required section: {section}")
            
            if verification_result['errors']:
                return verification_result
            
            # Validate metadata
            metadata = backup_data['metadata']
            verification_result['metadata'] = metadata
            
            required_metadata = ['backup_name', 'created_at', 'backup_version']
            for field in required_metadata:
                if field not in metadata:
                    verification_result['warnings'].append(f"Missing metadata field: {field}")
            
            # Validate data structure
            data = backup_data['data']
            expected_tables = ['configuration_categories', 'configuration_keys', 'configuration_values']
            
            for table in expected_tables:
                if table not in data:
                    verification_result['warnings'].append(f"Missing table data: {table}")
                else:
                    verification_result['stats'][table] = len(data[table])
            
            # Check data integrity
            if 'configuration_categories' in data and 'configuration_keys' in data:
                categories = {cat['id']: cat for cat in data['configuration_categories']}
                orphaned_keys = []
                
                for key in data['configuration_keys']:
                    if key['category_id'] not in categories:
                        orphaned_keys.append(key['key_path'])
                
                if orphaned_keys:
                    verification_result['warnings'].append(f"Found {len(orphaned_keys)} orphaned keys")
            
            verification_result['is_valid'] = len(verification_result['errors']) == 0
            
        except Exception as e:
            verification_result['errors'].append(f"Failed to read backup file: {str(e)}")
        
        return verification_result