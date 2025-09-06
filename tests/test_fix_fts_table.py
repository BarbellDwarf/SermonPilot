#!/usr/bin/env python3
"""
Fix the corrupted FTS table that's causing the T.title error
"""
import sys
from pathlib import Path

# Add paths relative to the project root
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "ui"))

def fix_fts_table():
    """Fix the corrupted FTS table"""
    print("🔧 Fixing Corrupted FTS Table")
    print("=" * 40)
    
    try:
        from database import get_db
        db = get_db()
        
        with db.get_connection() as conn:
            print("🗑️  Dropping corrupted FTS table...")
            
            # Drop the corrupted FTS table and all its related tables
            fts_tables = [
                'sermon_search',
                'sermon_search_data', 
                'sermon_search_idx',
                'sermon_search_docsize',
                'sermon_search_config'
            ]
            
            for table in fts_tables:
                try:
                    conn.execute(f"DROP TABLE IF EXISTS {table}")
                    print(f"   ✅ Dropped {table}")
                except Exception as e:
                    print(f"   ⚠️  Could not drop {table}: {e}")
            
            print("\n🏗️  Creating new FTS table...")
            
            # Create a new FTS table with the correct schema
            conn.execute("""
                CREATE VIRTUAL TABLE sermon_search USING fts5(
                    sermon_id UNINDEXED,
                    title,
                    speaker,
                    transcript_text,
                    description,
                    hashtags
                )
            """)
            
            print("✅ Created new FTS table")
            
            print("\n📝 Populating FTS table with existing sermon data...")
            
            # Get all sermons and populate the FTS table
            sermons = conn.execute("""
                SELECT s.id, s.title, s.speaker, s.description,
                       COALESCE(sc.transcript_text, '') as transcript_text,
                       COALESCE(sc.hashtags, '') as hashtags
                FROM sermons s
                LEFT JOIN sermon_content sc ON s.id = sc.sermon_id
            """).fetchall()
            
            for sermon in sermons:
                conn.execute("""
                    INSERT INTO sermon_search (
                        sermon_id, title, speaker, transcript_text, description, hashtags
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    sermon['id'],
                    sermon['title'] or '',
                    sermon['speaker'] or '',
                    sermon['transcript_text'] or '',
                    sermon['description'] or '',
                    sermon['hashtags'] or ''
                ))
            
            print(f"✅ Populated FTS table with {len(sermons)} sermons")
            
            # Test the FTS table
            print("\n🧪 Testing fixed FTS table...")
            count = conn.execute("SELECT COUNT(*) FROM sermon_search").fetchone()[0]
            print(f"✅ FTS table working with {count} records")
            
            # Commit the changes
            conn.commit()
            print("✅ Changes committed")
            
            return True
            
    except Exception as e:
        print(f"❌ FTS fix failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_update_after_fix():
    """Test that sermon updates work after fixing FTS"""
    print("\n🧪 Testing Sermon Update After FTS Fix")
    print("=" * 45)
    
    try:
        from database import get_db
        db = get_db()
        
        with db.get_connection() as conn:
            # Get a test sermon
            sermon = conn.execute("SELECT * FROM sermons LIMIT 1").fetchone()
            print(f"📋 Testing update for sermon: {sermon['title']}")
            
            # Try the update that was failing
            conn.execute("""
                UPDATE sermons SET 
                    scripture_reference = ?,
                    updated_at = datetime('now')
                WHERE id = ?
            """, ('James 1:1-8', sermon['id']))
            
            print("✅ Sermon update successful")
            
            # Update the FTS table
            conn.execute("""
                INSERT OR REPLACE INTO sermon_search (
                    sermon_id, title, speaker, transcript_text, description, hashtags
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                sermon['id'],
                sermon['title'] or '',
                sermon['speaker'] or '',
                '',  # transcript_text
                sermon['description'] or '',
                ''   # hashtags
            ))
            
            print("✅ FTS update successful")
            
            conn.commit()
            print("✅ Update committed successfully")
            
            return True
            
    except Exception as e:
        print(f"❌ Update test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🔧 FTS Table Repair Script")
    print("=" * 50)
    
    success1 = fix_fts_table()
    if success1:
        success2 = test_update_after_fix()
        
        if success2:
            print("\n🎉 FTS table fixed successfully!")
            print("The T.title error should now be resolved.")
            sys.exit(0)
        else:
            print("\n❌ FTS table fixed but updates still failing!")
            sys.exit(1)
    else:
        print("\n❌ Could not fix FTS table!")
        sys.exit(1)
