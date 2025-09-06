#!/usr/bin/env python3
"""
Test database update functionality to debug the T.title error
"""
import sys
from pathlib import Path

# Add paths relative to the project root
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "ui"))

def test_database_update():
    """Test the specific database update that's failing"""
    print("🧪 Testing Database Update Functionality")
    print("=" * 50)
    
    try:
        from database import get_db
        
        # Get the database connection
        db = get_db()
        
        # Test getting a sermon first
        print("📋 Getting test sermon...")
        with db.get_connection() as conn:
            sermon = conn.execute("SELECT * FROM sermons LIMIT 1").fetchone()
            if not sermon:
                print("❌ No sermons found in database")
                return False
                
            print(f"✅ Found sermon: {sermon['title']} (ID: {sermon['id']})")
            
            # Test the problematic update
            print(f"🔧 Testing update for sermon {sermon['id']}...")
            
            # Try the exact same update that's failing
            test_data = {
                'title': sermon['title'],
                'speaker': sermon['speaker'],
                'series_title': 'Test Series',  # This is what we're trying to update
                'scripture_reference': 'James 1:1-8',  # This is what we added in UI
                'event_type': sermon['event_type'],
                'description': sermon.get('description', ''),
                'church_name': sermon.get('church_name', '')
            }
            
            # Try the update
            conn.execute("""
                UPDATE sermons SET 
                    title = ?,
                    speaker = ?,
                    series_title = ?,
                    scripture_reference = ?,
                    event_type = ?,
                    description = ?,
                    church_name = ?,
                    updated_at = datetime('now')
                WHERE id = ?
            """, (
                test_data['title'],
                test_data['speaker'], 
                test_data['series_title'],
                test_data['scripture_reference'],
                test_data['event_type'],
                test_data['description'],
                test_data['church_name'],
                sermon['id']
            ))
            
            print("✅ Basic sermon update successful")
            
            # Now test the FTS update that might be causing the issue
            print("🔍 Testing FTS table update...")
            
            # Check what's in the FTS table
            fts_record = conn.execute("SELECT * FROM sermon_search WHERE sermon_id = ?", (sermon['id'],)).fetchone()
            if fts_record:
                print(f"✅ Found FTS record for sermon {sermon['id']}")
                
                # Try to update the FTS table
                conn.execute("""
                    INSERT OR REPLACE INTO sermon_search (
                        sermon_id, title, speaker, transcript_text, description, hashtags
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    sermon['id'],
                    test_data['title'],
                    test_data['speaker'],
                    fts_record.get('transcript_text', ''),
                    test_data['description'],
                    fts_record.get('hashtags', '')
                ))
                
                print("✅ FTS table update successful")
            else:
                print(f"⚠️  No FTS record found for sermon {sermon['id']}")
            
            # Test commit
            conn.commit()
            print("✅ Database commit successful")
            
            return True
            
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_fts_schema():
    """Test the FTS table schema specifically"""
    print("\n🔍 Testing FTS Table Schema")
    print("=" * 30)
    
    try:
        from database import get_db
        db = get_db()
        
        with db.get_connection() as conn:
            # Check FTS table structure
            fts_info = conn.execute("PRAGMA table_info(sermon_search)").fetchall()
            print("📋 FTS Table Columns:")
            for col in fts_info:
                print(f"   {col[1]} {col[2]}")
            
            # Try a simple FTS query to see if it works
            print("\n🧪 Testing FTS query...")
            result = conn.execute("SELECT COUNT(*) FROM sermon_search").fetchone()
            print(f"✅ FTS table has {result[0]} records")
            
            # Try the problematic query pattern that might be causing T.title error
            print("\n🧪 Testing potential problematic queries...")
            
            # This might be what's causing the issue - check if there are any views or triggers
            views = conn.execute("SELECT name FROM sqlite_master WHERE type='view'").fetchall()
            if views:
                print("📋 Views found:")
                for view in views:
                    print(f"   {view[0]}")
            else:
                print("✅ No views found")
                
            triggers = conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()
            if triggers:
                print("📋 Triggers found:")
                for trigger in triggers:
                    print(f"   {trigger[0]}")
            else:
                print("✅ No triggers found")
                
            return True
            
    except Exception as e:
        print(f"❌ FTS schema test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🧪 Database Update Debug Test")
    print("=" * 60)
    
    success1 = test_database_update()
    success2 = test_fts_schema()
    
    if success1 and success2:
        print("\n🎉 All database tests passed!")
        print("The T.title error must be happening elsewhere.")
        sys.exit(0)
    else:
        print("\n❌ Database tests failed!")
        print("Found the source of the T.title error.")
        sys.exit(1)
