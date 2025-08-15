# Test Files

## Audio File Requirements

Several test files in this directory require a sample audio file to run properly. The tests look for:

```text
tests/sample_audio.mp3
```

### To run audio-dependent tests

1. **Option 1**: Add your own sample audio file
   - Place any MP3 file at `tests/sample_audio.mp3`
   - The tests will automatically detect and use it

2. **Option 2**: Skip audio tests
   - Tests will automatically skip if no audio file is present
   - Use `pytest -v` to see which tests are skipped

### Tests that require audio

- `test_no_compression.py` - Audio processing without compression
- `test_best_enhancement_models.py` - Model comparison tests
- `test_resemble_comprehensive.py` - Resemble Enhance testing
- `test_quick_models.py` - Quick model validation
- `test_optimized_enhancement.py` - Performance optimization tests

### Audio File Specifications

- **Format**: MP3
- **Duration**: Any length (tests will process appropriate segments)
- **Content**: Speech/sermon audio works best
- **Size**: No specific requirement (larger files test chunking logic)

### Important Notes

- Audio files are **excluded from git** via `.gitignore`
- Tests are designed to gracefully skip when audio is unavailable
- No sensitive or copyrighted content should be used for testing
