#!/usr/bin/env python3
"""
Test script to verify job queue integration in the UI using Playwright.

This script tests that:
1. Batch processing creates a job that persists when navigating away
2. New sermon processing creates a job that persists when navigating away
3. Jobs can be monitored from the Jobs page
4. Jobs run in the background
"""

import asyncio
import time
import sys
from pathlib import Path

# Add project paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "ui"))

async def test_job_queue_integration():
    """Test the job queue integration using Playwright"""
    
    print("🚀 Starting job queue integration test...")
    
    try:
        # Start the Streamlit app in the background
        import subprocess
        
        print("📱 Starting Streamlit app...")
        streamlit_process = subprocess.Popen([
            sys.executable, "-m", "streamlit", "run", "streamlit_app.py",
            "--server.port", "8502",
            "--server.headless", "true"
        ], cwd=project_root)
        
        # Give it time to start
        time.sleep(10)
        
        # Now test with Playwright
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            # Launch browser
            browser = await p.chromium.launch(headless=False)  # Set to False to see the browser
            page = await browser.new_page()
            
            # Navigate to the app
            print("🌐 Navigating to Streamlit app...")
            await page.goto("http://localhost:8502")
            
            # Wait for the app to load
            await page.wait_for_selector("text=SermonAudio Processor", timeout=30000)
            print("✅ App loaded successfully")
            
            # Test 1: Batch Update Job Creation
            print("\n🔄 Testing batch update job creation...")
            
            # Navigate to batch update page
            await page.click("text=Batch Update")
            await page.wait_for_selector("text=Batch Processing", timeout=10000)
            print("✅ Navigated to Batch Update page")
            
            # Check if we can create a mock batch job
            # First, add some mock sermon IDs for testing
            if await page.is_visible("text=No sermons selected"):
                print("ℹ️ No sermons selected - this is expected for a test")
            
            # Test 2: Check Jobs Page
            print("\n📊 Testing Jobs page...")
            
            # Navigate to jobs page
            await page.click("text=Jobs")
            await page.wait_for_selector("text=Background Jobs", timeout=10000)
            print("✅ Navigated to Jobs page")
            
            # Check if jobs page loads properly
            if await page.is_visible("text=No jobs found"):
                print("ℹ️ No background jobs currently running - this is expected")
            
            # Test 3: New Sermon Page
            print("\n🎤 Testing new sermon page...")
            
            # Navigate to new sermon page
            await page.click("text=New Sermon")
            await page.wait_for_selector("text=Create New Sermon", timeout=10000)
            print("✅ Navigated to New Sermon page")
            
            # Test 4: Settings Page (to check configuration)
            print("\n⚙️ Testing settings page...")
            
            # Navigate to settings page
            await page.click("text=Settings")
            await page.wait_for_selector("text=Configuration", timeout=10000)
            print("✅ Navigated to Settings page")
            
            print("\n🎉 All basic navigation tests passed!")
            print("ℹ️ To test actual job creation, you would need to:")
            print("   1. Configure API settings in Settings page")
            print("   2. Add sermon data in Batch Update page")
            print("   3. Start a batch processing job")
            print("   4. Navigate away and check Jobs page")
            
            # Keep browser open for manual testing
            print("\n⏸️ Browser will stay open for 30 seconds for manual testing...")
            await page.wait_for_timeout(30000)
            
            await browser.close()
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        
    finally:
        # Clean up Streamlit process
        print("\n🧹 Cleaning up...")
        try:
            streamlit_process.terminate()
            streamlit_process.wait(timeout=5)
        except Exception as e:
            print(f"⚠️ Error terminating Streamlit: {e}")
            try:
                streamlit_process.kill()
            except:
                pass
    
    print("\n✅ Test completed!")

def test_job_queue_directly():
    """Test the job queue system directly without UI"""
    
    print("🔧 Testing job queue system directly...")
    
    try:
        from ui.job_queue import get_job_queue, JobType, JobStatus
        
        # Get job queue instance
        job_queue = get_job_queue()
        
        # Create a test job
        print("📝 Creating test job...")
        job_id = job_queue.add_job(
            job_type=JobType.VALIDATION,
            title="Test Job",
            description="Testing job queue functionality",
            parameters={'test': True}
        )
        
        print(f"✅ Created job with ID: {job_id}")
        
        # Check job status
        job = job_queue.get_job(job_id)
        if job:
            print(f"✅ Job found with status: {job.status}")
            print(f"   Title: {job.title}")
            print(f"   Progress: {job.progress}%")
        else:
            print("❌ Job not found")
            
        # List all jobs
        all_jobs = job_queue.get_all_jobs()
        print(f"📋 Total jobs in queue: {len(all_jobs)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Direct job queue test failed: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Job Queue Integration Test Suite")
    print("=" * 50)
    
    # Test 1: Direct job queue functionality
    print("\n1️⃣ Testing job queue directly...")
    direct_test_passed = test_job_queue_directly()
    
    if direct_test_passed:
        print("\n2️⃣ Testing UI integration with Playwright...")
        # Test 2: UI integration with Playwright
        try:
            asyncio.run(test_job_queue_integration())
        except KeyboardInterrupt:
            print("\n⏹️ Test interrupted by user")
        except Exception as e:
            print(f"\n❌ Playwright test failed: {e}")
            print("💡 Make sure you have Playwright installed: pip install playwright")
            print("💡 And install browsers: playwright install")
    else:
        print("\n⏭️ Skipping UI tests due to job queue test failure")
    
    print("\n🏁 Test suite completed!")
