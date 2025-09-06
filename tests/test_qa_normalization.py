"""
Test Q&A Audio Normalization functionality
"""

import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from audio_processing import AudioProcessor
from qa_normalizer import QANormalizer, QASegment


def create_test_audio_with_qa(sample_rate=16000, duration=30):
    """
    Create synthetic audio that simulates a Q&A session:
    - First 10 seconds: normal speaker level (-15dB RMS)
    - Next 5 seconds: quiet question (-35dB RMS) 
    - Next 10 seconds: normal speaker level (-15dB RMS)
    - Last 5 seconds: quiet question (-35dB RMS)
    """
    total_samples = int(duration * sample_rate)
    audio = np.zeros(total_samples)

    # Generate sine wave components
    freq1 = 440  # A note for main speaker
    freq2 = 220  # Lower note for questions

    t = np.linspace(0, duration, total_samples)

    # Main speaker segments (0-10s, 15-25s)
    main_level = 10**(-15/20)  # -15dB RMS
    for start, end in [(0, 10), (15, 25)]:
        start_idx = int(start * sample_rate)
        end_idx = int(end * sample_rate)
        segment_t = t[start_idx:end_idx]
        audio[start_idx:end_idx] = main_level * np.sin(2 * np.pi * freq1 * segment_t)

    # Question segments (10-15s, 25-30s)
    question_level = 10**(-35/20)  # -35dB RMS
    for start, end in [(10, 15), (25, 30)]:
        start_idx = int(start * sample_rate)
        end_idx = int(end * sample_rate)
        segment_t = t[start_idx:end_idx]
        audio[start_idx:end_idx] = question_level * np.sin(2 * np.pi * freq2 * segment_t)

    return audio, sample_rate


def test_qa_segment_dataclass():
    """Test QASegment dataclass functionality"""
    segment = QASegment(
        start_time=10.0,
        end_time=15.0,
        segment_type='question',
        confidence=0.8,
        audio_level_db=-35.0,
        gain_applied=20.0
    )

    assert segment.duration() == 5.0
    assert segment.segment_type == 'question'

    # Test serialization
    segment_dict = segment.to_dict()
    assert segment_dict['start_time'] == 10.0
    assert segment_dict['gain_applied'] == 20.0


def test_qa_normalizer_init():
    """Test QANormalizer initialization with different configs"""

    # Basic config
    config = {
        'qa_normalization': {
            'enabled': True,
            'detection_method': 'level_based',
            'target_lufs': -23.0,
            'main_speaker_threshold': -12.0,
            'question_threshold': -30.0
        }
    }

    normalizer = QANormalizer(config)
    assert normalizer.detection_method == 'level_based'
    assert normalizer.target_lufs == -23.0
    assert normalizer.main_speaker_threshold_db == -12.0
    assert normalizer.question_threshold_db == -30.0

    # Test with minimal config (should use defaults)
    minimal_config = {'qa_normalization': {}}
    normalizer2 = QANormalizer(minimal_config)
    assert normalizer2.target_lufs == -23.0  # Default value


def test_qa_detection_synthetic_audio():
    """Test Q&A detection on synthetic audio with known Q&A segments"""

    config = {
        'qa_normalization': {
            'enabled': True,
            'detection_method': 'level_based',
            'target_lufs': -23.0,
            'main_speaker_threshold': -12.0,
            'question_threshold': -30.0
        }
    }

    # Create test audio
    audio_data, sample_rate = create_test_audio_with_qa()

    # Save to temporary file
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
        temp_path = temp_file.name

    try:
        sf.write(temp_path, audio_data, sample_rate)

        # Process with Q&A normalizer
        normalizer = QANormalizer(config)
        normalized_audio, _ = normalizer.process_audio(temp_path)

        # Check that segments were detected
        segments = normalizer.get_segments()
        assert len(segments) > 0, "No Q&A segments detected"

        # Check processing stats
        stats = normalizer.get_processing_stats()
        assert stats['total_segments'] > 0
        assert stats['detection_method'] == 'level_based'

        print(f"✅ Detected {len(segments)} Q&A segments")
        for i, segment in enumerate(segments):
            print(f"   Segment {i+1}: {segment['start_time']:.1f}-{segment['end_time']:.1f}s, "
                  f"gain: +{segment['gain_applied']:.1f}dB")

    finally:
        # Clean up
        os.unlink(temp_path)


def test_audio_processor_with_qa():
    """Test AudioProcessor integration with Q&A normalization"""

    config = {
        'qa_normalization': {
            'enabled': True,
            'detection_method': 'level_based',
            'target_lufs': -23.0,
            'main_speaker_threshold': -12.0,
            'question_threshold': -30.0
        }
    }

    # Create test audio
    audio_data, sample_rate = create_test_audio_with_qa()

    # Create temporary input and output files
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_input:
        input_path = temp_input.name
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_output:
        output_path = temp_output.name

    try:
        # Save test audio
        sf.write(input_path, audio_data, sample_rate)

        # Process with AudioProcessor
        processor = AudioProcessor(enhancement_method='none', config=config)
        success, qa_info = processor.process_sermon_audio(
            input_path,
            output_path,
            noise_reduction=False,  # Skip noise reduction for faster test
            normalize=False,  # Skip normalization for cleaner test
            amplify=False  # Skip amplification for cleaner test
        )

        assert success, "Audio processing failed"
        assert qa_info is not None, "Q&A processing info not returned"
        assert 'qa_segments' in qa_info, "Q&A segments not in processing info"

        # Check that output file was created
        assert os.path.exists(output_path), "Output file not created"

        # Verify output file is readable
        output_audio, output_sr = sf.read(output_path)
        assert len(output_audio) > 0, "Output file is empty"

        print("✅ AudioProcessor Q&A integration successful")
        print(f"   Processed {qa_info.get('total_segments', 0)} segments")
        print(f"   Average gain applied: {qa_info.get('average_gain_applied', 0):.1f}dB")

    finally:
        # Clean up
        for path in [input_path, output_path]:
            if os.path.exists(path):
                os.unlink(path)


def test_qa_disabled():
    """Test that Q&A processing can be properly disabled"""

    config = {
        'qa_normalization': {
            'enabled': False  # Explicitly disabled
        }
    }

    # Create test audio
    audio_data, sample_rate = create_test_audio_with_qa()

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_input:
        input_path = temp_input.name
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_output:
        output_path = temp_output.name

    try:
        sf.write(input_path, audio_data, sample_rate)

        processor = AudioProcessor(enhancement_method='none', config=config)
        success, qa_info = processor.process_sermon_audio(
            input_path,
            output_path,
            noise_reduction=False,
            normalize=False,
            amplify=False
        )

        assert success, "Audio processing failed"
        # Q&A info should be None when disabled
        assert qa_info is None, "Q&A processing should be disabled"

        print("✅ Q&A processing properly disabled")

    finally:
        for path in [input_path, output_path]:
            if os.path.exists(path):
                os.unlink(path)


if __name__ == "__main__":
    """Run tests directly"""

    print("🧪 Testing Q&A Audio Normalization")
    print("=" * 50)

    try:
        test_qa_segment_dataclass()
        print("✅ QASegment dataclass test passed")

        test_qa_normalizer_init()
        print("✅ QANormalizer initialization test passed")

        test_qa_detection_synthetic_audio()
        print("✅ Q&A detection test passed")

        test_audio_processor_with_qa()
        print("✅ AudioProcessor Q&A integration test passed")

        test_qa_disabled()
        print("✅ Q&A disabled test passed")

        print("\n🎉 All Q&A normalization tests passed!")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
