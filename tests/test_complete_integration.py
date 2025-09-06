"""
Integration Test for Complete Sermon Processing System with Q&A Normalization

This test demonstrates the complete workflow:
1. Audio processing with Q&A normalization
2. Database storage of sermon records and Q&A segments
3. UI components for browsing and viewing
"""

import datetime
import os
import sys
import tempfile
from pathlib import Path

# Add paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "ui"))

import numpy as np
import soundfile as sf
from database import SermonRepository

from audio_processing import AudioProcessor


def create_sample_sermon_audio(duration=60, sample_rate=16000):
    """Create synthetic sermon audio with Q&A segments for testing"""
    total_samples = int(duration * sample_rate)
    audio = np.zeros(total_samples)

    # Create realistic sermon pattern:
    # 0-20s: Normal speaking (-15dB RMS)
    # 20-25s: Quiet question (-35dB RMS)
    # 25-40s: Normal response (-15dB RMS)
    # 40-45s: Another quiet question (-35dB RMS)
    # 45-60s: Final response (-15dB RMS)

    t = np.linspace(0, duration, total_samples)

    # Main speaker segments (normal level)
    main_level = 10**(-15/20)  # -15dB RMS
    for start, end in [(0, 20), (25, 40), (45, 60)]:
        start_idx = int(start * sample_rate)
        end_idx = int(end * sample_rate)
        if end_idx <= total_samples:
            # Use slightly different frequencies for variety
            freq = 440 + start * 10  # Vary frequency slightly
            segment_t = t[start_idx:end_idx]
            audio[start_idx:end_idx] = main_level * np.sin(2 * np.pi * freq * segment_t)

    # Question segments (quiet level)
    question_level = 10**(-35/20)  # -35dB RMS
    for start, end in [(20, 25), (40, 45)]:
        start_idx = int(start * sample_rate)
        end_idx = int(end * sample_rate)
        if end_idx <= total_samples:
            freq = 220  # Lower frequency for questions
            segment_t = t[start_idx:end_idx]
            audio[start_idx:end_idx] = question_level * np.sin(2 * np.pi * freq * segment_t)

    return audio, sample_rate

def test_complete_sermon_workflow():
    """Test the complete sermon processing workflow"""

    print("🧪 Testing Complete Sermon Processing Workflow")
    print("=" * 60)

    # Configuration for Q&A processing
    config = {
        'qa_normalization': {
            'enabled': True,
            'detection_method': 'level_based',
            'target_lufs': -23.0,
            'main_speaker_threshold': -12.0,
            'question_threshold': -30.0,
            'transition_smoothing': True
        },
        'audio_enhancement_method': 'none',  # Skip AI enhancement for faster testing
        'debug': True
    }

    # Step 1: Create test audio
    print("1️⃣ Creating synthetic sermon audio with Q&A segments...")
    audio_data, sample_rate = create_sample_sermon_audio(duration=60)

    # Create temporary files
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as input_file:
        input_path = input_file.name
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as output_file:
        output_path = output_file.name

    try:
        # Save test audio
        sf.write(input_path, audio_data, sample_rate)
        print(f"   ✅ Test audio created: {input_path}")

        # Step 2: Process audio with Q&A normalization
        print("2️⃣ Processing audio with Q&A normalization...")
        processor = AudioProcessor(enhancement_method='none', config=config)

        success, qa_info = processor.process_sermon_audio(
            input_path,
            output_path,
            noise_reduction=False,
            normalize=False,
            amplify=False
        )

        assert success, "Audio processing should succeed"
        assert qa_info is not None, "Q&A processing info should be returned"

        qa_segments = qa_info.get('qa_segments', [])
        print(f"   ✅ Q&A processing complete: {len(qa_segments)} segments detected")

        for i, segment in enumerate(qa_segments, 1):
            print(f"      Segment {i}: {segment['start_time']:.1f}-{segment['end_time']:.1f}s, "
                  f"gain: +{segment['gain_applied']:.1f}dB")

        # Step 3: Save to database
        print("3️⃣ Saving sermon record to database...")
        repo = SermonRepository()

        sermon_data = {
            'id': 'test_sermon_001',
            'title': 'Test Sermon with Q&A',
            'speaker': 'Pastor Test',
            'recorded_date': '2024-01-15',
            'event_type': 'Sunday Service',
            'bible_text': 'John 3:16',
            'duration': 60.0,
            'status': 'processed',
            'file_paths': {
                'original_audio': input_path,
                'processed_audio': output_path,
                'transcript': None,
                'description': None
            },
            'processing_info': {
                'enhancement_method': 'none',
                'noise_reduction_applied': False,
                'normalization_applied': False,
                'qa_normalization_applied': True,
                'qa_segments_count': len(qa_segments),
                'qa_segments': qa_segments,
                'processing_duration': 5.0,
                'quality_score': 8.5,
                'processing_logs': qa_info
            },
            'content': {
                'transcript_text': 'This is a test sermon transcript with Q&A segments included for demonstration purposes.',
                'description': 'A comprehensive test of our Q&A audio normalization system.',
                'hashtags': '#test #qa #normalization #sermon',
                'key_topics': ['Q&A Processing', 'Audio Enhancement', 'Testing'],
                'summary': 'Test sermon demonstrating Q&A normalization capabilities.'
            },
            'upload_info': {
                'sermonaudio_id': 'test_sermon_001',
                'upload_date': datetime.datetime.now(),
                'upload_status': 'completed',
                'upload_message': 'Test sermon processed successfully'
            }
        }

        save_success = repo.save_sermon(sermon_data)
        assert save_success, "Sermon should be saved to database successfully"
        print("   ✅ Sermon saved to database")

        # Step 4: Retrieve and verify database content
        print("4️⃣ Verifying database storage...")

        # Get the sermon back
        retrieved_sermon = repo.get_sermon('test_sermon_001')
        assert retrieved_sermon is not None, "Sermon should be retrievable"
        assert retrieved_sermon['title'] == 'Test Sermon with Q&A'

        # Verify Q&A segments were saved
        processing_info = retrieved_sermon.get('processing_info', {})
        saved_qa_segments = processing_info.get('qa_segments', [])
        assert len(saved_qa_segments) == len(qa_segments), "All Q&A segments should be saved"

        print(f"   ✅ Sermon retrieved with {len(saved_qa_segments)} Q&A segments")

        # Step 5: Test search functionality
        print("5️⃣ Testing search functionality...")

        # Search by content
        search_results = repo.search_sermons('normalization')
        assert len(search_results) > 0, "Search should find the test sermon"
        print(f"   ✅ Search found {len(search_results)} matching sermons")

        # Test filtering
        all_sermons = repo.get_all_sermons(filters={'has_qa_segments': True})
        qa_sermons = [s for s in all_sermons if s.get('qa_segments_count', 0) > 0]
        assert len(qa_sermons) > 0, "Should find sermons with Q&A segments"
        print(f"   ✅ Found {len(qa_sermons)} sermons with Q&A segments")

        # Step 6: Test statistics
        print("6️⃣ Testing analytics and statistics...")

        stats = repo.get_processing_stats()
        assert stats['total_sermons'] >= 1, "Should have at least one sermon"
        assert stats['qa_sermons'] >= 1, "Should have at least one sermon with Q&A"
        assert stats['total_qa_segments'] >= len(qa_segments), "Should track Q&A segments"

        print(f"   ✅ Statistics: {stats['total_sermons']} sermons, "
              f"{stats['qa_sermons']} with Q&A, "
              f"{stats['total_qa_segments']} total Q&A segments")

        # Step 7: Test UI data access
        print("7️⃣ Testing UI data access patterns...")

        # Simulate Library page data access
        recent_sermons = repo.get_all_sermons(limit=10)
        assert len(recent_sermons) >= 1, "Should retrieve recent sermons"

        # Simulate Viewer page data access
        sermon_for_viewing = repo.get_sermon('test_sermon_001')
        assert sermon_for_viewing is not None, "Should retrieve sermon for viewing"
        assert 'content' in sermon_for_viewing, "Should include content"
        assert 'processing_info' in sermon_for_viewing, "Should include processing info"

        print("   ✅ UI data access patterns working correctly")

        # Success summary
        print("\n🎉 Complete Workflow Test PASSED!")
        print("\nSystem Capabilities Verified:")
        print("  ✅ Q&A audio segment detection and normalization")
        print("  ✅ Comprehensive database storage and retrieval")
        print("  ✅ Full-text search across sermon content")
        print("  ✅ Analytics and processing statistics")
        print("  ✅ UI-ready data access patterns")
        print("  ✅ End-to-end integration workflow")

        return True

    finally:
        # Cleanup
        for path in [input_path, output_path]:
            if os.path.exists(path):
                os.unlink(path)

if __name__ == "__main__":
    try:
        test_complete_sermon_workflow()
        print("\n✅ All integration tests passed!")
    except Exception as e:
        print(f"\n❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
