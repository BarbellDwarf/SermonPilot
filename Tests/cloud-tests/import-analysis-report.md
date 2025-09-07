# SermonAudio Processor Import Analysis Report
**Generated**: 1757204887.9279902

## 📊 Summary
- **Total Python Files**: 122
- **Files with Errors**: 6
- **Total Imports**: 1000
- **External Packages**: 16
- **Unresolvable Imports**: 117

## 📦 External Package Dependencies
- `chromadb`
- `deepfilternet`
- `numpy`
- `ollama`
- `openai`
- `pandas`
- `psutil`
- `pydub`
- `pytest`
- `requests`
- `sentence_transformers`
- `sermonaudio`
- `soundfile`
- `streamlit`
- `torch`
- `torchaudio`

## 🔝 Most Imported Modules
- `pathlib`: 95 imports
- `sys`: 92 imports
- `datetime`: 44 imports
- `traceback`: 42 imports
- `os`: 39 imports
- `logging`: 33 imports
- `sermon_updater`: 33 imports
- `database`: 33 imports
- `yaml`: 32 imports
- `job_queue`: 31 imports

## ❌ Unresolvable Imports
- `shutil` in `unknown:10` - Module not found in stdlib, external packages, or project
- `tempfile` in `unknown:11` - Module not found in stdlib, external packages, or project
- `tempfile` in `unknown:811` - Module not found in stdlib, external packages, or project
- `shutil` in `unknown:721` - Module not found in stdlib, external packages, or project
- `tempfile` in `unknown:1062` - Module not found in stdlib, external packages, or project
- `shutil` in `unknown:1237` - Module not found in stdlib, external packages, or project
- `io` in `unknown:15` - Module not found in stdlib, external packages, or project
- `df` in `unknown:54` - Module not found in stdlib, external packages, or project
- `df` in `unknown:54` - Module not found in stdlib, external packages, or project
- `resemble_enhance.enhancer.inference` in `unknown:64` - Module not found in stdlib, external packages, or project

## 🔄 Potential Circular Dependencies
- `analytics.py` → `ui.sermonaudio_analytics`
- `analytics.py` → `ui.analytics_chat`

## 📄 File Analysis Summary
### 📈 Files with Many Imports (>20)
- `sermon_updater.py`: 42 imports
- `audio_processing.py`: 33 imports
- `analytics.py`: 33 imports
- `settings.py`: 27 imports
- `test_best_enhancement_models.py`: 22 imports

## 💡 Recommendations
- Review and fix unresolvable imports
- Investigate potential circular dependencies
- Consider refactoring files with excessive imports
- Fix Python syntax errors in affected files
