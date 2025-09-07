"""
Test the new audio editing UI components

Tests for AudioWaveformViewer, AudioEditor, and AudioPreview components.
"""

import pytest
import numpy as np
import sys
from pathlib import Path

# Add project paths for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "ui"))

try:
    from ui.components.audio_waveform import AudioWaveformViewer
    from ui.components.audio_editor import AudioEditor
    from ui.components.audio_preview import AudioPreview
except ImportError as e:
    pytest.skip(f"Audio editing components not available: {e}", allow_module_level=True)


class TestAudioWaveformViewer:
    """Test AudioWaveformViewer component."""
    
    def test_initialization(self):
        """Test basic initialization."""
        # Create test audio data
        sample_rate = 44100
        duration = 2.0  # 2 seconds
        samples = int(sample_rate * duration)
        audio_data = np.sin(2 * np.pi * 440 * np.linspace(0, duration, samples))  # 440 Hz sine wave
        
        viewer = AudioWaveformViewer(audio_data, sample_rate)
        
        assert viewer.sample_rate == sample_rate
        assert len(viewer.audio_data) == samples
        assert viewer.duration == duration
        assert len(viewer.segments) == 0

    def test_segment_management(self):
        """Test segment addition and management."""
        audio_data = np.random.randn(44100)  # 1 second of random audio
        viewer = AudioWaveformViewer(audio_data, 44100)
        
        # Add valid segment
        viewer.add_segment(0.5, 0.8, "remove")
        assert len(viewer.segments) == 1
        assert viewer.segments[0] == (0.5, 0.8, "remove")
        
        # Add another segment
        viewer.add_segment(0.1, 0.3, "amplify")
        assert len(viewer.segments) == 2
        
        # Segments should be sorted by start time
        segments = viewer.get_segments()
        assert segments[0][0] <= segments[1][0]  # First segment starts before second
        
        # Remove segment
        viewer.remove_segment(0)
        assert len(viewer.segments) == 1
        
        # Clear all segments
        viewer.clear_segments()
        assert len(viewer.segments) == 0

    def test_invalid_segments(self):
        """Test handling of invalid segments."""
        audio_data = np.random.randn(44100)  # 1 second of audio
        viewer = AudioWaveformViewer(audio_data, 44100)
        
        # Try to add invalid segments
        original_count = len(viewer.segments)
        
        # End before start
        viewer.add_segment(0.8, 0.5, "remove")
        assert len(viewer.segments) == original_count
        
        # Start before 0
        viewer.add_segment(-0.1, 0.5, "remove")
        assert len(viewer.segments) == original_count
        
        # End after duration
        viewer.add_segment(0.5, 2.0, "remove")
        assert len(viewer.segments) == original_count

    def test_audio_info(self):
        """Test audio information calculation."""
        # Create test audio with known properties
        audio_data = np.array([0.5, -0.3, 0.8, -0.1])
        viewer = AudioWaveformViewer(audio_data, 1000)
        
        info = viewer.get_audio_info()
        
        assert info['duration'] == 4.0 / 1000  # 4 samples at 1000 Hz
        assert info['sample_rate'] == 1000
        assert info['samples'] == 4
        assert info['channels'] == 1
        assert info['max_amplitude'] == 0.8
        
        # Check RMS calculation
        expected_rms = np.sqrt(np.mean(audio_data**2))
        assert abs(info['rms_level'] - expected_rms) < 1e-6


class TestAudioEditor:
    """Test AudioEditor component."""
    
    def test_initialization(self):
        """Test basic initialization."""
        editor = AudioEditor()
        assert editor.editing_mode == "select"
        assert editor.selected_region is None

    def test_remove_region(self):
        """Test audio region removal."""
        editor = AudioEditor()
        
        # Create test audio: [1, 2, 3, 4, 5]
        audio_data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        sample_rate = 5  # 1 second, 1 sample per 0.2 seconds
        
        # Remove middle section (samples 1-3, which is 2, 3, 4)
        result = editor.apply_edit(audio_data, sample_rate, 0.2, 0.8, "remove")
        
        # Should have [1, 5] remaining
        expected = np.array([1.0, 5.0])
        np.testing.assert_array_equal(result, expected)

    def test_amplify_region(self):
        """Test audio region amplification."""
        editor = AudioEditor()
        
        # Create test audio
        audio_data = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        sample_rate = 5
        
        # Amplify middle section by 6dB (factor of ~2)
        # 0.4 to 0.8 seconds = samples 2 to 3 (indices 2 and 3)
        result = editor.apply_edit(
            audio_data, sample_rate, 0.4, 0.8, "amplify", 
            volume_boost_db=6.0
        )
        
        # Check that the correct samples are amplified
        assert result[0] == 0.1  # First sample unchanged
        assert result[1] == 0.2  # Second sample unchanged
        # Samples 2 and 3 should be amplified
        assert result[2] > 0.59 and result[2] < 0.61  # Sample 2: 0.3 * ~2
        assert result[3] > 0.79 and result[3] < 0.81  # Sample 3: 0.4 * ~2
        assert result[4] == 0.5  # Fifth sample unchanged

    def test_fade_effects(self):
        """Test fade in/out effects."""
        editor = AudioEditor()
        
        # Create test audio - constant level
        audio_data = np.ones(100) * 0.5  # 100 samples at 0.5 amplitude
        sample_rate = 100  # 1 second
        
        # Apply fade in for first 0.2 seconds
        result = editor.apply_edit(
            audio_data, sample_rate, 0.0, 0.2, "fade_in",
            fade_duration=0.2
        )
        
        # Check that fade starts at 0 and reaches full amplitude
        assert result[0] == 0.0
        assert result[-1] == 0.5  # Last sample should be unchanged
        
        # Check that fade is gradual
        assert result[10] < result[19]  # Should be increasing

    def test_split_audio(self):
        """Test audio splitting."""
        editor = AudioEditor()
        
        # Create test audio
        audio_data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        sample_rate = 5
        
        # Split at 0.6 seconds (sample 3)
        part1, part2 = editor.split_audio(audio_data, 0.6, sample_rate)
        
        expected_part1 = np.array([1.0, 2.0, 3.0])
        expected_part2 = np.array([4.0, 5.0])
        
        np.testing.assert_array_equal(part1, expected_part1)
        np.testing.assert_array_equal(part2, expected_part2)

    def test_editing_summary(self):
        """Test editing summary calculation."""
        editor = AudioEditor()
        
        segments = [
            (0.0, 1.0, "remove"),
            (2.0, 3.0, "amplify"),
            (4.0, 5.5, "remove")
        ]
        
        summary = editor.get_editing_summary(segments)
        
        assert summary["total_segments"] == 3
        assert summary["total_edited_duration"] == 3.5  # 1 + 1 + 1.5
        assert summary["actions"]["remove"]["count"] == 2
        assert summary["actions"]["amplify"]["count"] == 1
        assert summary["actions"]["remove"]["duration"] == 2.5  # 1 + 1.5
        assert summary["actions"]["amplify"]["duration"] == 1.0


class TestAudioPreview:
    """Test AudioPreview component."""
    
    def test_initialization(self):
        """Test basic initialization."""
        preview = AudioPreview()
        assert len(preview.temp_files) == 0
        assert preview.temp_dir.exists()

    def test_extract_region(self):
        """Test audio region extraction."""
        preview = AudioPreview()
        
        # Create test audio
        audio_data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        sample_rate = 5
        
        # Extract middle region (0.4 to 0.8 seconds = samples 2-3)
        region = preview.extract_region(audio_data, sample_rate, 0.4, 0.8)
        
        expected = np.array([3.0, 4.0])
        np.testing.assert_array_equal(region, expected)

    def test_extract_region_bounds(self):
        """Test region extraction with boundary conditions."""
        preview = AudioPreview()
        
        audio_data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        sample_rate = 5
        
        # Test with invalid bounds
        region = preview.extract_region(audio_data, sample_rate, -0.5, 0.2)
        expected = np.array([1.0])  # Should start from 0
        np.testing.assert_array_equal(region, expected)
        
        # Test with end beyond audio
        region = preview.extract_region(audio_data, sample_rate, 0.8, 2.0)
        expected = np.array([5.0])  # Should end at audio end
        np.testing.assert_array_equal(region, expected)
        
        # Test with invalid order (start > end)
        region = preview.extract_region(audio_data, sample_rate, 0.8, 0.2)
        expected = np.array([])  # Should return empty
        np.testing.assert_array_equal(region, expected)

    def test_audio_statistics(self):
        """Test audio statistics calculation."""
        preview = AudioPreview()
        
        # Create test audio with known properties
        audio_data = np.array([0.5, -0.3, 0.8, -0.1])
        stats = preview.get_audio_statistics(audio_data)
        
        assert stats['max_amplitude'] == 0.8
        
        expected_rms = np.sqrt(np.mean(audio_data**2))
        assert abs(stats['rms_level'] - expected_rms) < 1e-6
        
        expected_peak_to_rms = 0.8 / expected_rms
        assert abs(stats['peak_to_rms_ratio'] - expected_peak_to_rms) < 1e-6
        
        expected_dynamic_range = 0.8 - (-0.3)  # max - min
        assert abs(stats['dynamic_range'] - expected_dynamic_range) < 1e-6

    def test_cleanup(self):
        """Test temporary file cleanup."""
        preview = AudioPreview()
        
        # Add some fake temp files to the list
        fake_files = ["temp1.wav", "temp2.wav"]
        preview.temp_files = fake_files.copy()
        
        # Cleanup should clear the list
        preview.cleanup_temp_files()
        assert len(preview.temp_files) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])