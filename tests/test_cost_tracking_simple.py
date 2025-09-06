#!/usr/bin/env python3
"""
Simple test script to add sample LLM usage data and verify cost tracking.
"""

import sys
import sqlite3
from pathlib import Path
import datetime

# Add the UI directory to the path
project_root = Path(__file__).parent.parent
ui_dir = project_root / "ui"

def test_cost_tracking():
    """Test cost tracking by adding sample data directly to the database"""
    
    # Find the database file
    db_path = project_root / "sermon_processor.db"
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return
    
    print(f"Using database at: {db_path}")
    
    # Connect to the database
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Check if the llm_api_usage table exists
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='llm_api_usage'
    """)
    
    if not cursor.fetchone():
        print("Creating llm_api_usage table...")
        cursor.execute("""
            CREATE TABLE llm_api_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                sermon_id TEXT,
                operation TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0.0,
                request_duration_ms INTEGER DEFAULT 0,
                status TEXT DEFAULT 'success',
                error_message TEXT,
                request_data TEXT,
                response_data TEXT
            )
        """)
        
        # Add indices for performance
        cursor.execute("CREATE INDEX idx_llm_usage_timestamp ON llm_api_usage(timestamp)")
        cursor.execute("CREATE INDEX idx_llm_usage_provider ON llm_api_usage(provider)")
        cursor.execute("CREATE INDEX idx_llm_usage_operation ON llm_api_usage(operation)")
        cursor.execute("CREATE INDEX idx_llm_usage_sermon_id ON llm_api_usage(sermon_id)")
        
        conn.commit()
    
    # Add sample data
    sample_data = [
        ('101211913263888', 'description_generation', 'openai', 'gpt-4o-mini', 1250, 150, 1400, 0.045, 2340, 'success'),
        ('101211917167796', 'hashtag_generation', 'openai', 'gpt-4o-mini', 800, 80, 880, 0.028, 1890, 'success'),
        ('101211921225193', 'description_generation', 'ollama', 'llama3.1:8b', 1100, 200, 1300, 0.0, 4560, 'success'),
        ('10121198547284', 'hashtag_generation', 'openai', 'gpt-4o-mini', 750, 90, 840, 0.025, 1650, 'success'),
        ('101220207437943', 'description_generation', 'openai', 'gpt-4o', 1200, 180, 1380, 0.12, 3240, 'success'),
        ('10123173825772', 'description_generation', 'openai', 'gpt-4o-mini', 1150, 140, 1290, 0.041, 2180, 'success'),
        ('1013241529447510', 'hashtag_generation', 'ollama', 'llama3.1:8b', 720, 85, 805, 0.0, 3890, 'success'),
        ('101324153106359', 'description_generation', 'openai', 'gpt-4o', 1300, 195, 1495, 0.135, 3560, 'success'),
    ]
    
    print("Adding sample LLM usage data...")
    
    for data in sample_data:
        cursor.execute("""
            INSERT INTO llm_api_usage (
                sermon_id, operation, provider, model, 
                input_tokens, output_tokens, total_tokens, cost_usd,
                request_duration_ms, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, data)
    
    conn.commit()
    print(f"Added {len(sample_data)} sample records")
    
    # Test queries
    print("\nTesting summary queries...")
    
    # Total usage
    cursor.execute("""
        SELECT 
            COUNT(*) as total_calls,
            SUM(input_tokens) as total_input_tokens,
            SUM(output_tokens) as total_output_tokens,
            SUM(total_tokens) as total_tokens,
            SUM(cost_usd) as total_cost,
            AVG(cost_usd) as avg_cost_per_call,
            AVG(request_duration_ms) as avg_duration_ms
        FROM llm_api_usage
    """)
    
    summary = cursor.fetchone()
    print(f"Total summary: {summary}")
    
    # Provider breakdown
    cursor.execute("""
        SELECT 
            provider,
            COUNT(*) as calls,
            SUM(total_tokens) as tokens,
            SUM(cost_usd) as cost
        FROM llm_api_usage
        GROUP BY provider
        ORDER BY cost DESC
    """)
    
    providers = cursor.fetchall()
    print(f"Provider breakdown: {providers}")
    
    # Operation breakdown
    cursor.execute("""
        SELECT 
            operation,
            COUNT(*) as calls,
            SUM(total_tokens) as tokens,
            SUM(cost_usd) as cost
        FROM llm_api_usage
        GROUP BY operation
        ORDER BY cost DESC
    """)
    
    operations = cursor.fetchall()
    print(f"Operation breakdown: {operations}")
    
    conn.close()
    print("\nCost tracking test completed successfully!")
    print("\nYou can now view the cost tracking data in the Streamlit UI!")


if __name__ == "__main__":
    test_cost_tracking()
