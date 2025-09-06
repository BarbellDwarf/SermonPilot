#!/usr/bin/env python3
"""
Check audio enhancement package availability
"""

def check_audio_packages():
    """Check what audio enhancement packages are available"""
    packages_to_check = [
        ('df', 'DeepFilterNet (df)'),
        ('deepfilternet', 'DeepFilterNet (deepfilternet)'),
        ('resemble_enhance', 'Resemble Enhance'),
        ('torch', 'PyTorch'),
        ('torchaudio', 'TorchAudio'),
        ('pydub', 'Pydub'),
        ('librosa', 'Librosa')
    ]
    
    results = {}
    
    for package, name in packages_to_check:
        try:
            __import__(package)
            results[package] = {'available': True, 'name': name}
            print(f"✅ {name} is available")
        except ImportError as e:
            results[package] = {'available': False, 'name': name, 'error': str(e)}
            print(f"❌ {name} not available: {e}")
    
    return results

if __name__ == "__main__":
    print("🔍 Checking audio enhancement packages...")
    print()
    
    results = check_audio_packages()
    
    print()
    print("📋 Summary:")
    available_count = sum(1 for r in results.values() if r['available'])
    total_count = len(results)
    
    print(f"Available packages: {available_count}/{total_count}")
    
    if not results.get('deepfilternet', {}).get('available', False):
        print()
        print("💡 To fix DeepFilterNet issue:")
        print("   pip install deepfilternet")
        print("   - OR -")
        print("   Change config.yaml: audio_enhancement_method: none")
