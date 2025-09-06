# SermonAudio Processor Web UI

A modern Streamlit web interface for the SermonAudio AI audio processing pipeline.

## Features

- **📊 Dashboard**: Recent activity, quick stats, system status
- **🎵 New Sermon**: Upload audio files, configure processing, real-time progress
- **🔄 Batch Update**: Process multiple sermons with filtering and progress tracking
- **✅ Validation**: Quality metrics and description validation
- **📈 Analytics**: Processing metrics and interactive charts
- **⚙️ Settings**: Configuration management with web-based editing

## Installation

1. Install core project dependencies:
   ```bash
   pip install -r ../requirements.txt
   ```

2. Install UI-specific dependencies:
   ```bash
   pip install -r requirements-ui.txt
   ```

## Running the Web UI

1. Ensure you have a valid `config.yaml` in the project root:
   ```bash
   cp ../config.example.yaml ../config.yaml
   # Edit config.yaml with your settings
   ```

2. Start the Streamlit application:
   ```bash
   streamlit run streamlit_app.py
   ```

3. Open your browser to `http://localhost:8501`

## Development

### Project Structure

```
ui/
├── streamlit_app.py        # Main application entry point
├── pages/                  # Individual page implementations
│   ├── dashboard.py        # Dashboard with activity and stats
│   ├── new_sermon.py       # New sermon processing workflow
│   ├── settings.py         # Configuration management
│   └── ...                 # Additional pages
├── requirements-ui.txt     # UI-specific dependencies
└── README.md              # This file
```

### Adding New Pages

1. Create a new file in `pages/` directory
2. Implement a main function (e.g., `show_my_page()`)
3. Add the page to the navigation in `streamlit_app.py`
4. Import and call the page function

### Integration with CLI

The web UI integrates with the existing CLI functionality by:
- Importing and using existing modules (`sermon_updater.py`, `audio_processing.py`, `llm_manager.py`)
- Sharing the same configuration system (`config.yaml`)
- Providing a web wrapper around CLI functions

## Configuration

The web UI uses the same configuration as the CLI tool. Key settings:

- **SermonAudio API**: API key and broadcaster ID
- **LLM Providers**: OpenAI/Ollama configuration for primary and fallback
- **Audio Processing**: Enhancement methods and parameters
- **Processing Options**: Dry run, debug mode, output directories

## Architecture

### Session State Management

The application uses Streamlit's session state to maintain:
- Configuration data
- LLM manager instances
- Processing history
- Current user settings
- Processing queue status

### Real-time Updates

Processing operations provide real-time feedback through:
- Progress bars for long-running operations
- Live log output during processing
- Status updates for batch operations
- System health monitoring

### Error Handling

The UI includes comprehensive error handling:
- Graceful degradation when dependencies are missing
- Clear error messages with suggested solutions
- Validation of user inputs before processing
- Recovery options for failed operations

## Security Considerations

- API keys are handled securely using Streamlit's input widgets
- Configuration files are validated before loading
- File uploads are restricted to supported audio formats
- Session state is properly isolated between users

## Performance

The UI is optimized for performance through:
- Lazy loading of heavy components
- Caching of expensive operations
- Efficient state management
- Minimal resource usage

## Troubleshooting

### Common Issues

1. **"Module not found" errors**: Ensure all dependencies are installed
2. **Configuration errors**: Check `config.yaml` syntax and required fields
3. **LLM connection issues**: Verify provider settings and network connectivity
4. **Audio processing failures**: Check audio file formats and enhancement method availability

### Debug Mode

Enable debug mode in Settings → General → Debug Mode for detailed logging.

## Support

For issues and questions:
- Check the main project documentation
- Review the GitHub issues page
- Enable debug mode for detailed error information