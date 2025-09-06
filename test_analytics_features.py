#!/usr/bin/env python3
"""
Test script for the new analytics features

Tests the RAG system, analytics data layer, and chat interface.
"""

import sys
import logging
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_analytics_data_layer():
    """Test the SermonAudio analytics data layer"""
    print("\n🔍 Testing SermonAudio Analytics Data Layer...")
    
    try:
        from ui.sermonaudio_analytics import SermonAudioAnalytics
        
        analytics = SermonAudioAnalytics()
        
        # Test getting analytics data
        print("  - Fetching analytics data...")
        data = analytics.get_all_sermon_analytics()
        
        print(f"  ✅ Successfully fetched {len(data)} sermon records")
        
        if data:
            sample = data[0]
            print(f"  📄 Sample record: {sample.get('title', 'Unknown')} by {sample.get('speaker', 'Unknown')}")
            print(f"     Views: {sample.get('views', 0)}, Listens: {sample.get('listens', 0)}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Analytics data layer test failed: {e}")
        return False


def test_rag_system():
    """Test the RAG system"""
    print("\n🤖 Testing RAG System...")
    
    try:
        from ui.rag_system import SermonAnalyticsRAG, initialize_rag_system_with_data
        from ui.sermonaudio_analytics import SermonAudioAnalytics
        
        # Get some test data
        analytics = SermonAudioAnalytics()
        data = analytics.get_all_sermon_analytics()
        
        if not data:
            print("  ⚠️  No analytics data available for RAG testing")
            return False
        
        # Initialize RAG system
        print("  - Initializing RAG system...")
        rag = initialize_rag_system_with_data(data[:10])  # Use first 10 records
        
        # Test queries
        test_questions = [
            "What are the most popular sermons?",
            "Which speaker has the highest views?",
            "What's the average completion rate?"
        ]
        
        for question in test_questions:
            print(f"  - Testing question: '{question}'")
            response = rag.query_analytics(question)
            
            if response.get('answer'):
                print(f"    ✅ Got response: {response['answer'][:100]}...")
            else:
                print(f"    ⚠️  No answer for question")
        
        # Test collection stats
        stats = rag.get_collection_stats()
        print(f"  📊 Collection stats: {stats.get('total_documents', 0)} documents")
        
        return True
        
    except Exception as e:
        print(f"  ❌ RAG system test failed: {e}")
        return False


def test_performance_monitor():
    """Test the performance monitor"""
    print("\n⚡ Testing Performance Monitor...")
    
    try:
        from ui.performance_monitor import PerformanceMonitor
        
        monitor = PerformanceMonitor()
        
        # Test getting metrics
        print("  - Getting system metrics...")
        system_metrics = monitor.get_system_metrics()
        
        print(f"  📊 CPU usage: {system_metrics.get('cpu_percent', 0):.1f}%")
        print(f"  📊 Memory usage: {system_metrics.get('memory_percent', 0):.1f}%")
        print(f"  📊 Disk usage: {system_metrics.get('disk_percent', 0):.1f}%")
        
        # Test optimization recommendations with mock processing metrics
        print("  - Getting optimization recommendations...")
        mock_processing_metrics = {
            'total_processed': 10,
            'success_rate': 0.9,
            'avg_processing_time': 30.0,
            'error_count': 1,
            'error_rate': 10.0,
            'queue_length': 5
        }
        
        recommendations = monitor.get_optimization_recommendations(
            system_metrics, mock_processing_metrics
        )
        
        print(f"  💡 Got {len(recommendations)} recommendations")
        for rec in recommendations[:3]:  # Show first 3
            print(f"     - {rec.get('title', 'Unknown recommendation')}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Performance monitor test failed: {e}")
        return False


def test_dependencies():
    """Test that all required dependencies are available"""
    print("\n📦 Testing Dependencies...")
    
    dependencies = [
        ("chromadb", "ChromaDB"),
        ("sentence_transformers", "Sentence Transformers"),
        ("plotly", "Plotly"),
        ("psutil", "PSUtil")
    ]
    
    all_available = True
    
    for module, name in dependencies:
        try:
            __import__(module)
            print(f"  ✅ {name} available")
        except ImportError:
            print(f"  ❌ {name} not available")
            all_available = False
    
    return all_available


def main():
    """Run all tests"""
    print("🧪 Testing New Analytics Features")
    print("=" * 50)
    
    tests = [
        ("Dependencies", test_dependencies),
        ("Performance Monitor", test_performance_monitor),
        ("Analytics Data Layer", test_analytics_data_layer),
        ("RAG System", test_rag_system)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"\n❌ {test_name} test crashed: {e}")
            results[test_name] = False
    
    # Summary
    print("\n" + "=" * 50)
    print("📋 Test Summary:")
    
    passed = 0
    total = len(results)
    
    for test_name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status}: {test_name}")
        if success:
            passed += 1
    
    print(f"\n🏆 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Analytics features are ready.")
        return 0
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
