#!/usr/bin/env python3
"""
Integration test for hashtag verification in the full sermon processing pipeline.
This tests the complete flow with hashtag verification enabled.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

def test_hashtag_integration():
    """Test hashtag verification in the context of the full processing pipeline"""
    print("🧪 Integration Test: Hashtag Verification in Full Pipeline")
    print("=" * 60)
    
    # Mock sermon data that might produce problematic hashtag responses
    test_transcript = """
    In today's sermon, we explore the profound theme of God's love and grace.
    Through faith in Jesus Christ, we find salvation and hope for eternal life.
    The church community provides support and fellowship as we grow in Christian living.
    We must trust in God's plan and walk in obedience to His word.
    """
    
    # Import required modules
    import sermon_updater
    
    # Create a mock LLM manager that simulates problematic responses
    class ProblematicLLMManager:
        def __init__(self):
            self.call_count = 0
            
        def get_provider_info(self):
            return {'primary': {'type': 'mock'}}
            
        def chat(self, messages):
            self.call_count += 1
            prompt = messages[0]['content'].lower()
            
            if 'hashtag validator' in prompt:
                # Verification pass - return clean hashtags
                return "#faith #salvation #grace #jesus #church #hope #love #christian"
            else:
                # Initial generation - return problematic response with comments
                return """I'll generate some relevant hashtags for this sermon about faith and salvation:

#faith #salvation #grace #jesus #church #hope #love #christian #eternal #obedience

These hashtags should help people discover this sermon when searching for content about Christian faith, salvation, and spiritual growth. The hashtags cover the main themes discussed."""
    
    # Mock the LLM manager
    original_llm_manager = sermon_updater.llm_manager
    mock_manager = ProblematicLLMManager()
    sermon_updater.llm_manager = mock_manager
    
    try:
        print("📋 Testing hashtag generation with problematic LLM response...")
        print(f"Input transcript: {test_transcript[:100]}...")
        
        # Test with verification enabled (default)
        sermon_updater.config = {'hashtag_verification': True}
        
        verified_hashtags = sermon_updater.generate_hashtags(test_transcript)
        print(f"\n✅ With verification enabled:")
        print(f"   Result: {verified_hashtags}")
        print(f"   LLM calls made: {mock_manager.call_count}")
        
        # Verify the result
        assert verified_hashtags.startswith("#"), "Should start with hashtag"
        assert "I'll generate" not in verified_hashtags, "Comments should be removed"
        assert "These hashtags should help" not in verified_hashtags, "Comments should be removed"
        assert len(verified_hashtags) <= 150, "Should respect length limit"
        assert mock_manager.call_count == 2, "Should make two LLM calls (generation + verification)"
        
        print("   ✅ Verification successfully removed comments and explanations")
        print("   ✅ Length limit enforced")
        print("   ✅ Two-pass system working correctly")
        
        # Test with verification disabled for comparison
        mock_manager.call_count = 0
        sermon_updater.config = {'hashtag_verification': False}
        
        unverified_hashtags = sermon_updater.generate_hashtags(test_transcript)
        print(f"\n⚠️  With verification disabled:")
        print(f"   Result: {unverified_hashtags[:100]}...")
        print(f"   LLM calls made: {mock_manager.call_count}")
        
        assert mock_manager.call_count == 1, "Should make only one LLM call when verification disabled"
        print("   ✅ Single-pass mode working (backward compatibility)")
        
        # Show the difference
        print(f"\n📊 Comparison:")
        print(f"   Verified:   {len(verified_hashtags)} chars, clean format")
        print(f"   Unverified: {len(unverified_hashtags)} chars, may contain comments")
        
        print(f"\n✅ Integration test passed!")
        print("   • Hashtag verification properly integrated into generation flow")
        print("   • Configuration option works correctly")
        print("   • Backward compatibility maintained")
        print("   • Comments and explanations successfully removed")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Restore original LLM manager
        sermon_updater.llm_manager = original_llm_manager

def test_edge_cases():
    """Test edge cases for hashtag verification"""
    print("\n🔧 Testing Edge Cases")
    print("=" * 40)
    
    import sermon_updater
    
    # Mock LLM manager for edge cases
    class EdgeCaseLLMManager:
        def get_provider_info(self):
            return {'primary': {'type': 'mock'}}
            
        def chat(self, messages):
            prompt = messages[0]['content'].lower()
            if 'hashtag validator' in prompt:
                # Simulate different edge case responses for verification
                if 'empty' in prompt:
                    return "No valid hashtags found"
                elif 'long' in prompt:
                    return "#verylonghashtag #anotherlonghashtag #extremelylonghashtagnamethatexceedslimits #short #medium #lengthy"
                else:
                    return "#faith #hope #love"
            else:
                # Initial generation
                return "#faith #hope #love"
    
    original_llm_manager = sermon_updater.llm_manager
    sermon_updater.llm_manager = EdgeCaseLLMManager()
    sermon_updater.config = {'hashtag_verification': True}
    
    try:
        # Test case 1: Empty response
        print("📋 Edge case 1: Empty verification response")
        result = sermon_updater.verify_hashtags("", "empty sermon text")
        print(f"   Result: {result}")
        assert result.startswith("#"), "Should provide fallback hashtags"
        print("   ✅ Handles empty response correctly")
        
        # Test case 2: Length limit enforcement
        print("\n📋 Edge case 2: Length limit enforcement")
        long_input = "#verylonghashtag #anotherlonghashtag #extremelylonghashtagnamethatexceedslimits #short #medium #lengthy #more #tags #here #and #more #tags"
        result = sermon_updater.verify_hashtags(long_input, "long sermon text")
        print(f"   Result: {result}")
        print(f"   Length: {len(result)} chars")
        assert len(result) <= 150, "Should enforce length limit"
        print("   ✅ Length limit properly enforced")
        
        print("\n✅ All edge cases handled correctly!")
        return True
        
    except Exception as e:
        print(f"\n❌ Edge case test failed: {e}")
        return False
        
    finally:
        sermon_updater.llm_manager = original_llm_manager

if __name__ == "__main__":
    print("🚀 Hashtag Verification Integration Test Suite")
    print("=" * 70)
    
    # Run integration test
    integration_passed = test_hashtag_integration()
    
    # Run edge case tests
    edge_cases_passed = test_edge_cases()
    
    print("\n" + "=" * 70)
    print("📊 Integration Test Results")
    print("=" * 70)
    print(f"Integration test: {'✅ PASSED' if integration_passed else '❌ FAILED'}")
    print(f"Edge cases test:  {'✅ PASSED' if edge_cases_passed else '❌ FAILED'}")
    
    overall_success = integration_passed and edge_cases_passed
    print(f"\nOverall result: {'✅ ALL TESTS PASSED' if overall_success else '❌ SOME TESTS FAILED'}")
    
    if overall_success:
        print("\n🎉 Hashtag verification system is fully integrated and working!")
        print("\n📝 How to use:")
        print("   • Set hashtag_verification: true in config.yaml (default)")
        print("   • Set hashtag_verification: false to disable verification")
        print("   • The system automatically cleans up problematic LLM responses")
        print("   • Two-pass system ensures clean, valid hashtag output")
    else:
        print("\n⚠️  Integration issues detected. Please check the test output.")
