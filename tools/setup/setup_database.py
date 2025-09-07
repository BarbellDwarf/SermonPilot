#!/usr/bin/env python3
"""
Database Setup and Verification Script

Ensures all database tables and components are properly configured for the 
SermonAudio processor system.
"""

import logging
import sqlite3
import sys
from pathlib import Path
import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseSetup:
    """Database setup and verification manager"""
    
    def __init__(self, db_path: str = "sermon_processor.db"):
        self.db_path = db_path
        self.required_tables = {
            'sermons': [
                'sermon_id TEXT PRIMARY KEY',
                'title TEXT',
                'speaker TEXT',
                'series TEXT',
                'published_date TIMESTAMP',
                'description TEXT',
                'duration_seconds INTEGER',
                'file_size_bytes INTEGER',
                'created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
                'updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
            ],
            'processing_info': [
                'sermon_id TEXT PRIMARY KEY',
                'enhancement_method TEXT',
                'noise_reduction_applied BOOLEAN',
                'normalization_applied BOOLEAN',
                'qa_normalization_applied BOOLEAN',
                'qa_segments_count INTEGER',
                'processing_duration REAL',
                'quality_score REAL',
                'processing_logs TEXT',
                'processed_at TIMESTAMP',
                'FOREIGN KEY (sermon_id) REFERENCES sermons (sermon_id)'
            ],
            'validation_results': [
                'sermon_id TEXT PRIMARY KEY',
                'is_valid BOOLEAN',
                'score REAL',
                'reason TEXT',
                'criteria_met TEXT',
                'criteria_failed TEXT',
                'validated_at TIMESTAMP',
                'FOREIGN KEY (sermon_id) REFERENCES sermons (sermon_id)'
            ],
            'background_jobs': [
                'id TEXT PRIMARY KEY',
                'type TEXT',
                'title TEXT',
                'description TEXT',
                'status TEXT',
                'progress REAL',
                'parameters TEXT',
                'result TEXT',
                'logs TEXT',
                'created_at TIMESTAMP',
                'started_at TIMESTAMP',
                'completed_at TIMESTAMP',
                'can_cancel BOOLEAN',
                'can_retry BOOLEAN',
                'priority INTEGER'
            ],
            'llm_api_usage': [
                'id INTEGER PRIMARY KEY AUTOINCREMENT',
                'provider TEXT',
                'model TEXT',
                'endpoint TEXT',
                'input_tokens INTEGER',
                'output_tokens INTEGER',
                'cost REAL',
                'request_timestamp TIMESTAMP',
                'response_time_ms INTEGER',
                'sermon_id TEXT',
                'operation_type TEXT'
            ]
        }
        
    def run_setup(self) -> bool:
        """Run complete database setup and verification"""
        logger.info("🔧 Starting database setup and verification...")
        
        try:
            # Create database connection
            self._verify_database_connection()
            
            # Create or verify tables
            self._setup_tables()
            
            # Verify table structures
            self._verify_table_structures()
            
            # Run basic integrity checks
            self._run_integrity_checks()
            
            # Setup indexes for performance
            self._setup_indexes()
            
            logger.info("✅ Database setup completed successfully!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Database setup failed: {e}")
            return False
    
    def _verify_database_connection(self):
        """Verify database connection works"""
        logger.info("📡 Verifying database connection...")
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            conn.close()
            logger.info("✅ Database connection verified")
        except Exception as e:
            raise RuntimeError(f"Database connection failed: {e}")
    
    def _setup_tables(self):
        """Create or verify all required tables"""
        logger.info("🏗️  Setting up database tables...")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for table_name, columns in self.required_tables.items():
            try:
                # Check if table exists
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name=?
                """, (table_name,))
                
                if cursor.fetchone():
                    logger.info(f"  ✓ Table '{table_name}' exists")
                else:
                    # Create table
                    columns_sql = ',\n    '.join(columns)
                    create_sql = f"""
                    CREATE TABLE {table_name} (
                        {columns_sql}
                    )
                    """
                    cursor.execute(create_sql)
                    logger.info(f"  ✨ Created table '{table_name}'")
                    
            except Exception as e:
                logger.error(f"  ❌ Failed to setup table '{table_name}': {e}")
                raise
        
        conn.commit()
        conn.close()
    
    def _verify_table_structures(self):
        """Verify all tables have the expected structure"""
        logger.info("🔍 Verifying table structures...")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for table_name in self.required_tables.keys():
            try:
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()
                
                if columns:
                    logger.info(f"  ✓ Table '{table_name}' has {len(columns)} columns")
                else:
                    logger.warning(f"  ⚠️  Table '{table_name}' appears to be empty or missing")
                    
            except Exception as e:
                logger.error(f"  ❌ Failed to verify table '{table_name}': {e}")
        
        conn.close()
    
    def _run_integrity_checks(self):
        """Run basic database integrity checks"""
        logger.info("🔒 Running integrity checks...")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Check foreign key constraints
            cursor.execute("PRAGMA foreign_key_check")
            fk_violations = cursor.fetchall()
            
            if fk_violations:
                logger.warning(f"  ⚠️  Found {len(fk_violations)} foreign key violations")
                for violation in fk_violations:
                    logger.warning(f"    - {violation}")
            else:
                logger.info("  ✓ No foreign key violations found")
            
            # Check database integrity
            cursor.execute("PRAGMA integrity_check")
            integrity_result = cursor.fetchone()[0]
            
            if integrity_result == "ok":
                logger.info("  ✓ Database integrity check passed")
            else:
                logger.warning(f"  ⚠️  Database integrity issue: {integrity_result}")
                
        except Exception as e:
            logger.error(f"  ❌ Integrity check failed: {e}")
        finally:
            conn.close()
    
    def _setup_indexes(self):
        """Create performance indexes"""
        logger.info("⚡ Setting up performance indexes...")
        
        indexes = [
            ("idx_sermons_speaker", "sermons", "speaker"),
            ("idx_sermons_published", "sermons", "published_date"),
            ("idx_processing_processed_at", "processing_info", "processed_at"),
            ("idx_validation_validated_at", "validation_results", "validated_at"),
            ("idx_jobs_status", "background_jobs", "status"),
            ("idx_jobs_created", "background_jobs", "created_at"),
            ("idx_llm_usage_timestamp", "llm_api_usage", "request_timestamp"),
            ("idx_llm_usage_provider", "llm_api_usage", "provider")
        ]
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for index_name, table_name, column_name in indexes:
            try:
                cursor.execute(f"""
                    CREATE INDEX IF NOT EXISTS {index_name} 
                    ON {table_name} ({column_name})
                """)
                logger.info(f"  ✓ Index '{index_name}' created/verified")
            except Exception as e:
                logger.warning(f"  ⚠️  Failed to create index '{index_name}': {e}")
        
        conn.commit()
        conn.close()
    
    def get_database_status(self) -> dict:
        """Get current database status and statistics"""
        logger.info("📊 Gathering database statistics...")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        stats = {
            'database_file': self.db_path,
            'file_exists': Path(self.db_path).exists(),
            'file_size_mb': 0,
            'tables': {},
            'total_records': 0
        }
        
        try:
            if stats['file_exists']:
                stats['file_size_mb'] = round(Path(self.db_path).stat().st_size / 1024 / 1024, 2)
            
            # Get table statistics
            for table_name in self.required_tables.keys():
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    count = cursor.fetchone()[0]
                    stats['tables'][table_name] = count
                    stats['total_records'] += count
                except Exception:
                    stats['tables'][table_name] = 'Error'
            
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
        finally:
            conn.close()
        
        return stats


def main():
    """Main setup script entry point"""
    print("🔧 SermonAudio Database Setup & Verification")
    print("=" * 50)
    
    # Check if config exists
    config_path = "config.yaml"
    if not Path(config_path).exists():
        print(f"❌ Configuration file not found: {config_path}")
        print("Please create config.yaml before running database setup.")
        sys.exit(1)
    
    # Load configuration
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        print(f"✅ Configuration loaded from {config_path}")
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}")
        sys.exit(1)
    
    # Initialize database setup
    db_path = "sermon_processor.db"
    setup = DatabaseSetup(db_path)
    
    # Run setup
    success = setup.run_setup()
    
    if success:
        # Show database status
        print("\n📊 Database Status:")
        print("-" * 30)
        stats = setup.get_database_status()
        
        print(f"Database file: {stats['database_file']}")
        print(f"File size: {stats['file_size_mb']} MB")
        print(f"Total records: {stats['total_records']}")
        
        print("\nTable Statistics:")
        for table_name, count in stats['tables'].items():
            print(f"  {table_name}: {count} records")
        
        print("\n✅ Database setup completed successfully!")
        print("\n💡 Next steps:")
        print("  1. Run the SermonAudio processor to populate data")
        print("  2. Use the analytics interface to view insights")
        print("  3. Configure embedding providers for RAG features")
        
        sys.exit(0)
    else:
        print("\n❌ Database setup failed. Please check the logs above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
