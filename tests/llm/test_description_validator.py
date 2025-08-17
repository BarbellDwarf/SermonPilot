"""
Test suite for the Description Validator.

Tests the validation functionality against sample descriptions and ensures
proper integration with the existing LLM validation system.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

# Add the src directory to the path so we can import our modules
import sys
from pathlib import Path

# Get the repo root directory (two levels up from this test file)
repo_root = Path.cwd()
if repo_root.name == "llm":
    repo_root = repo_root.parent.parent
elif repo_root.name == "tests":
    repo_root = repo_root.parent
# If we're already in the repo root, stay there
src_dir = repo_root / "src"
sys.path.insert(0, str(src_dir))

try:
    from description_validator import DescriptionValidator, ValidationResult, ValidationSummary
    from llm_manager import LLMManager
except ImportError as e:
    print(f"Import error: {e}")
    print(f"Attempted to import from: {src_dir}")
    print("Make sure you're running this from the project root directory")
    sys.exit(1)


class TestDescriptionValidator(unittest.TestCase):
    """Test cases for the DescriptionValidator class."""
    
    def setUp(self):
        """Set up test environment with mock config."""
        self.test_config = {
            'llm': {
                'validator': {
                    'enabled': True,
                    'provider': 'ollama',
                    'ollama': {
                        'host': 'http://localhost:11434',
                        'model': 'gemma2:2b'
                    }
                }
            },
            'metadata_processing': {
                'description': {
                    'validation': {
                        'enabled': True,
                        'criteria': [
                            'Contains specific theological content or Bible references',
                            'Mentions the speaker\'s main message or key points',
                            'Is written in a professional, engaging style',
                            'Avoids generic Christian phrases without substance',
                            'Has clear application or takeaway for listeners'
                        ]
                    }
                }
            },
            'output_directory': 'processed_sermons'
        }
        
        # Create a temporary config file
        self.temp_dir = tempfile.mkdtemp()
        self.config_file = os.path.join(self.temp_dir, 'test_config.yaml')
        
        import yaml
        with open(self.config_file, 'w') as f:
            yaml.dump(self.test_config, f)
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('llm_manager.LLMManager')
    def test_validator_initialization(self, mock_llm_manager):
        """Test that the validator initializes correctly."""
        # Mock the LLM manager
        mock_manager_instance = Mock()
        mock_manager_instance.validator_provider = Mock()
        mock_llm_manager.return_value = mock_manager_instance
        
        validator = DescriptionValidator(self.config_file)
        
        self.assertIsNotNone(validator.config)
        self.assertIsNotNone(validator.llm_manager)
        self.assertEqual(len(validator.validation_criteria), 5)
        self.assertEqual(validator.min_length, 50)
        self.assertEqual(validator.max_length, 1600)
    
    def test_parse_validation_response(self):
        """Test parsing of LLM validation responses."""
        validator = DescriptionValidator.__new__(DescriptionValidator)
        validator.validation_criteria = [
            'Contains specific theological content',
            'Mentions main message',
            'Professional style',
            'Avoids generic phrases',
            'Clear application'
        ]
        validator.regeneration_threshold = 0.6
        
        # Test a good response
        good_response = """
        SCORE: 0.85
        STATUS: APPROVED
        REASON: Well-written description with clear theological content
        CRITERIA_MET: 1,2,3,5
        CRITERIA_FAILED: 4
        """
        
        score, is_valid, reason, criteria_met, criteria_failed = validator._parse_validation_response(good_response)
        
        self.assertEqual(score, 0.85)
        self.assertTrue(is_valid)
        self.assertIn('theological content', reason)
        self.assertEqual(len(criteria_met), 4)
        self.assertEqual(len(criteria_failed), 1)
    
    def test_parse_validation_response_malformed(self):
        """Test parsing of malformed validation responses."""
        validator = DescriptionValidator.__new__(DescriptionValidator)
        validator.validation_criteria = ['Test criterion']
        validator.regeneration_threshold = 0.6
        
        # Test malformed response
        malformed_response = "This is not a properly formatted response"
        
        score, is_valid, reason, criteria_met, criteria_failed = validator._parse_validation_response(malformed_response)
        
        # Should use defaults - note that default score of 0.5 is below regeneration threshold
        self.assertEqual(score, 0.5)
        self.assertFalse(is_valid)  # 0.5 is below 0.6 threshold, so should be invalid
        self.assertEqual(reason, "Parsed response")
        self.assertEqual(len(criteria_met), 0)
        self.assertEqual(len(criteria_failed), 0)
    
    def test_description_length_validation(self):
        """Test basic description length validation."""
        validator = DescriptionValidator.__new__(DescriptionValidator)
        validator.min_length = 50
        validator.max_length = 1600
        validator.validation_criteria = ['Test criterion']
        validator.regeneration_threshold = 0.6
        
        # Test too short
        short_desc = "Too short"
        is_valid, reason, score, met, failed = validator.validate_description(short_desc)
        self.assertFalse(is_valid)
        self.assertIn("too short", reason.lower())
        self.assertEqual(score, 0.0)
        
        # Test too long
        long_desc = "x" * 2000
        is_valid, reason, score, met, failed = validator.validate_description(long_desc)
        self.assertFalse(is_valid)
        self.assertIn("maximum length", reason.lower())
        self.assertEqual(score, 0.2)
    
    def test_create_sample_sermon_directory(self):
        """Create a sample sermon directory for testing local validation."""
        # Create a test sermon directory structure
        sermon_id = "123456789"
        sermon_dir = Path(self.temp_dir) / "processed_sermons" / sermon_id
        sermon_dir.mkdir(parents=True, exist_ok=True)
        
        # Create a sample description file
        description_file = sermon_dir / f"{sermon_id}_description.txt"
        sample_description = (
            "Pastor John Smith's sermon on Romans 8:28 emphasizes God's sovereignty "
            "in working all things together for good for those who love Him. Smith "
            "explains that this promise doesn't mean all things are good, but that "
            "God can use even difficult circumstances to accomplish His purposes. "
            "He encourages believers to trust in God's perfect plan and timing, "
            "even when they can't see the bigger picture. The application is to "
            "maintain faith during trials and remember that God's love never fails."
        )
        description_file.write_text(sample_description, encoding='utf-8')
        
        # Create hashtags file
        hashtags_file = sermon_dir / f"{sermon_id}_hashtags.txt"
        hashtags_file.write_text("#Faith #Trust #GodsLove #Romans #Sovereignty", encoding='utf-8')
        
        return sermon_dir, sample_description
    
    @patch('description_validator.LLMManager')
    def test_validate_local_sermon(self, mock_llm_manager):
        """Test validation of a local sermon directory."""
        # Create sample sermon
        sermon_dir, sample_description = self.test_create_sample_sermon_directory()
        
        # Mock the LLM manager and validator
        mock_manager_instance = Mock()
        mock_validator_provider = Mock()
        mock_validator_provider.chat.return_value = """
        SCORE: 0.85
        STATUS: APPROVED  
        REASON: Contains specific biblical content and practical application
        CRITERIA_MET: 1,2,3,5
        CRITERIA_FAILED: 4
        """
        mock_manager_instance.validator_provider = mock_validator_provider
        mock_llm_manager.return_value = mock_manager_instance
        
        # Update config to point to our test directory
        updated_config = self.test_config.copy()
        updated_config['output_directory'] = str(Path(self.temp_dir) / "processed_sermons")
        
        import yaml
        with open(self.config_file, 'w') as f:
            yaml.dump(updated_config, f)
        
        validator = DescriptionValidator(self.config_file)
        result = validator._validate_local_sermon(sermon_dir)
        
        self.assertIsNotNone(result)
        self.assertEqual(result.sermon_id, "123456789")
        self.assertTrue(result.is_valid)
        self.assertGreater(result.validation_score, 0.8)
        self.assertEqual(result.description, sample_description)
        self.assertEqual(result.source, "local")
    
    def test_validation_summary_generation(self):
        """Test generation of validation summaries."""
        # Create sample validation results
        results = [
            ValidationResult(
                sermon_id="1", title="Test 1", speaker="Speaker 1",
                description="Good description", description_length=100,
                is_valid=True, validation_reason="Meets criteria",
                validation_score=0.85, criteria_met=["criterion1", "criterion2"],
                criteria_failed=[], needs_regeneration=False,
                validated_at="2024-01-01", source="local"
            ),
            ValidationResult(
                sermon_id="2", title="Test 2", speaker="Speaker 2", 
                description="Poor description", description_length=50,
                is_valid=False, validation_reason="Too generic",
                validation_score=0.45, criteria_met=["criterion1"],
                criteria_failed=["criterion2", "criterion3"], needs_regeneration=True,
                validated_at="2024-01-01", source="local"
            )
        ]
        
        validator = DescriptionValidator.__new__(DescriptionValidator)
        validator.validation_criteria = ["criterion1", "criterion2", "criterion3"]
        
        summary = validator.generate_summary(results)
        
        self.assertEqual(summary.total_sermons, 2)
        self.assertEqual(summary.valid_descriptions, 1)
        self.assertEqual(summary.invalid_descriptions, 1)
        self.assertEqual(summary.validation_rate, 50.0)
        self.assertEqual(summary.needs_regeneration, 1)
        self.assertEqual(summary.average_score, 0.65)
        
        # Check criteria performance
        self.assertEqual(summary.criteria_performance["criterion1"], 100.0)  # Met by both
        self.assertEqual(summary.criteria_performance["criterion2"], 50.0)   # Met by one
        self.assertEqual(summary.criteria_performance["criterion3"], 0.0)    # Met by none


def run_basic_tests():
    """Run basic functionality tests without requiring LLM providers."""
    print("🧪 Running Description Validator Tests...")
    
    # Create a simple test suite with just the basic tests
    suite = unittest.TestSuite()
    
    # Add tests that don't require LLM mocking
    suite.addTest(TestDescriptionValidator('test_parse_validation_response'))
    suite.addTest(TestDescriptionValidator('test_parse_validation_response_malformed'))
    suite.addTest(TestDescriptionValidator('test_description_length_validation'))
    suite.addTest(TestDescriptionValidator('test_validation_summary_generation'))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    if result.wasSuccessful():
        print("\n✅ All basic tests passed!")
    else:
        print(f"\n❌ {len(result.failures)} failures, {len(result.errors)} errors")
        
    return result.wasSuccessful()


def test_with_real_config():
    """Test validator initialization with the actual project config."""
    print("\n🔧 Testing with real configuration...")
    
    config_path = "config.yaml"
    if not os.path.exists(config_path):
        print("❌ config.yaml not found. Please run from project root.")
        return False
    
    try:
        # Test initialization
        validator = DescriptionValidator(config_path)
        print(f"✅ Validator initialized successfully")
        print(f"   Criteria: {len(validator.validation_criteria)}")
        print(f"   Output dir: {validator.output_dir}")
        
        # Test if validator provider is available
        if validator.llm_manager.validator_provider:
            print("✅ Validator LLM provider available")
        else:
            print("⚠️  Validator LLM provider not configured")
            
        return True
        
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False


if __name__ == '__main__':
    print("=" * 60)
    print("📋 DESCRIPTION VALIDATOR TEST SUITE")
    print("=" * 60)
    
    # Run basic tests
    basic_success = run_basic_tests()
    
    # Test with real config if available
    config_success = test_with_real_config()
    
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    print(f"Basic Tests: {'✅ PASS' if basic_success else '❌ FAIL'}")
    print(f"Config Test: {'✅ PASS' if config_success else '❌ FAIL'}")
    
    if basic_success and config_success:
        print("\n🎉 All tests completed successfully!")
        print("\nNext steps:")
        print("1. Run: python description_validator.py --local-sermons --detailed-report")
        print("2. Review validation results and criteria performance")
        print("3. Adjust validation criteria in config.yaml if needed")
    else:
        print("\n⚠️  Some tests failed. Please check the configuration.")
        
    sys.exit(0 if basic_success else 1)
