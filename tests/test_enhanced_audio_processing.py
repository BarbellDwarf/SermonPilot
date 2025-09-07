"""
Test the enhanced audio processing components for Q&A content

Tests for QuestionProcessor, AdaptiveAudioProcessor, and ProcessingModeSelector.
"""

import pytest
import numpy as np
import sys
from pathlib import Path

# Add project paths for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "ui"))

try:
    from src.audio.question_processor import QuestionProcessor
    from src.audio.adaptive_processor import AdaptiveAudioProcessor
    from ui.components.processing_modes import ProcessingModeSelector
except ImportError as e:
    pytest.skip(f"Enhanced audio processing components not available: {e}", allow_module_level=True)


class TestQuestionProcessor:
    """Test QuestionProcessor component."""
    
    def test_initialization(self):
        """Test basic initialization."""
        config = {
            'sample_rate': 44100,
            'question_threshold': 0.6
        }
        processor = QuestionProcessor(config)
        
        assert processor.sample_rate == 44100
        assert processor.question_threshold == 0.6
        assert processor.min_question_duration == 2.0
        assert processor.max_question_duration == 30.0

    def test_basic_question_detection(self):
        """Test basic question detection without librosa."""
        config = {'sample_rate': 44100}
        processor = QuestionProcessor(config)
        
        # Create test audio - 5 seconds of audio
        duration = 5.0
        audio_data = np.random.randn(int(44100 * duration)) * 0.1
        
        # Add some "speech-like" segments
        # Higher energy segment that might be detected as speech
        start_sample = int(1.0 * 44100)
        end_sample = int(3.0 * 44100)
        audio_data[start_sample:end_sample] += np.sin(2 * np.pi * 200 * np.linspace(0, 2, end_sample - start_sample)) * 0.3
        
        segments = processor.detect_question_segments(audio_data)
        
        # Should return a list (might be empty for random audio)
        assert isinstance(segments, list)
        
        # Each segment should be a tuple of (start, end)
        for segment in segments:
            assert isinstance(segment, tuple)
            assert len(segment) == 2
            assert segment[0] < segment[1]  # Start before end
            assert segment[0] >= 0  # Non-negative start
            assert segment[1] <= duration  # End within audio

    def test_segment_validation(self):
        """Test segment duration validation."""
        config = {'sample_rate': 44100}
        processor = QuestionProcessor(config)
        
        # Valid segment
        valid_segment = (1.0, 5.0)  # 4 seconds
        assert processor._validate_segment_duration(valid_segment)
        
        # Too short
        short_segment = (1.0, 1.5)  # 0.5 seconds
        assert not processor._validate_segment_duration(short_segment)
        
        # Too long
        long_segment = (1.0, 35.0)  # 34 seconds
        assert not processor._validate_segment_duration(long_segment)

    def test_segment_merging(self):
        """Test merging of overlapping segments."""
        config = {'sample_rate': 44100}
        processor = QuestionProcessor(config)
        
        # Overlapping segments
        segments = [
            (1.0, 3.0),
            (2.5, 5.0),  # Overlaps with first
            (7.0, 9.0),  # Separate
            (8.5, 10.0)  # Overlaps with third
        ]
        
        merged = processor._merge_overlapping_segments(segments)
        
        # Should have 2 merged segments
        assert len(merged) == 2
        assert merged[0] == (1.0, 5.0)  # First two merged
        assert merged[1] == (7.0, 10.0)  # Last two merged

    def test_extract_segment(self):
        """Test audio segment extraction."""
        config = {'sample_rate': 1000}  # Simple sample rate for testing
        processor = QuestionProcessor(config)
        
        audio_data = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])  # 10 samples at 1000 Hz = 0.01 seconds
        
        # Extract segment from 3ms for 4ms duration (3-7ms)
        segment = processor._extract_segment(audio_data, 0.003, 0.004)  # start at 3ms, duration 4ms
        
        # Should get samples 3-6 (0-indexed, end exclusive)
        expected = np.array([4, 5, 6, 7])
        np.testing.assert_array_equal(segment, expected)

    def test_processing_recommendations(self):
        """Test processing recommendations generation."""
        config = {'sample_rate': 44100}
        processor = QuestionProcessor(config)
        
        # No questions
        recommendations = processor.get_processing_recommendations([])
        assert not recommendations['has_questions']
        assert recommendations['recommended_mode'] == 'standard'
        
        # Heavy questions (simulated)
        # Create enough segments to trigger question_heavy mode
        question_segments = [(i * 20, i * 20 + 10) for i in range(10)]  # 10 segments of 10 seconds each
        recommendations = processor.get_processing_recommendations(question_segments)
        assert recommendations['has_questions']
        assert recommendations['recommended_mode'] in ['question_heavy', 'question_moderate', 'question_light']


class TestAdaptiveAudioProcessor:
    """Test AdaptiveAudioProcessor component."""
    
    def test_initialization(self):
        """Test basic initialization."""
        config = {
            'sample_rate': 44100,
            'gentle_noise_reduction': 0.3,
            'standard_noise_reduction': 0.6
        }
        processor = AdaptiveAudioProcessor(config)
        
        assert processor.sample_rate == 44100
        assert processor.gentle_noise_reduction == 0.3
        assert processor.standard_noise_reduction == 0.6

    def test_question_mask_creation(self):
        """Test creation of question masks."""
        config = {'sample_rate': 1000}
        processor = AdaptiveAudioProcessor(config)
        
        # Set question segments
        processor.question_segments = [(1.0, 3.0), (5.0, 7.0)]
        
        # Create mask for 10 seconds of audio
        mask = processor._create_question_mask(10000)
        
        # Check that question regions are marked
        assert np.all(mask[1000:3000])  # First question segment
        assert np.all(mask[5000:7000])  # Second question segment
        assert not np.any(mask[0:1000])  # Before first segment
        assert not np.any(mask[3000:5000])  # Between segments
        assert not np.any(mask[7000:])  # After last segment

    def test_question_buffer_mask(self):
        """Test creation of question buffer masks."""
        config = {'sample_rate': 1000}
        processor = AdaptiveAudioProcessor(config)
        
        # Set question segments
        processor.question_segments = [(5.0, 7.0)]  # One segment in middle
        
        # Create buffer mask
        mask = processor._create_question_buffer_mask(15000)
        
        # Should include 2-second buffer around the 5-7 second segment
        # So should cover roughly 3-9 seconds (3000-9000 samples)
        assert np.any(mask[3000:9000])  # Buffer region should be marked
        assert not np.any(mask[0:2000])  # Well before buffer
        assert not np.any(mask[10000:])  # Well after buffer

    def test_gentle_noise_reduction(self):
        """Test gentle noise reduction."""
        config = {'sample_rate': 44100}
        processor = AdaptiveAudioProcessor(config)
        
        # Create test audio with some noise
        audio_data = np.random.randn(1000) * 0.1  # Low-level noise
        original_rms = np.sqrt(np.mean(audio_data**2))
        
        # Apply gentle noise reduction
        processed = processor._gentle_noise_reduction(audio_data)
        processed_rms = np.sqrt(np.mean(processed**2))
        
        # Should reduce noise level
        assert processed_rms <= original_rms
        # But not too aggressively
        assert processed_rms > original_rms * 0.5

    def test_amplify_segment_with_clipping_protection(self):
        """Test segment amplification with clipping protection."""
        config = {'sample_rate': 44100}
        processor = AdaptiveAudioProcessor(config)
        
        # Create test segment near clipping level
        segment = np.array([0.8, -0.9, 0.7, -0.6])
        
        # Amplify by 6dB (should double amplitude)
        amplified = processor._amplify_segment(segment, 6.0)
        
        # Should be amplified but not clipped
        assert np.max(np.abs(amplified)) <= 1.0  # No hard clipping
        assert np.max(np.abs(amplified)) > np.max(np.abs(segment))  # But amplified

    def test_soft_clipping(self):
        """Test soft clipping function."""
        config = {'sample_rate': 44100}
        processor = AdaptiveAudioProcessor(config)
        
        # Test with values that would clip
        audio_data = np.array([-2.0, -1.5, 0.0, 1.5, 2.0])
        clipped = processor._soft_clip(audio_data)
        
        # Should be within [-1, 1] range
        assert np.all(np.abs(clipped) <= 1.0)
        # Should preserve sign
        assert np.all(np.sign(clipped) == np.sign(audio_data))

    def test_processing_with_questions(self):
        """Test full processing with question segments."""
        config = {'sample_rate': 1000}
        processor = AdaptiveAudioProcessor(config)
        
        # Create test audio
        audio_data = np.random.randn(5000) * 0.1  # 5 seconds
        question_segments = [(1.0, 2.0), (3.0, 4.0)]
        
        # Process
        processed = processor.process_with_question_preservation(audio_data, question_segments)
        
        # Should return same length
        assert len(processed) == len(audio_data)
        # Should be processed (different from input)
        assert not np.array_equal(processed, audio_data)

    def test_processing_statistics(self):
        """Test processing statistics calculation."""
        config = {'sample_rate': 44100}
        processor = AdaptiveAudioProcessor(config)
        
        # Set up some question segments
        processor.question_segments = [(1.0, 3.0)]
        
        # Create test audio
        original = np.random.randn(44100) * 0.1  # 1 second
        processed = original * 1.5  # Simulated processing
        
        stats = processor.get_processing_statistics(original, processed)
        
        # Check required fields
        assert 'original_rms' in stats
        assert 'processed_rms' in stats
        assert 'rms_change_db' in stats
        assert 'question_segments' in stats
        assert 'total_question_time' in stats
        assert 'question_percentage' in stats
        
        # Values should be reasonable
        assert stats['question_segments'] == 1
        assert stats['total_question_time'] == 2.0  # 3.0 - 1.0
        assert stats['original_rms'] > 0
        assert stats['processed_rms'] > 0

    def test_content_type_analysis(self):
        """Test content type analysis."""
        config = {'sample_rate': 44100}
        processor = AdaptiveAudioProcessor(config)
        
        # Test Q&A heavy content
        audio_data = np.random.randn(44100 * 60) * 0.1  # 1 minute
        question_segments = [(i * 5, i * 5 + 3) for i in range(6)]  # Many questions
        
        analysis = processor.analyze_content_type(audio_data, question_segments)
        
        assert 'content_type' in analysis
        assert 'recommended_mode' in analysis
        assert 'question_ratio' in analysis
        assert 'audio_quality' in analysis
        assert 'processing_recommendations' in analysis
        
        # Should detect high question ratio
        assert analysis['question_ratio'] > 0.1


class TestProcessingModeSelector:
    """Test ProcessingModeSelector UI component."""
    
    def test_initialization(self):
        """Test basic initialization."""
        selector = ProcessingModeSelector()
        
        # Should have predefined modes
        assert 'standard' in selector.modes
        assert 'question_friendly' in selector.modes
        assert 'lecture_mode' in selector.modes
        assert 'custom' in selector.modes
        
        # Each mode should have required fields
        for mode_key, mode_info in selector.modes.items():
            assert 'name' in mode_info
            assert 'description' in mode_info
            assert 'settings' in mode_info

    def test_processing_config_generation(self):
        """Test processing configuration generation."""
        selector = ProcessingModeSelector()
        
        # Test with standard settings
        settings = {
            'noise_reduction_strength': 0.6,
            'enable_amplification': True,
            'amplification_boost_db': 3.0,
            'preserve_questions': False
        }
        
        config = selector.get_processing_config(settings)
        
        # Should contain expected fields
        assert 'noise_reduction_strength' in config
        assert 'gentle_noise_reduction' in config
        assert 'standard_noise_reduction' in config
        assert 'enable_amplification' in config
        assert 'preserve_questions' in config
        assert 'sample_rate' in config
        
        # Values should be reasonable
        assert config['noise_reduction_strength'] == 0.6
        assert config['enable_amplification'] == True
        assert config['sample_rate'] == 44100

    def test_processing_intensity_calculation(self):
        """Test processing intensity calculation."""
        selector = ProcessingModeSelector()
        
        # Low intensity settings
        low_settings = {
            'noise_reduction_strength': 0.1,
            'enable_amplification': False,
            'speech_enhancement': False
        }
        low_intensity = selector._calculate_processing_intensity(low_settings)
        
        # High intensity settings
        high_settings = {
            'noise_reduction_strength': 0.9,
            'enable_amplification': True,
            'amplification_boost_db': 12.0,
            'speech_enhancement': True,
            'high_freq_boost_db': 6.0
        }
        high_intensity = selector._calculate_processing_intensity(high_settings)
        
        # High intensity should be greater than low intensity
        assert high_intensity > low_intensity
        # Both should be in valid range
        assert 0 <= low_intensity <= 1
        assert 0 <= high_intensity <= 1

    def test_processing_time_estimation(self):
        """Test processing time estimation."""
        selector = ProcessingModeSelector()
        
        # Basic settings
        basic_settings = {
            'noise_reduction_strength': 0.5
        }
        basic_time = selector._estimate_processing_time(basic_settings)
        
        # Complex settings
        complex_settings = {
            'noise_reduction_strength': 0.8,
            'speech_enhancement': True,
            'preserve_questions': True,
            'question_detection': True
        }
        complex_time = selector._estimate_processing_time(complex_settings)
        
        # Complex processing should take longer
        assert complex_time > basic_time
        # Times should be reasonable
        assert basic_time >= 1.0
        assert complex_time >= basic_time

    def test_quality_impact_estimation(self):
        """Test quality impact estimation."""
        selector = ProcessingModeSelector()
        
        # Gentle settings
        gentle_settings = {
            'noise_reduction_strength': 0.2,
            'gentle_processing': True,
            'preserve_questions': True
        }
        gentle_quality = selector._estimate_quality_impact(gentle_settings)
        
        # Aggressive settings
        aggressive_settings = {
            'noise_reduction_strength': 0.9,
            'gentle_processing': False,
            'preserve_questions': False
        }
        aggressive_quality = selector._estimate_quality_impact(aggressive_settings)
        
        # Gentle should preserve more quality
        assert gentle_quality > aggressive_quality
        # Both should be in valid range
        assert 50 <= gentle_quality <= 100
        assert 50 <= aggressive_quality <= 100

    def test_mode_settings_validation(self):
        """Test that all predefined modes have valid settings."""
        selector = ProcessingModeSelector()
        
        for mode_key, mode_info in selector.modes.items():
            if mode_key == 'custom':
                continue  # Custom mode has empty settings
            
            settings = mode_info['settings']
            
            # Should be able to generate config from settings
            config = selector.get_processing_config(settings)
            assert isinstance(config, dict)
            assert len(config) > 0
            
            # Should be able to calculate metrics
            intensity = selector._calculate_processing_intensity(settings)
            assert 0 <= intensity <= 1
            
            quality = selector._estimate_quality_impact(settings)
            assert 50 <= quality <= 100

    def test_custom_preset_management(self):
        """Test custom preset save/load functionality."""
        selector = ProcessingModeSelector()
        
        # Create test settings
        test_settings = {
            'noise_reduction_strength': 0.7,
            'enable_amplification': True,
            'custom_parameter': 'test_value'
        }
        
        # Save preset
        success = selector.save_custom_preset('test_preset', test_settings)
        assert success
        
        # Load preset
        loaded_settings = selector.load_custom_preset('test_preset')
        assert loaded_settings is not None
        assert loaded_settings == test_settings
        
        # Check available presets
        presets = selector.get_available_presets()
        assert 'test_preset' in presets


if __name__ == "__main__":
    pytest.main([__file__, "-v"])