#!/usr/bin/env python3
"""
Test script to verify cost tracking functionality by adding sample data.
"""

import sys
import os
from pathlib import Path
import datetime

# Add the UI directory to the path
ui_dir = Path(__file__).parent.parent / "ui"
sys.path.insert(0, str(ui_dir))

from database import get_db


def add_sample_llm_usage():
    """Add sample LLM usage data for testing cost tracking"""
    db = get_db()
    
    # Sample data for the last few days
    sample_data = [
        {
            'sermon_id': '101211913263888',
            'operation': 'description_generation',
            'provider': 'openai',
            'model': 'gpt-4o-mini',
            'input_tokens': 1250,
            'output_tokens': 150,
            'cost_usd': 0.045,
            'request_duration_ms': 2340,
            'status': 'success'
        },
        {
            'sermon_id': '101211917167796',
            'operation': 'hashtag_generation',
            'provider': 'openai',
            'model': 'gpt-4o-mini',
            'input_tokens': 800,
            'output_tokens': 80,
            'cost_usd': 0.028,
            'request_duration_ms': 1890,
            'status': 'success'
        },
        {
            'sermon_id': '101211921225193',
            'operation': 'description_generation',
            'provider': 'ollama',
            'model': 'llama3.1:8b',
            'input_tokens': 1100,
            'output_tokens': 200,
            'cost_usd': 0.0,
            'request_duration_ms': 4560,
            'status': 'success'
        },
        {
            'sermon_id': '10121198547284',
            'operation': 'hashtag_generation',
            'provider': 'openai',
            'model': 'gpt-4o-mini',
            'input_tokens': 750,
            'output_tokens': 90,
            'cost_usd': 0.025,
            'request_duration_ms': 1650,
            'status': 'success'
        },
        {
            'sermon_id': '101220207437943',
            'operation': 'description_generation',
            'provider': 'openai',
            'model': 'gpt-4o',
            'input_tokens': 1200,
            'output_tokens': 180,
            'cost_usd': 0.12,
            'request_duration_ms': 3240,
            'status': 'success'
        }
    ]
    
    print("Adding sample LLM usage data...")
    
    for data in sample_data:
        db.log_llm_api_usage(**data)
        
    print(f"Added {len(sample_data)} sample LLM usage records")
    
    # Test the summary functions
    print("\nTesting usage summary retrieval...")
    summary = db.get_llm_usage_summary(days=30)
    
    print(f"Summary: {summary['summary']}")
    print(f"Providers: {summary['providers']}")
    print(f"Models: {summary['models']}")
    print(f"Daily costs: {summary['daily_costs']}")
    
    print("\nTesting operations breakdown...")
    operations = db.get_llm_usage_by_operation(days=30)
    print(f"Operations: {operations}")
    
    print("\nCost tracking test completed successfully!")


if __name__ == "__main__":
    add_sample_llm_usage()
