#!/usr/bin/env python3
"""
Test script for the new-sermon functionality.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def create_test_audio(duration=2):
    """Create a test audio file."""
    temp_file = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
    temp_file.close()

    # Create a simple audio file using ffmpeg
    cmd = [
        'ffmpeg', '-f', 'lavfi', '-i', f'sine=frequency=440:duration={duration}',
        '-c:a', 'mp3', temp_file.name, '-y'
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return temp_file.name
    except (subprocess.CalledProcessError, FileNotFoundError):
        # If ffmpeg fails, create a dummy file
        with open(temp_file.name, 'wb') as f:
            f.write(b'dummy audio content')
        return temp_file.name

def test_new_sermon_basic():
    """Test basic new-sermon functionality."""
    audio_file = create_test_audio()
    repo_root = Path(__file__).parent.parent

    try:
        # Test with dry-run and skip transcription for speed
        cmd = [
            sys.executable, str(repo_root / 'sermon_updater.py'), '--dry-run', 'new-sermon',
            audio_file, '--speaker', 'Test Speaker', '--date', '2024-01-01',
            '--skip-transcription'
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_root, timeout=60)

        print(f"Exit code: {result.returncode}")
        print(f"Stdout: {result.stdout}")
        print(f"Stderr: {result.stderr}")

        assert result.returncode == 0, f"Command failed: {result.stderr}"
        assert "Creating new sermon from audio file" in result.stdout
        assert "New sermon created successfully" in result.stdout

    finally:
        # Clean up
        os.unlink(audio_file)

def test_new_sermon_with_metadata():
    """Test new-sermon with custom metadata."""
    audio_file = create_test_audio()
    repo_root = Path(__file__).parent.parent

    try:
        cmd = [
            sys.executable, str(repo_root / 'sermon_updater.py'), '--dry-run', 'new-sermon',
            audio_file, '--speaker', 'John Doe', '--date', '2024-01-01',
            '--bible-text', 'Romans 8:28', '--title', 'Custom Title',
            '--description', 'Custom description', '--hashtags', '#custom #test',
            '--skip-transcription'
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_root, timeout=60)

        assert result.returncode == 0
        assert "Custom Title" in result.stdout
        assert "Custom description" in result.stdout
        assert "#custom #test" in result.stdout

    finally:
        os.unlink(audio_file)

def test_new_sermon_help():
    """Test that new-sermon help works."""
    # Get the repo root directory
    repo_root = Path(__file__).parent.parent
    cmd = [sys.executable, str(repo_root / 'sermon_updater.py'), 'new-sermon', '--help']
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_root, timeout=30)

    print(f"Help exit code: {result.returncode}")
    print(f"Help stdout: {result.stdout[:500]}...")
    print(f"Help stderr: {result.stderr[:500]}...")

    # The command should exit with 0 for help
    assert result.returncode == 0, f"Help command failed with exit code {result.returncode}"
    assert "Process an audio file and create a new sermon" in result.stdout
    assert "--speaker" in result.stdout
    assert "--skip-transcription" in result.stdout

if __name__ == '__main__':
    print("Running new-sermon tests...")

    try:
        test_new_sermon_help()
        print("✅ Help test passed")

        test_new_sermon_basic()
        print("✅ Basic functionality test passed")

        test_new_sermon_with_metadata()
        print("✅ Custom metadata test passed")

        print("\n🎉 All tests passed!")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
