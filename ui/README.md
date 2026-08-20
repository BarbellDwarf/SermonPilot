# SermonPilot Web UI

A modern Streamlit web interface for the SermonAudio AI audio processing pipeline.

## Features

- **📊 Dashboard**: Recent activity, quick stats, system status
- **🎵 New Sermon**: Upload audio files, configure processing, real-time progress
- **🔄 Batch Update**: Process multiple sermons with filtering and progress tracking
- **✅ Validation**: Quality metrics and description validation
- **📈 Analytics**: Processing metrics and interactive charts
- **⚙️ Settings**: Configuration management with web-based editing

## Installation

1. Install the core project dependencies from the repo root:
   ```bash
   cd ..
   uv pip install -r requirements/requirements.txt
   ```

2. Install UI-specific dependencies (from this directory):
   ```bash
   pip install -r requirements-ui.txt
   ```

## Running the Web UI

1. Ensure you have a valid `config.yaml` in the project root:
   ```bash
   cd ..
   cp config/config.example.yaml config.yaml
   # Edit config.yaml with your settings
   ```

2. Start the Streamlit application from the repo root:
   ```bash
   streamlit run streamlit_app.py
   ```

3. Open your browser to `http://localhost:8501`

## Development

### Project Structure

```
streamlit_app.py        # Main application entry point (repo root)
ui/
├── pages.py            # Page registry: st.Page definitions for all pages
├── ui_pages/           # Individual page implementations
│   ├── dashboard.py        # Dashboard with activity and stats
│   ├── new_sermon_enhanced.py  # New sermon processing workflow
│   ├── library.py          # Sermon library and metadata management
│   ├── batch_update.py     # Batch processing
│   ├── validation.py       # Description validation
│   ├── jobs.py             # Background job monitoring
│   ├── analytics.py        # Analytics dashboard
│   ├── sermon_import.py    # Filesystem import
│   ├── settings.py         # Configuration management
│   └── config_management.py  # YAML/SQL config management
├── database.py         # SQLite models and repository
├── job_queue.py        # Background job system
├── job_executors.py    # Job execution
├── ui_processor.py     # UI processing interface
├── requirements-ui.txt # UI-specific dependencies
└── README.md           # This file
```

### Adding New Pages

1. Create a new file in `ui/ui_pages/` (e.g., `ui/ui_pages/my_page.py`)
2. Implement a main function (e.g., `show_my_page()`)
3. Register the page in `ui/pages.py` with an `st.Page` entry pointing at the new file
4. Import and call the page function from `streamlit_app.py` if it needs explicit wiring

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