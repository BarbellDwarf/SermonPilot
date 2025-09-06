#!/usr/bin/env python3
"""
Script to run real validation on recent sermons to generate actual LLM cost tracking data.
"""

import sys
import sqlite3
from pathlib import Path
import datetime
import yaml

# Add the project paths
project_root = Path(__file__).parent.parent
ui_dir = project_root / "ui"
src_dir = project_root / "src"
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(ui_dir))

def load_config():
    """Load configuration from config.yaml"""
    config_path = project_root / "config.yaml"
    if not config_path.exists():
        print(f"Config file not found at {config_path}")
        return None
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def get_recent_sermons():
    """Get sermons from the database that have been processed recently"""
    db_path = project_root / "sermon_processor.db"
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return []
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Get sermons that have descriptions/hashtags (indicating they've been processed)
    cursor.execute("""
        SELECT sermon_id, title, description, hashtags, created_at
        FROM sermons 
        WHERE (description IS NOT NULL AND description != '') 
           OR (hashtags IS NOT NULL AND hashtags != '')
        ORDER BY created_at DESC 
        LIMIT 10
    """)
    
    sermons = []
    for row in cursor.fetchall():
        sermons.append({
            'sermon_id': row[0],
            'title': row[1],
            'description': row[2],
            'hashtags': row[3],
            'created_at': row[4]
        })
    
    conn.close()
    return sermons

def run_validation_on_sermon(sermon, config):
    """Run validation on a specific sermon to generate real LLM usage"""
    try:
        from llm_manager import LLMManager
        from description_validator import DescriptionValidator
        
        print(f"Running validation on sermon: {sermon['title'][:50]}...")
        
        # Initialize LLM manager with cost tracking
        llm_manager = LLMManager(config)
        
        # Create validator with LLM manager
        validator = DescriptionValidator()
        validator.llm_manager = llm_manager  # Override with our configured LLM manager
        
        # Validate description if it exists
        if sermon['description']:
            print("  Validating description...")
            try:
                context = {
                    'title': sermon['title'],
                    'speaker': sermon.get('speaker', 'Unknown')
                }
                is_valid, reason, score, criteria_met, criteria_failed = validator.validate_description(
                    sermon['description'],
                    context=context,
                    sermon_id=sermon['sermon_id']  # Pass sermon_id for cost tracking
                )
                print(f"  Description validation: {'✓' if is_valid else '✗'} - {reason}")
            except Exception as e:
                print(f"  Description validation failed: {e}")
        
        # Validate hashtags if they exist
        if sermon['hashtags']:
            print("  Validating hashtags...")
            try:
                context = {
                    'title': sermon['title'],
                    'speaker': sermon.get('speaker', 'Unknown')
                }
                is_valid, reason = validator.validate_hashtags(
                    sermon['hashtags'],
                    context=context,
                    sermon_id=sermon['sermon_id']  # Pass sermon_id for cost tracking
                )
                print(f"  Hashtags validation: {'✓' if is_valid else '✗'} - {reason}")
            except Exception as e:
                print(f"  Hashtags validation failed: {e}")
        
        print(f"  ✓ Completed validation for sermon {sermon['sermon_id']}")
        return True
        
    except Exception as e:
        print(f"  ✗ Error validating sermon {sermon['sermon_id']}: {e}")
        return False

def generate_new_content_for_sermon(sermon, config):
    """Generate new description/hashtags for a sermon to create LLM usage"""
    try:
        from llm_manager import LLMManager
        
        print(f"Generating content for sermon: {sermon['title'][:50]}...")
        
        # Initialize LLM manager with cost tracking
        llm_manager = LLMManager(config)
        
        # Generate description if missing or short
        if not sermon['description'] or len(sermon['description']) < 50:
            print(f"  Generating description...")
            try:
                description_prompt = [
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that creates engaging sermon descriptions."
                    },
                    {
                        "role": "user", 
                        "content": f"Create a compelling 2-3 sentence description for this sermon: '{sermon['title']}'"
                    }
                ]
                
                description = llm_manager.chat(
                    description_prompt,
                    operation="description_generation",
                    sermon_id=sermon['sermon_id']
                )
                print(f"  ✓ Generated description: {description[:100]}...")
            except Exception as e:
                print(f"  ✗ Description generation failed: {e}")
        
        # Generate hashtags if missing
        if not sermon['hashtags']:
            print(f"  Generating hashtags...")
            try:
                hashtag_prompt = [
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that creates relevant hashtags for sermons."
                    },
                    {
                        "role": "user",
                        "content": f"Create 5-7 relevant hashtags for this sermon: '{sermon['title']}'. Return only the hashtags separated by commas."
                    }
                ]
                
                hashtags = llm_manager.chat(
                    hashtag_prompt,
                    operation="hashtag_generation", 
                    sermon_id=sermon['sermon_id']
                )
                print(f"  ✓ Generated hashtags: {hashtags}")
            except Exception as e:
                print(f"  ✗ Hashtag generation failed: {e}")
        
        print(f"  ✓ Completed content generation for sermon {sermon['sermon_id']}")
        return True
        
    except Exception as e:
        print(f"  ✗ Error generating content for sermon {sermon['sermon_id']}: {e}")
        return False

def main():
    """Main function to run real validation and content generation"""
    print("🎯 Running Real LLM Validation to Generate Cost Tracking Data")
    print("=" * 60)
    
    # Load configuration
    print("Loading configuration...")
    config = load_config()
    if not config:
        print("❌ Failed to load configuration")
        return
    
    # Get recent sermons
    print("Finding recent sermons...")
    sermons = get_recent_sermons()
    if not sermons:
        print("❌ No processed sermons found in database")
        return
    
    print(f"Found {len(sermons)} processed sermons")
    
    # Run validation and content generation on sermons
    successful_operations = 0
    total_operations = 0
    
    for i, sermon in enumerate(sermons[:5], 1):  # Limit to 5 sermons to avoid excessive API calls
        print(f"\n--- Processing Sermon {i}/{min(5, len(sermons))} ---")
        
        # Run validation
        total_operations += 1
        if run_validation_on_sermon(sermon, config):
            successful_operations += 1
        
        # Generate new content (this will create more LLM API calls)
        total_operations += 1
        if generate_new_content_for_sermon(sermon, config):
            successful_operations += 1
    
    print(f"\n🎉 Completed Real LLM Operations!")
    print(f"   Successful operations: {successful_operations}/{total_operations}")
    print(f"   Real cost tracking data has been generated!")
    print(f"\n💰 You can now view real cost tracking data in the Analytics dashboard!")

if __name__ == "__main__":
    main()
