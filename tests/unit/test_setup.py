#!/usr/bin/env python

"""
Test script to verify SermonAudio Updater setup
"""

import os
import sys


def test_imports():
    """Test if all required packages are installed."""
    print("Testing package imports...")

    packages = {
        'sermonaudio': 'SermonAudio API',
        'requests': 'HTTP requests',
        'numpy': 'Numerical processing',
        'scipy': 'Scientific computing',
        'pydub': 'Audio manipulation',
        'noisereduce': 'Noise reduction',
        'soundfile': 'Audio file I/O',
        'yaml': 'YAML parsing',
        'dotenv': 'Environment variables',
        'tqdm': 'Progress bars',
        'colorlog': 'Colored logging'
    }

    missing = []
    for package, description in packages.items():
        try:
            if package == 'yaml':
                import yaml
            elif package == 'dotenv':
                from dotenv import load_dotenv
            else:
                __import__(package)
            print(f"✓ {package:<15} - {description}")
        except ImportError:
            print(f"✗ {package:<15} - {description} [MISSING]")
            missing.append(package)

    # Test optional packages
    print("\nOptional packages:")
    optional = {
        'ollama': 'Ollama LLM',
        'openai': 'OpenAI API',
        'pyaudacity': 'Audacity integration'
    }

    for package, description in optional.items():
        try:
            __import__(package)
            print(f"✓ {package:<15} - {description}")
        except ImportError:
            print(f"○ {package:<15} - {description} [Not installed]")

    return missing


def test_sermonaudio_connection():
    """Test SermonAudio API connection."""
    print("\nTesting SermonAudio API...")

    try:
        import sermonaudio
        from sermonaudio.node.requests import Node

        # Check if API key is set
        api_key = os.getenv('SERMONAUDIO_API_KEY')
        if not api_key:
            print("✗ No API key found in environment")
            print("  Set SERMONAUDIO_API_KEY in .env file")
            return False

        sermonaudio.set_api_key(api_key)

        # Try a simple API call
        try:
            # Get broadcaster info
            broadcaster_id = os.getenv('SERMONAUDIO_BROADCASTER_ID')
            if broadcaster_id:
                response = Node.get_sermons(
                    broadcaster_id=broadcaster_id,
                    page_size=1
                )
                print("✓ API connection successful")
                print(f"  Found {len(response.results)} sermon(s)")
                return True
            else:
                print("✗ No broadcaster ID found")
                print("  Set SERMONAUDIO_BROADCASTER_ID in .env file")
                return False
        except Exception as e:
            print(f"✗ API call failed: {e}")
            return False

    except ImportError:
        print("✗ SermonAudio package not installed")
        return False


def test_ollama():
    """Test Ollama connection."""
    print("\nTesting Ollama...")

    try:
        import ollama

        # Check if Ollama is running
        try:
            models = ollama.list()
            print("✓ Ollama is running")
            print(f"  Available models: {[m['name'] for m in models['models']]}")

            # Test generation
            if models['models']:
                model = models['models'][0]['name']
                response = ollama.generate(
                    model=model,
                    prompt="Say 'Hello, SermonAudio!' in 5 words or less."
                )
                print(f"  Test generation: {response['response'].strip()}")
            else:
                print("  No models installed. Run: ollama pull llama3")

            return True
        except Exception as e:
            print("✗ Ollama not running or not accessible")
            print("  Start Ollama with: ollama serve")
            print(f"  Error: {e}")
            return False

    except ImportError:
        print("○ Ollama package not installed (optional)")
        return None


def test_audio_processing():
    """Test audio processing capabilities."""
    print("\nTesting audio processing...")

    try:
        from audio_processing import AudioProcessor

        processor = AudioProcessor()
        print("✓ Audio processor initialized")

        # Test with a sample file if available
        test_file = "tests/sample.mp3"
        if os.path.exists(test_file):
            print(f"  Testing with {test_file}")
            try:
                data, rate = processor.load_audio(test_file)
                print(f"  ✓ Loaded audio: {len(data)} samples at {rate} Hz")
            except Exception as e:
                print(f"  ✗ Failed to load audio: {e}")
        else:
            print("  No test audio file found")

        return True

    except Exception as e:
        print(f"✗ Audio processing test failed: {e}")
        return False


def test_audacity():
    """Test Audacity pipe connection."""
    print("\nTesting Audacity connection...")

    try:
        from audio_processing import AudacityProcessor

        processor = AudacityProcessor()
        if processor.pipe_exists:
            print("✓ Audacity pipe detected")
            # Try sending a simple command
            result = processor.send_command("Help: Command=Help")
            if result:
                print("  ✓ Communication successful")
            else:
                print("  ✗ Communication failed")
        else:
            print("○ Audacity pipe not found")
            print("  Make sure Audacity is running with mod-script-pipe enabled")

    except Exception as e:
        print(f"✗ Audacity test failed: {e}")


def create_test_config():
    """Create a test configuration file."""
    print("\nCreating test configuration...")

    config = {
        'api_key': os.getenv('SERMONAUDIO_API_KEY', 'your-api-key'),
        'broadcaster_id': os.getenv('SERMONAUDIO_BROADCASTER_ID', 'your-broadcaster-id'),
        'llm_provider': 'ollama',
        'ollama_model': 'llama3',
        'audio_noise_reduction': True,
        'audio_amplify': True,
        'audio_normalize': True,
        'dry_run': True  # Safe for testing
    }

    import yaml
    with open('test_config.yaml', 'w') as f:
        yaml.dump(config, f, default_flow_style=False)

    print("✓ Created test_config.yaml")
    print("  Edit this file with your API credentials")


def main():
    """Run all tests."""
    print("SermonAudio Updater Setup Test")
    print("=" * 50)

    # Load environment variables
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("✓ Loaded .env file")
    except:
        print("○ No .env file loaded")

    # Run tests
    missing = test_imports()

    if missing:
        print(f"\n⚠ Missing required packages: {', '.join(missing)}")
        print("Install with: pip install -r requirements.txt")
        sys.exit(1)

    sa_ok = test_sermonaudio_connection()
    ollama_ok = test_ollama()
    audio_ok = test_audio_processing()
    test_audacity()

    # Create test config
    create_test_config()

    # Summary
    print("\n" + "=" * 50)
    print("Setup Summary:")

    if sa_ok and audio_ok:
        print("✓ Core functionality ready")
        if ollama_ok:
            print("✓ AI features available (Ollama)")
        else:
            print("○ AI features not available (install Ollama for summaries)")

        print("\nNext steps:")
        print("1. Edit test_config.yaml with your API credentials")
        print("2. Run: python sermon-updater.py --config test_config.yaml --dry-run")
        print("3. Remove --dry-run to actually update sermons")
    else:
        print("✗ Setup incomplete")
        print("\nFix the issues above and run this test again")


if __name__ == '__main__':
    main()
