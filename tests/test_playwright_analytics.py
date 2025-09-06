#!/usr/bin/env python3
"""
Playwright test to verify analytics functionality for validated/interacted sermons.
This tests the UI to ensure the enhanced analytics logic displays correctly.
"""

import asyncio
import sys
import time
from pathlib import Path
from playwright.async_api import async_playwright

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

async def test_analytics_ui():
    """Test analytics UI functionality with Playwright."""
    
    print("=" * 60)
    print("PLAYWRIGHT TEST: ANALYTICS UI FOR VALIDATED SERMONS")
    print("=" * 60)
    
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=False)  # Set to True for headless
        page = await browser.new_page()
        
        try:
            # Navigate to Streamlit app
            print("🚀 Starting Streamlit app...")
            
            # Start Streamlit in background (if not already running)
            import subprocess
            import threading
            
            def start_streamlit():
                subprocess.run([
                    sys.executable, "-m", "streamlit", "run", 
                    "ui/streamlit_app.py", 
                    "--server.port=8501",
                    "--server.headless=true"
                ], cwd=Path.cwd())
            
            # Start Streamlit in a separate thread
            streamlit_thread = threading.Thread(target=start_streamlit, daemon=True)
            streamlit_thread.start()
            
            # Wait for Streamlit to start
            print("⏳ Waiting for Streamlit to start...")
            await asyncio.sleep(10)
            
            # Navigate to the app
            print("🌐 Navigating to Streamlit app...")
            await page.goto("http://localhost:8501")
            
            # Wait for page to load
            await page.wait_for_timeout(5000)
            
            # Take screenshot of initial page
            await page.screenshot(path="tests/screenshots/streamlit_home.png")
            print("📸 Screenshot saved: streamlit_home.png")
            
            # Check if we're on the main page
            page_title = await page.title()
            print(f"📄 Page title: {page_title}")
            
            # Look for navigation elements
            print("🔍 Checking navigation...")
            
            # Try to find Analytics link/button
            analytics_links = await page.locator("text=Analytics").all()
            if analytics_links:
                print(f"✅ Found {len(analytics_links)} Analytics navigation elements")
                
                # Click on Analytics
                print("🖱️ Clicking on Analytics...")
                await analytics_links[0].click()
                
                # Wait for analytics page to load
                await page.wait_for_timeout(3000)
                
                # Take screenshot of analytics page
                await page.screenshot(path="tests/screenshots/analytics_page.png")
                print("📸 Screenshot saved: analytics_page.png")
                
                # Check for analytics content
                print("🔍 Checking analytics page content...")
                
                # Look for key analytics elements
                elements_to_check = [
                    "Processing Metrics",
                    "Content Analysis", 
                    "Cost Tracking",
                    "Performance"
                ]
                
                found_elements = []
                for element in elements_to_check:
                    elements = await page.locator(f"text={element}").all()
                    if elements:
                        found_elements.append(element)
                        print(f"✅ Found: {element}")
                    else:
                        print(f"❌ Missing: {element}")
                
                # Check for content analysis specifically
                print("\n🔍 Looking for Content Analysis tab...")
                content_analysis_tabs = await page.locator("text=Content Analysis").all()
                if content_analysis_tabs:
                    print("🖱️ Clicking on Content Analysis tab...")
                    await content_analysis_tabs[0].click()
                    await page.wait_for_timeout(3000)
                    
                    # Look for validated sermon data
                    print("🔍 Checking for validated sermon analytics...")
                    
                    # Look for indicators that analytics are being pulled
                    analytics_indicators = [
                        "validated",
                        "processed", 
                        "sermons",
                        "analytics",
                        "speaker",
                        "quality"
                    ]
                    
                    page_content = await page.content()
                    found_indicators = []
                    for indicator in analytics_indicators:
                        if indicator.lower() in page_content.lower():
                            found_indicators.append(indicator)
                    
                    print(f"📊 Found analytics indicators: {found_indicators}")
                    
                    # Take screenshot of content analysis
                    await page.screenshot(path="tests/screenshots/content_analysis.png")
                    print("📸 Screenshot saved: content_analysis.png")
                    
                    # Check for specific messages about validated sermons
                    validated_messages = await page.locator("text*=validated").all()
                    processed_messages = await page.locator("text*=processed").all()
                    
                    print(f"✅ Found {len(validated_messages)} validated-related messages")
                    print(f"✅ Found {len(processed_messages)} processed-related messages")
                    
                    if validated_messages or processed_messages:
                        print("🎉 Analytics page shows validated/processed sermon data!")
                        success = True
                    else:
                        print("⚠️ No specific validated/processed sermon indicators found")
                        success = False
                
                else:
                    print("❌ Content Analysis tab not found")
                    success = False
                    
            else:
                print("❌ Analytics navigation not found")
                success = False
                
            # Final screenshot
            await page.screenshot(path="tests/screenshots/final_state.png")
            print("📸 Final screenshot saved: final_state.png")
            
            return success
                
        except Exception as e:
            print(f"❌ Error during test: {e}")
            import traceback
            traceback.print_exc()
            
            # Take error screenshot
            try:
                await page.screenshot(path="tests/screenshots/error_state.png")
                print("📸 Error screenshot saved: error_state.png")
            except:
                pass
            
            return False
            
        finally:
            # Close browser
            await browser.close()

def run_playwright_test():
    """Run the Playwright test."""
    
    # Create screenshots directory
    screenshots_dir = Path("tests/screenshots")
    screenshots_dir.mkdir(exist_ok=True)
    
    # Run the async test
    success = asyncio.run(test_analytics_ui())
    
    return success

if __name__ == '__main__':
    success = run_playwright_test()
    exit_code = 0 if success else 1
    print(f'\nPlaywright test {"PASSED" if success else "FAILED"} - Exit code: {exit_code}')
    sys.exit(exit_code)
