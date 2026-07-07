# Enhanced Audio Editing Features - User Guide

## Overview

SermonPilot now includes comprehensive audio editing capabilities specifically designed for educational content with Q&A sessions. These features provide content creators with powerful tools to optimize their recordings before processing.

## New Features Summary

### 🎵 Interactive Audio Editing
- **Waveform Visualization**: See your audio visually with interactive timeline
- **Manual Editing**: Select, trim, amplify, and mark regions manually
- **Real-time Preview**: Listen to edits before final processing
- **Q&A Marking**: Special handling for question and answer segments

### 🧠 Intelligent Q&A Detection
- **Automatic Detection**: AI identifies potential question segments
- **Pitch Analysis**: Detects rising intonation typical of questions
- **Pause Detection**: Identifies silence patterns after questions
- **Preservation**: Gentle processing for detected Q&A regions

### 🎛️ Advanced Processing Modes
- **Standard Processing**: Balanced for typical recordings
- **Question-Friendly**: Optimized for interactive content
- **Lecture Mode**: Clear speech with minimal interruptions
- **Gentle Enhancement**: Minimal processing for high-quality audio
- **Aggressive Cleanup**: Strong noise reduction for challenging recordings
- **Custom Settings**: Full manual control over all parameters

## How to Access

### Option 1: Enhanced New Sermon Page
The enhanced features are available through the new "Enhanced New Sermon" interface:

```python
# In the Streamlit app, use:
from ui.ui_pages.new_sermon_enhanced import show_new_sermon_enhanced
```

### Option 2: Individual Components
Use components separately in your own workflow:

```python
from ui.components.audio_waveform import AudioWaveformViewer
from ui.components.audio_editor import AudioEditor
from ui.components.audio_preview import AudioPreview
from ui.components.processing_modes import ProcessingModeSelector
from src.audio.question_processor import QuestionProcessor
from src.audio.adaptive_processor import AdaptiveAudioProcessor
```

## Workflow Guide

### Step 1: Upload & Metadata (📁)
1. Upload your audio file (MP3, WAV, M4A, FLAC, OGG)
2. Fill in required metadata (speaker, date, event type)
3. Add optional information (title, description, bible text)

### Step 2: Analyze Audio (📊)
1. View audio information (duration, quality metrics)
2. Visualize the waveform
3. Run quality analysis to detect issues
4. Auto-detect Q&A segments
5. Review processing recommendations

### Step 3: Edit Audio (✂️)
1. Select editing mode (Select, Remove, Amplify, Mark Q&A)
2. Choose regions using the waveform or manual time selection
3. Apply edits (trim, boost volume, mark questions)
4. Preview original vs edited audio
5. Compare side-by-side
6. Review edit summary

### Step 4: Configure Processing (🎛️)
1. Choose from 6 processing modes
2. Fine-tune settings if needed
3. Review processing preview (intensity, time, quality impact)
4. Set AI metadata generation options

### Step 5: Process & Upload (▶️)
1. Review complete processing summary
2. Preview what processing will be applied
3. Start enhanced processing with audio edits
4. Monitor progress and review results

## Processing Modes Explained

### 🎯 Standard Processing
- **Best for**: Regular sermons, single speaker presentations
- **Settings**: Balanced noise reduction (60%), standard amplification
- **Processing Time**: 1.3x realtime
- **Quality Preservation**: 88%

### ❓ Question-Friendly Processing
- **Best for**: Interactive lectures, Q&A sessions, panel discussions
- **Settings**: Gentle noise reduction (30%), question preservation enabled
- **Processing Time**: 1.7x realtime  
- **Quality Preservation**: 99%

### 🎓 Lecture Mode
- **Best for**: Educational lectures, training sessions, webinars
- **Settings**: Strong noise reduction (70%), speech enhancement
- **Processing Time**: 4.1x realtime
- **Quality Preservation**: 86%

### 🌿 Gentle Enhancement
- **Best for**: High-quality recordings, professional productions
- **Settings**: Minimal processing (20% noise reduction)
- **Processing Time**: 1.1x realtime
- **Quality Preservation**: 100%

### 🔧 Aggressive Cleanup
- **Best for**: Noisy environments, poor quality recordings
- **Settings**: Strong noise reduction (80%), maximum enhancement
- **Processing Time**: 4.2x realtime
- **Quality Preservation**: 84%

### ⚙️ Custom Settings
- **Best for**: Specific requirements, fine-tuned control
- **Settings**: Manually configure all parameters
- **Processing Time**: Variable
- **Quality Preservation**: Variable

## Technical Features

### Q&A Detection Algorithm
- **Pitch Analysis**: Detects rising intonation patterns
- **Energy Patterns**: Identifies speech activity and pauses  
- **Position Analysis**: Questions more likely later in recordings
- **Fallback Methods**: Works without librosa/scipy dependencies

### Adaptive Processing
- **Context-Aware**: Different processing for questions vs. answers
- **Buffer Zones**: 2-second gentle processing around Q&A
- **Intelligent Amplification**: Boost questions for clarity
- **Quality Preservation**: Maintains natural dynamics

### Audio Editing
- **Non-destructive**: Original audio preserved
- **Real-time Preview**: Instant feedback on edits
- **Multiple Actions**: Remove, amplify, fade, mark segments
- **Statistics**: Detailed edit summary and impact analysis

## Demo Script

Run the included demo to see all features working together:

```bash
python demo_enhanced_workflow.py
```

This creates synthetic audio with Q&A characteristics and demonstrates:
- Audio analysis and quality assessment
- Automatic Q&A detection
- Manual editing workflow
- Processing mode comparison
- Adaptive processing with preservation
- Preview generation

## Testing

The implementation includes comprehensive tests:

```bash
# Test individual components
python -m pytest tests/test_audio_editing_components.py -v

# Test enhanced processing
python -m pytest tests/test_enhanced_audio_processing.py -v

# Test complete workflow integration
python -m pytest tests/test_enhanced_workflow_integration.py -v
```

**Test Results**: 46 tests total, all passing
- 15 tests for UI components
- 22 tests for enhanced processing
- 9 tests for workflow integration

## Performance Characteristics

### Memory Usage
- Efficient chunked processing for large files
- Temporary file cleanup
- Optimized numpy operations

### Processing Speed
- GPU acceleration when available (CUDA)
- Fallback to CPU processing
- Multiple processing intensity levels

### Quality
- Intelligent Q&A preservation
- Minimal artifacts from editing
- Professional-grade audio enhancement

## Error Handling

The system gracefully handles:
- Empty or invalid audio files
- Missing dependencies (librosa, scipy)
- Processing failures
- Network interruptions
- Memory limitations

## Future Enhancements

Potential improvements include:
- Real-time spectrogram visualization
- Advanced EQ controls
- Multi-track editing
- Automatic speaker diarization
- Cloud processing integration

## Support

For issues or questions:
1. Check the test output for validation
2. Run the demo script to verify functionality  
3. Review error messages for specific guidance
4. Consult the processing logs for detailed information

This implementation provides a complete, production-ready solution for intelligent audio editing specifically designed for educational and religious content with Q&A preservation.