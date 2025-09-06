#!/usr/bin/env python3
"""
Test script to verify all components are working properly
"""

import sys
import os
from pathlib import Path

# Add the UI directory to the path
ui_dir = Path(__file__).parent / "ui"
sys.path.insert(0, str(ui_dir))

def test_performance_monitor():
    """Test the performance monitoring system"""
    print("Testing Performance Monitor...")
    try:
        from performance_monitor import PerformanceMonitor
        monitor = PerformanceMonitor()
        metrics = monitor.get_system_metrics()
        print(f"✅ Performance Monitor: CPU {metrics['cpu']['usage_percent']}%, "
              f"Memory {metrics['memory']['used_percent']}%")
        return True
    except Exception as e:
        print(f"❌ Performance Monitor failed: {e}")
        return False

def test_sermonaudio_analytics():
    """Test the SermonAudio analytics"""
    print("Testing SermonAudio Analytics...")
    try:
        from sermonaudio_analytics import SermonAudioAnalytics
        analytics = SermonAudioAnalytics()
        sermons = analytics.get_all_sermon_analytics()
        print(f"✅ SermonAudio Analytics: Generated {len(sermons)} sermon records")
        return True
    except Exception as e:
        print(f"❌ SermonAudio Analytics failed: {e}")
        return False

def test_rag_system():
    """Test the RAG system"""
    print("Testing RAG System...")
    try:
        from rag_system import SermonAnalyticsRAG
        rag = SermonAnalyticsRAG()
        
        # Test with sample data
        sample_data = [{
            'sermon_id': 'test123',
            'title': 'Test Sermon',
            'speaker': 'Test Speaker',
            'views': 100,
            'engagement_score': 8.5
        }]
        
        rag.add_analytics_data(sample_data)
        result = rag.query_analytics("What sermons have high engagement?")
        print(f"✅ RAG System: Query successful - {result['answer'][:50]}...")
        return True
    except Exception as e:
        print(f"❌ RAG System failed: {e}")
        return False

def test_analytics_chat():
    """Test the analytics chat interface"""
    print("Testing Analytics Chat Interface...")
    try:
        from analytics_chat import AnalyticsChatInterface
        chat = AnalyticsChatInterface()
        print("✅ Analytics Chat Interface: Initialized successfully")
        return True
    except Exception as e:
        print(f"❌ Analytics Chat Interface failed: {e}")
        return False

def test_streamlit_integration():
    """Test basic Streamlit integration"""
    print("Testing Streamlit Integration...")
    try:
        import streamlit as st
        from ui_pages.analytics import show_analytics
        print("✅ Streamlit Integration: Analytics page importable")
        return True
    except Exception as e:
        print(f"❌ Streamlit Integration failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🔍 Running Component Tests for SermonAudio Processor UI\n")
    
    tests = [
        test_performance_monitor,
        test_sermonaudio_analytics,
        test_rag_system,
        test_analytics_chat,
        test_streamlit_integration
    ]
    
    results = []
    for test in tests:
        result = test()
        results.append(result)
        print()
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The implementation is working correctly.")
    else:
        print("⚠️ Some tests failed. Please check the error messages above.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)