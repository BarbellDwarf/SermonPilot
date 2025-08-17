import os
import pytest

def test_no_compression():
    """Test that would use audio file - skip if no test audio available"""
    input_path = "tests/2024-12-12 - Zechariah - Mark Hogan (1212241923147168).mp3"
    
    if not os.path.exists(input_path):
        pytest.skip("Test audio file not available - audio files excluded from repository")
        
    output_path = "tests/test_no_compression_output.mp3"
    
# Add src directory to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

    from audio_processing import process_sermon_audio
    result = process_sermon_audio(
        input_path,
        output_path,
        noise_reduction=True,
        amplify=False,
        normalize=True,
        gain_db=0.0,
        target_level_db=-21.0
    )
    print(f"Test no compression result: {result}")
    print(f"Output file: {output_path}")

if __name__ == "__main__":
    test_no_compression()
