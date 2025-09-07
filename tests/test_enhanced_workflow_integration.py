"""
Integration tests for the enhanced audio editing workflow

Tests the complete workflow from audio upload to processing configuration.
"""

import pytest
import numpy as np
import tempfile
import sys
from pathlib import Path

# Add project paths for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "ui"))

try:
    from ui.components.audio_waveform import AudioWaveformViewer
    from ui.components.audio_editor import AudioEditor
    from ui.components.audio_preview import AudioPreview
    from ui.components.processing_modes import ProcessingModeSelector
    from src.audio.question_processor import QuestionProcessor
    from src.audio.adaptive_processor import AdaptiveAudioProcessor
    COMPONENTS_AVAILABLE = True
except ImportError as e:
    pytest.skip(f"Audio editing components not available: {e}", allow_module_level=True)
    COMPONENTS_AVAILABLE = False


class TestEnhancedWorkflowIntegration:
    """Test the complete enhanced audio editing workflow."""
    
    def setup_method(self):
        """Set up test audio data for each test."""
        # Create test audio: 10 seconds of mixed content
        self.sample_rate = 44100
        self.duration = 10.0
        self.samples = int(self.sample_rate * self.duration)
        
        # Create realistic test audio with speech-like characteristics
        t = np.linspace(0, self.duration, self.samples)
        
        # Base signal: mix of frequencies typical of speech
        speech_freq1 = 150  # Fundamental frequency
        speech_freq2 = 300  # First harmonic
        speech_freq3 = 450  # Second harmonic
        
        audio_signal = (
            0.3 * np.sin(2 * np.pi * speech_freq1 * t) +
            0.2 * np.sin(2 * np.pi * speech_freq2 * t) +
            0.1 * np.sin(2 * np.pi * speech_freq3 * t)
        )
        
        # Add some noise
        noise = np.random.randn(self.samples) * 0.05
        
        # Add silent sections (pauses)
        audio_signal[int(3 * self.sample_rate):int(3.5 * self.sample_rate)] *= 0.1  # Pause at 3-3.5s
        audio_signal[int(7 * self.sample_rate):int(7.5 * self.sample_rate)] *= 0.1  # Pause at 7-7.5s
        
        # Combine signal and noise
        self.audio_data = audio_signal + noise
        
        # Normalize to [-1, 1]
        max_val = np.max(np.abs(self.audio_data))
        if max_val > 0:
            self.audio_data = self.audio_data / max_val * 0.8  # Leave some headroom

    def test_complete_workflow_integration(self):
        """Test the complete workflow from audio analysis to processing configuration."""
        
        # Step 1: Initialize all components
        waveform_viewer = AudioWaveformViewer(self.audio_data, self.sample_rate)
        audio_editor = AudioEditor()
        audio_preview = AudioPreview()
        mode_selector = ProcessingModeSelector()
        question_processor = QuestionProcessor({'sample_rate': self.sample_rate})
        adaptive_processor = AdaptiveAudioProcessor({'sample_rate': self.sample_rate})
        
        # Step 2: Analyze audio quality
        issues = self._analyze_audio_quality(self.audio_data, self.sample_rate)
        assert isinstance(issues, list)  # Should return a list of issues
        
        # Step 3: Detect question segments
        question_segments = question_processor.detect_question_segments(self.audio_data)
        assert isinstance(question_segments, list)
        
        # Add detected segments to waveform viewer
        for start_time, end_time in question_segments:
            waveform_viewer.add_segment(start_time, end_time, 'question')
        
        # Step 4: Manual editing - add some edits
        waveform_viewer.add_segment(1.0, 2.0, 'amplify')  # Amplify 1-2 seconds
        waveform_viewer.add_segment(8.0, 9.0, 'remove')   # Remove 8-9 seconds
        
        segments = waveform_viewer.get_segments()
        assert len(segments) >= 2  # At least our manual edits
        
        # Step 5: Apply edits and create preview
        edited_audio = self._apply_workflow_edits(self.audio_data, self.sample_rate, segments)
        assert len(edited_audio) < len(self.audio_data)  # Should be shorter due to removal
        
        # Step 6: Generate processing configuration
        mode_settings = mode_selector.modes['question_friendly']['settings']
        processing_config = mode_selector.get_processing_config(mode_settings)
        
        assert 'noise_reduction_strength' in processing_config
        assert 'preserve_questions' in processing_config
        assert processing_config['preserve_questions'] == True  # Question-friendly mode
        
        # Step 7: Process with adaptive processor
        processed_audio = adaptive_processor.process_with_question_preservation(
            edited_audio, question_segments
        )
        assert len(processed_audio) == len(edited_audio)
        assert not np.array_equal(processed_audio, edited_audio)  # Should be modified
        
        # Step 8: Validate processing statistics
        stats = adaptive_processor.get_processing_statistics(edited_audio, processed_audio)
        assert 'original_rms' in stats
        assert 'processed_rms' in stats
        assert 'question_segments' in stats
        assert stats['question_segments'] == len(question_segments)

    def test_question_preservation_workflow(self):
        """Test workflow specifically focused on Q&A preservation."""
        
        # Initialize components
        question_processor = QuestionProcessor({'sample_rate': self.sample_rate})
        adaptive_processor = AdaptiveAudioProcessor({'sample_rate': self.sample_rate})
        
        # Detect questions
        question_segments = question_processor.detect_question_segments(self.audio_data)
        
        # Get processing recommendations
        recommendations = question_processor.get_processing_recommendations(question_segments)
        
        # Configure adaptive processor based on recommendations
        config = {
            'sample_rate': self.sample_rate,
            'gentle_noise_reduction': recommendations['noise_reduction_strength'] * 0.5,
            'standard_noise_reduction': recommendations['noise_reduction_strength'],
            'question_amplification_db': recommendations.get('amplify_questions', False) and 2.0 or 0.0
        }
        
        adaptive_processor = AdaptiveAudioProcessor(config)
        
        # Process with question preservation
        processed_audio = adaptive_processor.process_with_question_preservation(
            self.audio_data, question_segments
        )
        
        # Analyze results
        content_analysis = adaptive_processor.analyze_content_type(self.audio_data, question_segments)
        
        assert 'content_type' in content_analysis
        assert 'recommended_mode' in content_analysis
        assert 'question_ratio' in content_analysis
        assert content_analysis['question_ratio'] >= 0.0

    def test_processing_mode_integration(self):
        """Test integration between processing modes and audio processors."""
        
        mode_selector = ProcessingModeSelector()
        
        # Test each processing mode
        for mode_key, mode_info in mode_selector.modes.items():
            if mode_key == 'custom':
                continue  # Skip custom mode for this test
            
            settings = mode_info['settings']
            processing_config = mode_selector.get_processing_config(settings)
            
            # Create adaptive processor with mode configuration
            adaptive_processor = AdaptiveAudioProcessor(processing_config)
            
            # Create dummy question segments if mode preserves questions
            question_segments = [(2.0, 4.0), (6.0, 8.0)] if processing_config.get('preserve_questions') else []
            
            # Process audio
            try:
                processed_audio = adaptive_processor.process_with_question_preservation(
                    self.audio_data, question_segments
                )
                
                # Validate output
                assert len(processed_audio) == len(self.audio_data)
                assert isinstance(processed_audio, np.ndarray)
                
                # Check that processing had some effect (unless it's gentle mode)
                if processing_config.get('noise_reduction_strength', 0) > 0.1:
                    assert not np.allclose(processed_audio, self.audio_data, rtol=1e-3)
                
            except Exception as e:
                pytest.fail(f"Mode '{mode_key}' failed processing: {e}")

    def test_edit_application_workflow(self):
        """Test the complete edit application workflow."""
        
        waveform_viewer = AudioWaveformViewer(self.audio_data, self.sample_rate)
        audio_editor = AudioEditor()
        
        # Add various types of edits
        edits = [
            (0.5, 1.5, 'amplify'),   # Amplify first second
            (3.0, 3.5, 'remove'),    # Remove pause section
            (5.0, 6.0, 'fade_in'),   # Fade in
            (8.5, 9.5, 'fade_out'),  # Fade out
        ]
        
        for start, end, action in edits:
            waveform_viewer.add_segment(start, end, action)
        
        segments = waveform_viewer.get_segments()
        assert len(segments) == len(edits)
        
        # Apply edits step by step
        processed_audio = self.audio_data.copy()
        
        # Apply edits in reverse order to maintain indices for removal
        sorted_segments = sorted(segments, key=lambda x: x[0], reverse=True)
        
        for start_time, end_time, action in sorted_segments:
            processed_audio = audio_editor.apply_edit(
                processed_audio, self.sample_rate, start_time, end_time, action
            )
        
        # Validate results
        # Should be shorter due to removal
        assert len(processed_audio) < len(self.audio_data)
        
        # Should be different from original
        # (Compare only the overlapping portion for fairness)
        min_length = min(len(processed_audio), len(self.audio_data))
        assert not np.allclose(processed_audio[:min_length], self.audio_data[:min_length], rtol=1e-3)

    def test_preview_generation_workflow(self):
        """Test audio preview generation workflow."""
        
        audio_preview = AudioPreview()
        waveform_viewer = AudioWaveformViewer(self.audio_data, self.sample_rate)
        
        # Add some edits
        waveform_viewer.add_segment(2.0, 3.0, 'amplify')
        waveform_viewer.add_segment(7.0, 8.0, 'remove')
        
        segments = waveform_viewer.get_segments()
        
        # Test original preview creation
        original_file = audio_preview.create_preview_audio(self.audio_data, self.sample_rate)
        assert original_file is not None
        assert Path(original_file).exists()
        
        # Test edited preview creation
        edited_file = audio_preview.create_preview_with_edits(
            self.audio_data, self.sample_rate, segments
        )
        assert edited_file is not None
        assert Path(edited_file).exists()
        
        # Test statistics generation
        stats = audio_preview.get_audio_statistics(self.audio_data)
        assert 'max_amplitude' in stats
        assert 'rms_level' in stats
        assert 'dynamic_range' in stats
        assert stats['max_amplitude'] > 0
        assert stats['rms_level'] > 0
        
        # Cleanup
        audio_preview.cleanup_temp_files()

    def test_error_handling_workflow(self):
        """Test error handling in the complete workflow."""
        
        # Test with invalid audio data
        invalid_audio = np.array([])
        
        # Components should handle empty audio gracefully
        waveform_viewer = AudioWaveformViewer(invalid_audio, self.sample_rate)
        info = waveform_viewer.get_audio_info()
        assert info['duration'] == 0
        assert info['samples'] == 0
        
        # Question processor should handle empty audio
        question_processor = QuestionProcessor({'sample_rate': self.sample_rate})
        segments = question_processor.detect_question_segments(invalid_audio)
        assert isinstance(segments, list)
        assert len(segments) == 0
        
        # Adaptive processor should handle empty audio
        adaptive_processor = AdaptiveAudioProcessor({'sample_rate': self.sample_rate})
        processed = adaptive_processor.process_with_question_preservation(invalid_audio, [])
        assert len(processed) == 0

    def test_memory_efficiency_workflow(self):
        """Test that the workflow handles large audio files efficiently."""
        
        # Create larger test audio (1 minute)
        large_duration = 60.0
        large_samples = int(self.sample_rate * large_duration)
        large_audio = np.random.randn(large_samples) * 0.1
        
        # Test with chunked processing approach
        chunk_size = int(10 * self.sample_rate)  # 10-second chunks
        
        processed_chunks = []
        for i in range(0, len(large_audio), chunk_size):
            chunk = large_audio[i:i + chunk_size]
            
            # Process chunk
            adaptive_processor = AdaptiveAudioProcessor({'sample_rate': self.sample_rate})
            processed_chunk = adaptive_processor._gentle_noise_reduction(chunk)
            processed_chunks.append(processed_chunk)
        
        # Recombine chunks
        processed_large_audio = np.concatenate(processed_chunks)
        
        assert len(processed_large_audio) == len(large_audio)
        assert not np.array_equal(processed_large_audio, large_audio)

    def _analyze_audio_quality(self, audio_data, sample_rate):
        """Helper method to analyze audio quality."""
        issues = []
        
        # Check for clipping
        if np.max(np.abs(audio_data)) > 0.95:
            issues.append("Audio may be clipped")
        
        # Check for low volume
        rms = np.sqrt(np.mean(audio_data**2))
        if rms < 0.01:
            issues.append("Audio levels are very low")
        
        # Check for DC offset
        dc_offset = np.mean(audio_data)
        if abs(dc_offset) > 0.01:
            issues.append("DC offset detected")
        
        return issues

    def _apply_workflow_edits(self, audio_data, sample_rate, segments):
        """Helper method to apply workflow edits."""
        audio_editor = AudioEditor()
        processed_audio = audio_data.copy()
        
        # Apply edits in reverse order to maintain indices
        sorted_segments = sorted(segments, key=lambda x: x[0], reverse=True)
        
        for start_time, end_time, action in sorted_segments:
            processed_audio = audio_editor.apply_edit(
                processed_audio, sample_rate, start_time, end_time, action
            )
        
        return processed_audio


class TestWorkflowPerformance:
    """Test performance characteristics of the enhanced workflow."""
    
    def test_processing_time_estimation(self):
        """Test that processing time estimates are reasonable."""
        
        mode_selector = ProcessingModeSelector()
        
        # Test different modes
        for mode_key, mode_info in mode_selector.modes.items():
            if mode_key == 'custom':
                continue
            
            settings = mode_info['settings']
            estimated_time = mode_selector._estimate_processing_time(settings)
            
            # Should be reasonable (between 1x and 10x realtime)
            assert 1.0 <= estimated_time <= 10.0
            
            # More complex modes should take longer
            if settings.get('speech_enhancement'):
                assert estimated_time >= 2.0

    def test_quality_preservation_estimation(self):
        """Test quality preservation estimates."""
        
        mode_selector = ProcessingModeSelector()
        
        for mode_key, mode_info in mode_selector.modes.items():
            if mode_key == 'custom':
                continue
            
            settings = mode_info['settings']
            quality_score = mode_selector._estimate_quality_impact(settings)
            
            # Should be reasonable percentage
            assert 50 <= quality_score <= 100
            
            # Gentle modes should preserve more quality
            if 'gentle' in mode_key or settings.get('gentle_processing'):
                assert quality_score >= 80


if __name__ == "__main__":
    pytest.main([__file__, "-v"])