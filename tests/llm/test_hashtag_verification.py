#!/usr/bin/env python3
"""
Test script for hashtag verification functionality.
Tests the new two-pass hashtag generation with verification.
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

import yaml
from llm_manager import LLMManager

def mock_llm_manager_for_testing():
    """Create a mock LLM manager for testing hashtag verification"""
    class MockLLMManager:
        def __init__(self):
            self.call_count = 0
            
        def get_provider_info(self):
            return {'primary': {'type': 'mock'}}
            
        def chat(self, messages):
            self.call_count += 1
            prompt = messages[0]['content'].lower()
            
            if 'hashtag validator' in prompt:
                # This is the verification pass
                return "#faith #salvation #grace #jesus #church #hope"
            else:
                # This is the initial generation pass - simulate problematic output
                return "Here are some relevant hashtags for this sermon:\n\n#faith #salvation #grace #jesus #church #hope #love\n\nThese hashtags should help with discoverability."

    return MockLLMManager()

def test_hashtag_verification():
    """Test the hashtag verification system"""
    print("🧪 Testing Hashtag Verification System")
    print("=" * 50)
    
    # Import functions after setting up the mock
    from sermon_updater import verify_hashtags, generate_hashtags
    import sermon_updater
    
    # Mock the LLM manager
    original_llm_manager = sermon_updater.llm_manager
    mock_manager = mock_llm_manager_for_testing()
    sermon_updater.llm_manager = mock_manager
    
    try:
        # Test case 1: Basic verification
        print("\n📋 Test 1: Basic hashtag verification")
        problematic_input = "Here are some hashtags:\n\n#faith #hope #salvation\n\nThese should work well."
        sermon_text = "This sermon is about faith, hope, and salvation through Jesus Christ."
        
        verified = verify_hashtags(problematic_input, sermon_text)
        print(f"Input: {problematic_input}")
        print(f"Verified: {verified}")
        
        # Should extract only hashtags
        assert verified.startswith("#"), "Verified output should start with hashtag"
        assert "Here are" not in verified, "Comments should be removed"
        assert "These should" not in verified, "Comments should be removed"
        print("✅ Basic verification passed")
        
        # Test case 2: Full generation with verification
        print("\n📋 Test 2: Full hashtag generation with verification")
        sermon_text = "This is a sermon about the love of God and salvation through faith in Jesus Christ."
        
        # Test with verification enabled
        sermon_updater.config = {'hashtag_verification': True}
        hashtags_with_verification = generate_hashtags(sermon_text)
        
        print(f"With verification: {hashtags_with_verification}")
        assert hashtags_with_verification.startswith("#"), "Should start with hashtag"
        assert len(hashtags_with_verification) <= 150, "Should respect length limit"
        print("✅ Full generation with verification passed")
        
        # Test case 3: Generation without verification (backward compatibility)
        print("\n📋 Test 3: Generation without verification")
        sermon_updater.config = {'hashtag_verification': False}
        
        # Reset call count
        mock_manager.call_count = 0
        hashtags_without_verification = generate_hashtags(sermon_text)
        
        print(f"Without verification: {hashtags_without_verification}")
        print(f"LLM calls made: {mock_manager.call_count}")
        assert mock_manager.call_count == 1, "Should only make one LLM call when verification disabled"
        print("✅ Generation without verification passed")
        
        # Test case 4: Edge cases
        print("\n📋 Test 4: Edge cases")
        
        # Test with no hashtags in input
        no_hashtags_input = "This is just regular text with no hashtags at all."
        verified_no_hashtags = verify_hashtags(no_hashtags_input, sermon_text)
        print(f"No hashtags input verified: {verified_no_hashtags}")
        assert verified_no_hashtags.startswith("#"), "Should generate fallback hashtags"
        print("✅ No hashtags case passed")
        
        # Test with malformed hashtags
        malformed_input = "#faith# #hope #salvation# #jesus"
        verified_malformed = verify_hashtags(malformed_input, sermon_text)
        print(f"Malformed input verified: {verified_malformed}")
        assert "#faith" in verified_malformed, "Should extract valid parts"
        print("✅ Malformed hashtags case passed")
        
        print("\n🎉 All hashtag verification tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Restore original LLM manager
        sermon_updater.llm_manager = original_llm_manager

def test_problematic_responses():
    """Test with various problematic LLM responses that we've seen in practice"""
    print("\n🔧 Testing Problematic Response Patterns")
    print("=" * 50)
    
    from sermon_updater import verify_hashtags
    
    test_cases = [
        {
            "name": "Comments at beginning",
            "input": "Here are some relevant hashtags for this sermon:\n#faith #hope #salvation #jesus",
            "expected_contains": ["#faith", "#hope", "#salvation", "#jesus"]
        },
        {
            "name": "Comments at end", 
            "input": "#faith #hope #salvation\n\nThese hashtags capture the main themes of the sermon.",
            "expected_contains": ["#faith", "#hope", "#salvation"]
        },
        {
            "name": "Mixed with explanations",
            "input": "I would suggest these hashtags:\n1. #faith - for the main theme\n2. #hope - for the secondary theme\n3. #salvation - for the conclusion",
            "expected_contains": ["#faith", "#hope", "#salvation"]
        },
        {
            "name": "Comma separated",
            "input": "#faith, #hope, #salvation, #jesus, #church",
            "expected_contains": ["#faith", "#hope", "#salvation", "#jesus", "#church"]
        },
        {
            "name": "Multiple lines with numbers",
            "input": "1. #faith\n2. #hope\n3. #salvation\n4. #jesus",
            "expected_contains": ["#faith", "#hope", "#salvation", "#jesus"]
        }
    ]
    
    sermon_text = "Sample sermon text about faith and hope."
    
    # Mock LLM manager that always returns clean hashtags
    class CleanMockLLM:
        def get_provider_info(self):
            return {'primary': {'type': 'mock'}}
        def chat(self, messages):
            return "#faith #hope #salvation #jesus #church"
    
    import sermon_updater
    original_llm_manager = sermon_updater.llm_manager
    sermon_updater.llm_manager = CleanMockLLM()
    
    try:
        all_passed = True
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n📋 Test {i}: {test_case['name']}")
            print(f"Input: {repr(test_case['input'])}")
            
            result = verify_hashtags(test_case['input'], sermon_text)
            print(f"Result: {result}")
            
            # Check that all expected hashtags are present
            for expected in test_case['expected_contains']:
                if expected not in result:
                    print(f"❌ Missing expected hashtag: {expected}")
                    all_passed = False
                else:
                    print(f"✅ Found expected hashtag: {expected}")
            
            # Check that no comments remain
            if any(word in result.lower() for word in ['here', 'are', 'some', 'suggest', 'would', 'theme', 'main']):
                print(f"❌ Comments still present in result")
                all_passed = False
            else:
                print("✅ No comments detected")
        
        if all_passed:
            print("\n🎉 All problematic response tests passed!")
        else:
            print("\n❌ Some tests failed")
            
        return all_passed
        
    finally:
        sermon_updater.llm_manager = original_llm_manager

if __name__ == "__main__":
    print("🚀 Hashtag Verification Test Suite")
    print("=" * 70)
    
    # Test basic functionality
    basic_passed = test_hashtag_verification()
    
    # Test problematic response patterns
    problematic_passed = test_problematic_responses()
    
    print("\n" + "=" * 70)
    print("📊 Test Results Summary")
    print("=" * 70)
    print(f"Basic functionality: {'✅ PASSED' if basic_passed else '❌ FAILED'}")
    print(f"Problematic responses: {'✅ PASSED' if problematic_passed else '❌ FAILED'}")
    
    overall_success = basic_passed and problematic_passed
    print(f"\nOverall result: {'✅ ALL TESTS PASSED' if overall_success else '❌ SOME TESTS FAILED'}")
    
    if overall_success:
        print("\n💡 Hashtag verification system is working correctly!")
        print("   • Comments and explanations are properly removed")
        print("   • Only valid hashtags are extracted")
        print("   • Length limits are enforced")
        print("   • Backward compatibility is maintained")
    else:
        print("\n⚠️  Some issues were detected. Please check the test output above.")
