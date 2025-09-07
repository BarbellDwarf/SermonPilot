# SermonAudio Processor UI Static Analysis Report
**Generated**: 1757206193.5755386

## 📊 Overview
- **Total UI Files**: 32
- **Total Lines of Code**: 16790
- **UI Pages**: 11
- **Shared Components**: 19

## 🏠 Main Application (streamlit_app.py)
- **Lines of Code**: 358
- **Functions**: 13
- **Imports**: 20
- **Description**: Streamlit Web UI for SermonAudio Processor

A modern web interface for the SermonAudio AI audio proc...

## 📄 UI Pages Analysis
### settings
- **Lines**: 1879
- **Functions**: 34
- **Classes**: 0
- **Streamlit Components**: 272
- **Purpose**: Settings Page for SermonAudio Processor

Handles configuration management, LLM provider setup, audio...

### viewer
- **Lines**: 384
- **Functions**: 1
- **Classes**: 0
- **Streamlit Components**: 96
- **Purpose**: Sermon Viewer Page - Detailed sermon viewing...

### analytics
- **Lines**: 1360
- **Functions**: 17
- **Classes**: 0
- **Streamlit Components**: 156
- **Purpose**: Analytics Page for SermonAudio Processor

Displays processing metrics, success rates, content analys...

### dashboard
- **Lines**: 288
- **Functions**: 8
- **Classes**: 0
- **Streamlit Components**: 43
- **Purpose**: Dashboard Page for SermonAudio Processor

Displays recent activity, quick stats, system status, and ...

### library
- **Lines**: 736
- **Functions**: 6
- **Classes**: 0
- **Streamlit Components**: 139
- **Purpose**: Sermon Library Page - Browse and search processed sermons

Provides comprehensive sermon browsing wi...

### batch_update
- **Lines**: 717
- **Functions**: 15
- **Classes**: 0
- **Streamlit Components**: 108
- **Purpose**: Batch Processing Page for SermonAudio Processor

Handles filtering sermons, selecting batches, confi...

### validation
- **Lines**: 735
- **Functions**: 17
- **Classes**: 0
- **Streamlit Components**: 135
- **Purpose**: Validation Page for SermonAudio Processor

Handles description validation, quality metrics, failed d...

### jobs
- **Lines**: 789
- **Functions**: 15
- **Classes**: 2
- **Streamlit Components**: 147
- **Purpose**: Jobs Page - Monitor and manage background jobs

Provides a comprehensive interface for viewing, mana...

### library_new
- **Lines**: 330
- **Functions**: 5
- **Classes**: 0
- **Streamlit Components**: 66
- **Purpose**: Sermon Library Page - Browse and search processed sermons

Provides comprehensive sermon browsing wi...

### new_sermon
- **Lines**: 551
- **Functions**: 9
- **Classes**: 0
- **Streamlit Components**: 121
- **Purpose**: New Sermon Processing Page for SermonAudio Processor

Handles file upload, metadata form input, proc...

## 🎨 Streamlit Component Usage
- `st.markdown`: 235 usages
- `st.columns`: 120 usages
- `st.info`: 117 usages
- `st.error`: 116 usages
- `st.button`: 101 usages
- `st.metric`: 96 usages
- `st.success`: 74 usages
- `st.write`: 65 usages
- `st.rerun`: 59 usages
- `st.text`: 55 usages
- `st.text_input`: 50 usages
- `st.selectbox`: 48 usages
- `st.checkbox`: 43 usages
- `st.warning`: 40 usages
- `st.caption`: 29 usages
- `st.expander`: 18 usages
- `st.subheader`: 17 usages
- `st.spinner`: 16 usages
- `st.progress`: 12 usages
- `st.tabs`: 11 usages
- `st.text_area`: 11 usages
- `st.dataframe`: 11 usages
- `st.number_input`: 9 usages
- `st.code`: 8 usages
- `st.date_input`: 7 usages
- `st.download_button`: 6 usages
- `st.container`: 6 usages
- `st.form_submit_button`: 5 usages
- `st.json`: 5 usages
- `st.bar_chart`: 5 usages
- `st.divider`: 4 usages
- `st.audio`: 4 usages
- `st.line_chart`: 4 usages
- `st.form`: 3 usages
- `st.chat_message`: 3 usages
- `st.set_page_config`: 2 usages
- `st.file_uploader`: 2 usages
- `st.slider`: 2 usages
- `st.exception`: 2 usages
- `st.title`: 1 usages
- `st.area_chart`: 1 usages
- `st.data_editor`: 1 usages
- `st.empty`: 1 usages

## 📦 Dependencies
- analytics_manager
- anthropic
- asyncio
- chromadb
- chromadb.config
- cohere
- collections.abc
- config_utils
- contextlib
- database
- dataclasses
- datetime
- df
- embedding_manager
- enum
- flask
- flask_cors
- hashlib
- job_executors
- job_queue
- json
- llm_manager
- logging
- mutagen.mp3
- mutagen.wave
- ollama
- openai
- os
- pandas
- pathlib
- performance_monitor
- psutil
- random
- re
- requests
- resemble_enhance
- sentence_transformers
- sermon_importer
- sermon_manager
- sermon_metadata
- sermon_updater
- sermonaudio
- sermonaudio_api
- shared_navigation
- shutil
- sqlite3
- src.audio_processing
- src.llm_manager
- streamlit
- subprocess
- sys
- system_status
- threading
- time
- torch
- traceback
- typing
- ui.analytics_chat
- ui.database
- ui.rag_system
- ui.sermonaudio_analytics
- ui_pages.analytics
- ui_pages.batch_update
- ui_pages.dashboard
- ui_pages.jobs
- ui_pages.library
- ui_pages.new_sermon
- ui_pages.settings
- ui_pages.validation
- ui_processor
- uuid
- voyageai
- warnings
- yaml

## ⚠️ Potential Issues
- High complexity files (>20): settings
- Large files (>500 lines): settings, analytics, library, batch_update, validation, jobs, new_sermon

## 📈 Quality Metrics
- **Overall Complexity Score**: 144
- **Average Lines per File**: 524
- **Streamlit Component Diversity**: 43 different components
