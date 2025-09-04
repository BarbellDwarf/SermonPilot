# New-Sermon Workflow Documentation

## Overview

The `new-sermon` command allows you to create new sermons directly from audio files with AI-powered metadata generation. This workflow combines audio processing, transcription, and intelligent content generation to streamline sermon publishing.

## Features

### 🎵 Audio Processing
- **AI Enhancement**: Uses DeepFilterNet or Resemble Enhance for audio quality improvement
- **Format Support**: Accepts various audio formats (MP3, WAV, M4A, etc.)
- **Fallback Processing**: Gracefully handles processing failures with original audio preservation

### 🎙️ Audio Transcription
- **OpenAI Whisper Integration**: High-quality speech-to-text transcription
- **Configurable Models**: Choose from `tiny`, `base`, `small`, `medium`, `large` for speed/quality balance
- **Optional Processing**: Skip transcription for faster workflow when not needed
- **Network Resilience**: Handles offline scenarios and network failures gracefully

### 🤖 Intelligent Metadata Generation
- **LLM-Powered**: Uses configured LLM providers for high-quality content generation
- **Content-Aware**: Generates titles, descriptions, and hashtags based on actual sermon content
- **Smart Fallbacks**: Creates structured metadata even when LLM/transcription fails
- **Customizable**: Override any generated content with your own

## Basic Usage

### Required Arguments
- `audio_file`: Path to the audio file
- `--speaker`: Name of the speaker/preacher
- `--date`: Recording date in YYYY-MM-DD format

### Example Commands

```bash
# Simplest usage - generates all metadata from audio
python sermon_updater.py new-sermon sermon.mp3 --speaker "Pastor Smith" --date "2024-01-15"

# With Bible reference for better metadata
python sermon_updater.py new-sermon sermon.mp3 --speaker "Pastor Smith" --date "2024-01-15" --bible-text "John 3:16"

# Fast processing without transcription
python sermon_updater.py new-sermon sermon.mp3 --speaker "Pastor Smith" --date "2024-01-15" --skip-transcription

# Custom transcription quality
python sermon_updater.py new-sermon sermon.mp3 --speaker "Pastor Smith" --date "2024-01-15" --whisper-model large

# Test run without uploading
python sermon_updater.py --dry-run new-sermon sermon.mp3 --speaker "Pastor Smith" --date "2024-01-15"
```

## Advanced Options

### Audio Transcription Control
- `--skip-transcription`: Skip audio transcription entirely (faster processing)
- `--whisper-model {tiny,base,small,medium,large}`: Control transcription quality vs speed
  - `tiny`: Fastest, lower quality
  - `base`: Good balance (default)
  - `small`: Better quality, slower
  - `medium`: High quality, much slower
  - `large`: Best quality, very slow

### Metadata Customization
- `--title`: Override generated title
- `--subtitle`: Add a subtitle
- `--description`: Override generated description  
- `--hashtags`: Override generated hashtags
- `--event-type`: Event type (default: "Sunday Service")
- `--bible-text`: Bible reference for context

## Processing Workflow

1. **Audio Processing**
   - Loads and validates audio file
   - Attempts AI enhancement (DeepFilterNet/Resemble Enhance)
   - Falls back to original audio if enhancement fails

2. **Transcription** (if enabled)
   - Downloads appropriate Whisper model
   - Transcribes enhanced or original audio
   - Handles network failures gracefully

3. **Metadata Generation**
   - Uses transcript content for LLM generation
   - Generates title, description, and hashtags
   - Falls back to structured metadata if LLM fails

4. **Sermon Creation**
   - Creates sermon via SermonAudio API
   - Uploads processed audio
   - Saves local files and metadata

5. **Local Storage**
   - Saves to `processed_sermons/{sermon_id}/`
   - Includes enhanced audio, transcript, and metadata JSON

## Performance Considerations

### Transcription Speed vs Quality
- **tiny**: ~32x realtime, basic quality
- **base**: ~16x realtime, good quality (recommended)
- **small**: ~8x realtime, better quality
- **medium**: ~4x realtime, high quality
- **large**: ~2x realtime, best quality

### Network Requirements
- **Whisper models**: Downloaded on first use (39MB - 2.9GB)
- **LLM providers**: Require active internet connection
- **Fallback mode**: Works offline with basic metadata

## Error Handling

The system is designed to be resilient:

- **Audio processing failures**: Uses original audio
- **Transcription failures**: Skips to basic metadata generation
- **LLM failures**: Uses structured fallback metadata
- **Network issues**: Graceful degradation with informative messages
- **Invalid audio**: Clear error messages with suggestions

## Configuration

Ensure your `config.yaml` includes:

```yaml
# LLM providers for metadata generation
llm:
  primary:
    provider: "openai"  # or "ollama"
    # ... provider settings
  fallback:
    enabled: true
    provider: "ollama"  # or "openai"
    # ... fallback settings

# SermonAudio API credentials
api_key: "your-api-key"
broadcaster_id: "your-broadcaster-id"
```

## Output Structure

Local files saved to `processed_sermons/{sermon_id}/`:
- `sermon_{sermon_id}.mp3`: Enhanced audio file
- `{sermon_id}_transcript.txt`: Full transcript (if available)
- `metadata.json`: Complete sermon metadata

Example metadata.json:
```json
{
  "sermonID": "1234567890123",
  "title": "The Hope of Glory",
  "speaker": "Pastor Smith",
  "recorded_date": "2024-01-15",
  "event_type": "Sunday Service",
  "bible_text": "Colossians 1:27",
  "description": "An inspiring message about...",
  "hashtags": "#hope #glory #colossians #faith",
  "transcript_length": 15420,
  "has_transcript": true
}
```

## Troubleshooting

### Common Issues

**"Whisper model download failed"**
- Check internet connection
- Try smaller model: `--whisper-model tiny`
- Use `--skip-transcription` for offline processing

**"Audio processing failed"**  
- Ensure ffmpeg is installed: `sudo apt install ffmpeg`
- Check audio file format and integrity
- Try with different audio file

**"LLM generation failed"**
- Verify LLM provider configuration in config.yaml
- Check API keys and network connectivity
- System will use fallback metadata automatically

**"Sermon creation failed"**
- Verify SermonAudio API credentials
- Check broadcaster permissions
- Ensure required fields (title, speaker, date) are valid

### Performance Optimization

- Use `--skip-transcription` for faster processing
- Use smaller Whisper models for speed
- Process during off-peak hours for better API performance
- Consider local LLM setup (Ollama) for better reliability

## Integration with Existing Workflow

The `new-sermon` command integrates seamlessly with existing commands:

```bash
# Create new sermon
python sermon_updater.py new-sermon audio.mp3 --speaker "Pastor Smith" --date "2024-01-15"

# Later, update metadata if needed  
python sermon_updater.py metadata-update --sermon-id {generated_id} --force-description

# Validate the description quality
python sermon_updater.py validation --validation-sermon-ids {generated_id}
```

## Best Practices

1. **Audio Quality**: Use high-quality source audio for best results
2. **Bible References**: Always include `--bible-text` when applicable
3. **Testing**: Use `--dry-run` to preview results before uploading
4. **Batch Processing**: Process multiple sermons with consistent settings
5. **Local Storage**: Keep local copies for backup and future reference

This comprehensive workflow enables efficient, automated sermon processing while maintaining quality and flexibility for manual customization when needed.