# Code Refactoring and Modularization Plan

## Executive Summary

This plan outlines a comprehensive approach to breaking down high-complexity files in the SermonAudio Processor into smaller, more maintainable modules. The goal is to improve code organization, reduce complexity, enhance testability, and make the codebase more maintainable for future development.

## Current Code Complexity Analysis

### High-Complexity Files Identified

#### Main Application Files
1. **`sermon_updater.py`** - 3,510 lines
   - **Complexity Issues**: Single monolithic file handling CLI, processing logic, API integration, and validation
   - **Responsibilities**: Command parsing, sermon processing, API calls, file operations, error handling
   - **Dependencies**: Multiple external libraries, configuration management, logging

2. **`streamlit_app.py`** - 357 lines
   - **Complexity Issues**: Main UI file handling routing, state management, and multiple page logic
   - **Responsibilities**: Page routing, component rendering, data processing, user interactions
   - **Dependencies**: Streamlit, multiple UI components, data processing modules

#### UI Module Files
3. **`ui/sermon_manager.py`** - Estimated 500+ lines
   - **Complexity Issues**: Sermon CRUD operations, data processing, API integration
   - **Responsibilities**: Sermon data management, processing coordination, status tracking

4. **`ui/ui_processor.py`** - Estimated 400+ lines
   - **Complexity Issues**: UI processing logic, form handling, progress tracking
   - **Responsibilities**: Processing workflows, user input validation, result display

#### Supporting Files
5. **`src/audio_processing.py`** - Estimated 600+ lines
   - **Complexity Issues**: Multiple audio processing algorithms, format handling
   - **Responsibilities**: Audio enhancement, noise reduction, format conversion

6. **`src/llm_manager.py`** - Estimated 450+ lines
   - **Complexity Issues**: Multiple LLM provider integrations, fallback logic
   - **Responsibilities**: Provider management, request routing, response processing

### Complexity Metrics

**Cyclomatic Complexity Thresholds:**
- **Low**: 1-10 (Good)
- **Medium**: 11-20 (Needs attention)
- **High**: 21-50 (Should refactor)
- **Very High**: 50+ (Critical - must refactor)

**Current Issues:**
- Functions with 50+ lines common
- Classes with multiple responsibilities
- Tight coupling between components
- Mixed concerns in single files
- Difficult to test individual components

## Phase 1: Analysis and Planning (Week 1)

### 1.1 Detailed Code Analysis

**Create complexity analysis tools:**
```python
# tools/analysis/code_complexity.py
import ast
import os
from pathlib import Path
from typing import Dict, List, Tuple

class ComplexityAnalyzer:
    def __init__(self, root_path: str):
        self.root_path = Path(root_path)

    def analyze_file(self, file_path: Path) -> Dict:
        """Analyze a single Python file for complexity metrics."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        tree = ast.parse(content)

        metrics = {
            'file_path': str(file_path),
            'lines_of_code': len(content.splitlines()),
            'functions': [],
            'classes': [],
            'imports': []
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                metrics['functions'].append({
                    'name': node.name,
                    'line_start': node.lineno,
                    'line_end': node.end_lineno,
                    'complexity': self._calculate_complexity(node)
                })
            elif isinstance(node, ast.ClassDef):
                metrics['classes'].append({
                    'name': node.name,
                    'line_start': node.lineno,
                    'methods': len([n for n in node.body if isinstance(n, ast.FunctionDef)])
                })

        return metrics

    def _calculate_complexity(self, node: ast.FunctionDef) -> int:
        """Calculate cyclomatic complexity of a function."""
        complexity = 1  # Base complexity

        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.With)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
            elif isinstance(child, ast.Try):
                complexity += len(child.handlers)

        return complexity

    def analyze_project(self) -> List[Dict]:
        """Analyze all Python files in the project."""
        results = []

        for py_file in self.root_path.rglob('*.py'):
            if not any(skip in str(py_file) for skip in ['__pycache__', '.venv', '.git']):
                results.append(self.analyze_file(py_file))

        return results

    def generate_report(self, results: List[Dict]) -> str:
        """Generate a complexity analysis report."""
        report = ["# Code Complexity Analysis Report", ""]

        # Sort by lines of code
        sorted_results = sorted(results, key=lambda x: x['lines_of_code'], reverse=True)

        for result in sorted_results[:20]:  # Top 20 most complex files
            report.append(f"## {result['file_path']}")
            report.append(f"- **Lines of Code**: {result['lines_of_code']}")
            report.append(f"- **Functions**: {len(result['functions'])}")
            report.append(f"- **Classes**: {len(result['classes'])}")

            # Flag high-complexity functions
            high_complexity = [f for f in result['functions'] if f['complexity'] > 20]
            if high_complexity:
                report.append("- **High Complexity Functions**:"                for func in high_complexity:
                    report.append(f"  - `{func['name']}`: {func['complexity']} complexity")

            report.append("")

        return "\n".join(report)
```

### 1.2 Dependency Analysis

**Analyze code dependencies:**
```python
# tools/analysis/dependency_analyzer.py
import ast
import os
from pathlib import Path
from typing import Dict, Set, List

class DependencyAnalyzer:
    def __init__(self, root_path: str):
        self.root_path = Path(root_path)

    def analyze_imports(self, file_path: Path) -> Dict[str, Set[str]]:
        """Analyze import statements in a file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        tree = ast.parse(content)

        imports = {
            'internal': set(),
            'external': set(),
            'relative': set()
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports['external'].add(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0:  # Relative import
                    imports['relative'].add(node.module or '')
                elif node.module:
                    module_root = node.module.split('.')[0]
                    if self._is_internal_module(module_root):
                        imports['internal'].add(module_root)
                    else:
                        imports['external'].add(module_root)

        return imports

    def _is_internal_module(self, module_name: str) -> bool:
        """Check if a module is internal to the project."""
        internal_modules = ['src', 'ui', 'tools', 'tests']
        return module_name in internal_modules or (self.root_path / module_name).exists()

    def build_dependency_graph(self) -> Dict[str, Dict[str, Set[str]]]:
        """Build a dependency graph for all Python files."""
        graph = {}

        for py_file in self.root_path.rglob('*.py'):
            if not any(skip in str(py_file) for skip in ['__pycache__', '.venv', '.git']):
                rel_path = py_file.relative_to(self.root_path)
                graph[str(rel_path)] = self.analyze_imports(py_file)

        return graph
```

### 1.3 Refactoring Strategy Planning

**Identify refactoring opportunities:**
- **Extract Classes**: Convert functions into class methods
- **Split Modules**: Break large files into logical modules
- **Create Interfaces**: Define clear contracts between modules
- **Reduce Coupling**: Minimize dependencies between modules
- **Improve Testability**: Make code more unit-testable

## Phase 2: Core Application Refactoring (Week 2-3)

### 2.1 Break Down sermon_updater.py

**Current Structure Analysis:**
- **Lines**: 3,510
- **Main Functions**: CLI parsing, sermon processing, API integration
- **Issues**: Monolithic structure, mixed responsibilities

**New Modular Structure:**
```
src/
├── cli/
│   ├── __init__.py
│   ├── parser.py          # Command line argument parsing
│   ├── commands.py        # Command implementations
│   └── main.py           # CLI entry point
├── sermonaudio/
│   ├── __init__.py
│   ├── client.py         # API client
│   ├── models.py         # Data models
│   ├── processor.py      # Sermon processing logic
│   └── batch_processor.py # Batch processing
├── processing/
│   ├── __init__.py
│   ├── audio_processor.py # Audio processing coordination
│   ├── content_generator.py # AI content generation
│   └── validator.py      # Content validation
└── core/
    ├── __init__.py
    ├── config.py         # Configuration management
    ├── logging.py        # Logging setup
    └── exceptions.py     # Custom exceptions
```

**Migration Strategy:**

#### Step 1: Extract Configuration Management
```python
# src/core/config.py
from typing import Dict, Any, Optional
import os
from pathlib import Path
import yaml

class ConfigManager:
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._find_config_file()
        self._config = {}
        self._load_config()

    def _find_config_file(self) -> str:
        """Find configuration file in standard locations."""
        search_paths = [
            Path.cwd() / "config.yaml",
            Path.cwd() / "config.yml",
            Path.home() / ".sermon-processor" / "config.yaml",
            Path("/etc/sermon-processor/config.yaml")
        ]

        for path in search_paths:
            if path.exists():
                return str(path)

        return "config.yaml"  # Default fallback

    def _load_config(self):
        """Load configuration from file and environment."""
        if Path(self.config_path).exists():
            with open(self.config_path, 'r') as f:
                self._config = yaml.safe_load(f) or {}

        # Override with environment variables
        self._override_from_env()

    def _override_from_env(self):
        """Override configuration with environment variables."""
        env_mappings = {
            'SERMONAUDIO_API_KEY': ['api_key'],
            'SERMONAUDIO_BROADCASTER_ID': ['broadcaster_id'],
            'OPENAI_API_KEY': ['llm', 'primary', 'openai', 'api_key'],
            'OLLAMA_HOST': ['llm', 'primary', 'ollama', 'host'],
        }

        for env_var, config_path in env_mappings.items():
            value = os.getenv(env_var)
            if value:
                self._set_nested_value(self._config, config_path, value)

    def _set_nested_value(self, config: Dict, path: List[str], value: Any):
        """Set a value in nested dictionary structure."""
        current = config
        for key in path[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[path[-1]] = value

    def get(self, key_path: str, default=None):
        """Get configuration value using dot notation."""
        keys = key_path.split('.')
        value = self._config
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def set(self, key_path: str, value: Any):
        """Set configuration value using dot notation."""
        keys = key_path.split('.')
        self._set_nested_value(self._config, keys, value)

    def save(self):
        """Save current configuration to file."""
        with open(self.config_path, 'w') as f:
            yaml.dump(self._config, f, default_flow_style=False)
```

#### Step 2: Extract CLI Components
```python
# src/cli/parser.py
import argparse
from typing import List, Dict, Any

class CLIParser:
    def __init__(self):
        self.parser = argparse.ArgumentParser(
            description="SermonAudio Processor - AI-powered sermon enhancement",
            formatter_class=argparse.RawDescriptionHelpFormatter
        )
        self._setup_arguments()

    def _setup_arguments(self):
        """Set up command line arguments."""
        # Global options
        self.parser.add_argument(
            '--config', '-c',
            help='Path to configuration file'
        )
        self.parser.add_argument(
            '--verbose', '-v',
            action='store_true',
            help='Enable verbose logging'
        )
        self.parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes'
        )

        # Create subparsers for different commands
        subparsers = self.parser.add_subparsers(
            dest='command',
            help='Available commands'
        )

        # Sermon processing command
        process_parser = subparsers.add_parser(
            'process',
            help='Process sermons'
        )
        self._add_sermon_filters(process_parser)
        process_parser.add_argument(
            '--sermon-id',
            help='Process specific sermon by ID'
        )

        # List command
        list_parser = subparsers.add_parser(
            'list',
            help='List sermons'
        )
        self._add_sermon_filters(list_parser)

        # New sermon command
        new_parser = subparsers.add_parser(
            'new-sermon',
            help='Create new sermon from audio file'
        )
        new_parser.add_argument(
            'audio_file',
            help='Path to audio file'
        )
        new_parser.add_argument(
            '--speaker',
            help='Speaker name'
        )
        new_parser.add_argument(
            '--title',
            help='Sermon title'
        )

    def _add_sermon_filters(self, parser):
        """Add common sermon filtering arguments."""
        parser.add_argument(
            '--since-days',
            type=int,
            help='Process sermons from last N days'
        )
        parser.add_argument(
            '--event-type',
            help='Filter by event type'
        )
        parser.add_argument(
            '--speaker-name',
            help='Filter by speaker name'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='Maximum number of sermons to process'
        )

    def parse_args(self, args: List[str] = None) -> argparse.Namespace:
        """Parse command line arguments."""
        return self.parser.parse_args(args)
```

#### Step 3: Extract SermonAudio API Client
```python
# src/sermonaudio/client.py
import requests
from typing import Dict, List, Optional, Any
import time
from dataclasses import dataclass
from urllib.parse import urlencode

@dataclass
class Sermon:
    sermon_id: str
    title: str
    speaker: str
    date: str
    audio_url: Optional[str] = None
    video_url: Optional[str] = None
    transcript_url: Optional[str] = None
    pdf_url: Optional[str] = None
    event_type: Optional[str] = None
    series: Optional[str] = None

class SermonAudioClient:
    BASE_URL = "https://api.sermonaudio.com/v2"

    def __init__(self, api_key: str, broadcaster_id: str):
        self.api_key = api_key
        self.broadcaster_id = broadcaster_id
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        })

    def get_sermons(self, filters: Dict[str, Any] = None) -> List[Sermon]:
        """Get sermons with optional filtering."""
        params = filters or {}
        params['broadcasterID'] = self.broadcaster_id

        url = f"{self.BASE_URL}/sermons"
        response = self._make_request(url, params=params)

        sermons = []
        for item in response.get('sermons', []):
            sermons.append(Sermon(
                sermon_id=item['sermonID'],
                title=item.get('title', ''),
                speaker=item.get('speaker', ''),
                date=item.get('preachedDate', ''),
                audio_url=item.get('audioURL'),
                video_url=item.get('videoURL'),
                transcript_url=item.get('transcriptURL'),
                pdf_url=item.get('pdfURL'),
                event_type=item.get('eventType'),
                series=item.get('series')
            ))

        return sermons

    def get_sermon(self, sermon_id: str) -> Optional[Sermon]:
        """Get a specific sermon by ID."""
        url = f"{self.BASE_URL}/sermons/{sermon_id}"
        response = self._make_request(url)

        if not response:
            return None

        item = response.get('sermon', {})
        return Sermon(
            sermon_id=item['sermonID'],
            title=item.get('title', ''),
            speaker=item.get('speaker', ''),
            date=item.get('preachedDate', ''),
            audio_url=item.get('audioURL'),
            video_url=item.get('videoURL'),
            transcript_url=item.get('transcriptURL'),
            pdf_url=item.get('pdfURL'),
            event_type=item.get('eventType'),
            series=item.get('series')
        )

    def update_sermon(self, sermon_id: str, updates: Dict[str, Any]) -> bool:
        """Update sermon metadata."""
        url = f"{self.BASE_URL}/sermons/{sermon_id}"
        response = self._make_request(url, method='PUT', data=updates)
        return response is not None

    def upload_audio(self, sermon_id: str, audio_path: str) -> bool:
        """Upload audio file for a sermon."""
        url = f"{self.BASE_URL}/sermons/{sermon_id}/audio"

        with open(audio_path, 'rb') as f:
            files = {'audio': f}
            response = self.session.post(url, files=files)

        return response.status_code == 200

    def _make_request(self, url: str, method: str = 'GET',
                     params: Dict = None, data: Dict = None) -> Optional[Dict]:
        """Make HTTP request with error handling and retries."""
        max_retries = 3
        retry_delay = 1

        for attempt in range(max_retries):
            try:
                if method == 'GET':
                    response = self.session.get(url, params=params)
                elif method == 'PUT':
                    response = self.session.put(url, json=data)
                elif method == 'POST':
                    response = self.session.post(url, json=data)

                response.raise_for_status()
                return response.json()

            except requests.RequestException as e:
                if attempt == max_retries - 1:
                    print(f"Request failed after {max_retries} attempts: {e}")
                    return None

                time.sleep(retry_delay)
                retry_delay *= 2

        return None
```

### 2.2 Break Down streamlit_app.py

**Current Structure Analysis:**
- **Lines**: 357
- **Main Issues**: Single file handling all pages and routing
- **Responsibilities**: Page routing, component rendering, state management

**New Modular Structure:**
```
ui/
├── __init__.py
├── app.py                 # Main application entry point
├── routing.py            # Page routing logic
├── components/           # Reusable UI components
│   ├── __init__.py
│   ├── navigation.py     # Navigation sidebar
│   ├── forms.py         # Form components
│   ├── tables.py        # Data display components
│   └── charts.py        # Chart components
├── pages/               # Individual page modules
│   ├── __init__.py
│   ├── dashboard.py     # Dashboard page
│   ├── processing.py    # Sermon processing page
│   ├── analytics.py     # Analytics page
│   ├── validation.py    # Validation page
│   └── settings.py      # Settings page
└── utils/               # UI utilities
    ├── __init__.py
    ├── state.py         # State management
    ├── formatting.py    # Data formatting
    └── validation.py    # UI validation
```

**Migration Strategy:**

#### Step 1: Create Main Application Structure
```python
# ui/app.py
import streamlit as st
from ui.routing import get_current_page
from ui.components.navigation import render_sidebar
from ui.pages import (
    dashboard, processing, analytics,
    validation, settings
)

def main():
    """Main Streamlit application entry point."""
    # Configure page
    st.set_page_config(
        page_title="SermonAudio Processor",
        page_icon="🎵",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Initialize session state
    if 'current_page' not in st.session_state:
        st.session_state.current_page = 'dashboard'

    # Render navigation
    render_sidebar()

    # Route to current page
    page = get_current_page()

    page_map = {
        'dashboard': dashboard.render,
        'processing': processing.render,
        'analytics': analytics.render,
        'validation': validation.render,
        'settings': settings.render
    }

    if page in page_map:
        page_map[page]()
    else:
        st.error(f"Unknown page: {page}")

if __name__ == "__main__":
    main()
```

#### Step 2: Create Page Routing System
```python
# ui/routing.py
import streamlit as st
from typing import Optional

def get_current_page() -> str:
    """Get the current page from URL parameters or session state."""
    # Check URL parameters first
    params = st.query_params
    if 'page' in params:
        page = params['page']
        st.session_state.current_page = page
        return page

    # Fall back to session state
    return st.session_state.get('current_page', 'dashboard')

def navigate_to(page: str):
    """Navigate to a specific page."""
    st.session_state.current_page = page
    st.query_params['page'] = page
    st.rerun()

def get_page_title(page: str) -> str:
    """Get the display title for a page."""
    titles = {
        'dashboard': 'Dashboard',
        'processing': 'Sermon Processing',
        'analytics': 'Analytics',
        'validation': 'Validation',
        'settings': 'Settings'
    }
    return titles.get(page, page.title())
```

#### Step 3: Create Reusable Components
```python
# ui/components/navigation.py
import streamlit as st
from ui.routing import navigate_to, get_current_page

def render_sidebar():
    """Render the main navigation sidebar."""
    with st.sidebar:
        st.title("🎵 SermonAudio Processor")

        # Navigation menu
        pages = [
            ('dashboard', '📊 Dashboard', 'Main overview and status'),
            ('processing', '🎵 Processing', 'Process and enhance sermons'),
            ('analytics', '📈 Analytics', 'View performance metrics'),
            ('validation', '✅ Validation', 'Quality control and validation'),
            ('settings', '⚙️ Settings', 'Configuration and preferences')
        ]

        current_page = get_current_page()

        for page_id, title, description in pages:
            if st.button(
                title,
                key=f"nav_{page_id}",
                help=description,
                use_container_width=True,
                type="primary" if page_id == current_page else "secondary"
            ):
                navigate_to(page_id)

        # Divider
        st.divider()

        # System status
        render_system_status()

def render_system_status():
    """Render system status information."""
    st.subheader("System Status")

    # Mock status - replace with real status
    status_data = {
        "Database": "🟢 Connected",
        "Ollama": "🟢 Running",
        "GPU": "🟢 Available",
        "Disk Space": "🟢 85% free"
    }

    for component, status in status_data.items():
        st.caption(f"{component}: {status}")
```

#### Step 4: Create Individual Page Modules
```python
# ui/pages/dashboard.py
import streamlit as st
from ui.components.charts import render_metrics_chart
from ui.utils.state import get_recent_activity

def render():
    """Render the dashboard page."""
    st.header("📊 Dashboard")

    # Key metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Sermons", "1,247", "+12 this week")

    with col2:
        st.metric("Processing Queue", "3", "-2 from yesterday")

    with col3:
        st.metric("Success Rate", "98.5%", "+0.3%")

    with col4:
        st.metric("Avg Processing Time", "4.2 min", "-0.5 min")

    # Recent activity
    st.subheader("Recent Activity")
    activities = get_recent_activity(limit=10)

    if activities:
        for activity in activities:
            with st.container():
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    st.write(f"**{activity['title']}**")
                    st.caption(f"by {activity['speaker']}")
                with col2:
                    st.caption(activity['status'])
                with col3:
                    st.caption(activity['timestamp'])
    else:
        st.info("No recent activity")

    # Performance chart
    st.subheader("Performance Trends")
    render_metrics_chart()
```

## Phase 3: Supporting Module Refactoring (Week 4)

### 3.1 Refactor Audio Processing Module

**Current Issues:**
- Single file handling multiple audio processing algorithms
- Tight coupling between different processing methods
- Difficult to test individual components

**New Structure:**
```python
# src/audio/__init__.py
from .processor import AudioProcessor
from .enhancer import AudioEnhancer
from .utils import AudioUtils

__all__ = ['AudioProcessor', 'AudioEnhancer', 'AudioUtils']

# src/audio/processor.py
from typing import Optional, Dict, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class AudioProcessor:
    """Main audio processing coordinator."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.enhancer = AudioEnhancer(config)
        self.utils = AudioUtils()

    def process_audio(self, input_path: str, output_path: str,
                     enhancements: Dict[str, bool] = None) -> bool:
        """Process audio file with specified enhancements."""
        try:
            # Validate input
            if not self.utils.validate_audio_file(input_path):
                logger.error(f"Invalid audio file: {input_path}")
                return False

            # Apply enhancements
            enhancements = enhancements or self._get_default_enhancements()

            if enhancements.get('noise_reduction'):
                self.enhancer.reduce_noise(input_path, input_path)

            if enhancements.get('amplification'):
                self.enhancer.amplify(input_path, input_path)

            if enhancements.get('normalization'):
                self.enhancer.normalize(input_path, input_path)

            # Convert to output format if needed
            self.utils.convert_format(input_path, output_path)

            logger.info(f"Audio processing completed: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Audio processing failed: {e}")
            return False

    def _get_default_enhancements(self) -> Dict[str, bool]:
        """Get default enhancement settings from config."""
        return {
            'noise_reduction': self.config.get('audio_noise_reduction', True),
            'amplification': self.config.get('audio_amplify', True),
            'normalization': self.config.get('audio_normalize', True)
        }
```

### 3.2 Refactor LLM Manager Module

**Current Issues:**
- Single class handling multiple LLM providers
- Complex fallback logic mixed with provider-specific code
- Difficult to add new providers

**New Structure:**
```python
# src/llm/__init__.py
from .manager import LLMManager
from .providers import get_provider

__all__ = ['LLMManager', 'get_provider']

# src/llm/providers/__init__.py
from .base import LLMProvider
from .ollama import OllamaProvider
from .openai import OpenAIProvider
from .xai import XAIProvider

def get_provider(provider_name: str, config: Dict) -> LLMProvider:
    """Factory function to get LLM provider instance."""
    providers = {
        'ollama': OllamaProvider,
        'openai': OpenAIProvider,
        'xai': XAIProvider
    }

    provider_class = providers.get(provider_name.lower())
    if not provider_class:
        raise ValueError(f"Unknown LLM provider: {provider_name}")

    return provider_class(config)

# src/llm/providers/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class LLMResponse:
    text: str
    usage: Dict[str, int]
    model: str
    provider: str

class LLMProvider(ABC):
    """Base class for LLM providers."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.model = config.get('model', self.get_default_model())

    @abstractmethod
    def get_default_model(self) -> str:
        """Get the default model name for this provider."""
        pass

    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """Generate text using the LLM."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available."""
        pass

    def get_usage_info(self) -> Dict[str, Any]:
        """Get usage information for this provider."""
        return {
            'provider': self.__class__.__name__,
            'model': self.model,
            'available': self.is_available()
        }
```

## Phase 4: Testing and Validation (Week 5)

### 4.1 Create Unit Tests for New Modules

**Testing Strategy:**
```python
# tests/unit/test_cli_parser.py
import pytest
from src.cli.parser import CLIParser

class TestCLIParser:
    def test_parse_basic_args(self):
        parser = CLIParser()
        args = parser.parse_args(['--verbose', '--dry-run'])

        assert args.verbose is True
        assert args.dry_run is True

    def test_parse_process_command(self):
        parser = CLIParser()
        args = parser.parse_args(['process', '--sermon-id', '123', '--limit', '5'])

        assert args.command == 'process'
        assert args.sermon_id == '123'
        assert args.limit == 5

    def test_parse_list_command(self):
        parser = CLIParser()
        args = parser.parse_args(['list', '--since-days', '7', '--event-type', 'Sunday - AM'])

        assert args.command == 'list'
        assert args.since_days == 7
        assert args.event_type == 'Sunday - AM'
```

### 4.2 Integration Testing

**Integration Tests:**
```python
# tests/integration/test_sermonaudio_client.py
import pytest
from unittest.mock import Mock, patch
from src.sermonaudio.client import SermonAudioClient, Sermon

class TestSermonAudioClient:
    @pytest.fixture
    def client(self):
        return SermonAudioClient('test_key', 'test_broadcaster')

    @patch('src.sermonaudio.client.requests.Session.get')
    def test_get_sermons_success(self, mock_get, client):
        mock_response = Mock()
        mock_response.json.return_value = {
            'sermons': [{
                'sermonID': '123',
                'title': 'Test Sermon',
                'speaker': 'Test Speaker',
                'preachedDate': '2024-01-01'
            }]
        }
        mock_get.return_value = mock_response

        sermons = client.get_sermons()

        assert len(sermons) == 1
        assert sermons[0].sermon_id == '123'
        assert sermons[0].title == 'Test Sermon'

    @patch('src.sermonaudio.client.requests.Session.get')
    def test_get_sermons_api_error(self, mock_get, client):
        mock_get.side_effect = Exception("API Error")

        sermons = client.get_sermons()

        assert sermons == []
```

### 4.3 Performance Testing

**Performance Benchmarks:**
```python
# tests/performance/test_audio_processing.py
import pytest
import time
from pathlib import Path
from src.audio.processor import AudioProcessor

class TestAudioProcessingPerformance:
    @pytest.fixture
    def processor(self):
        config = {
            'audio_noise_reduction': True,
            'audio_amplify': True,
            'audio_normalize': True
        }
        return AudioProcessor(config)

    def test_processing_performance(self, processor, sample_audio_file):
        """Test that audio processing completes within time limits."""
        input_path = str(sample_audio_file)
        output_path = str(sample_audio_file.parent / 'output.wav')

        start_time = time.time()
        result = processor.process_audio(input_path, output_path)
        end_time = time.time()

        processing_time = end_time - start_time

        assert result is True
        assert processing_time < 30  # Should complete within 30 seconds
        assert Path(output_path).exists()
```

## Implementation Timeline

### Week 1: Analysis and Planning
- [ ] Run complexity analysis on all Python files
- [ ] Analyze dependencies between modules
- [ ] Create detailed refactoring plan
- [ ] Set up automated testing framework

### Week 2: Core Application Refactoring
- [ ] Extract configuration management
- [ ] Create CLI parser module
- [ ] Extract SermonAudio API client
- [ ] Test CLI functionality

### Week 3: UI Refactoring
- [ ] Create modular page structure
- [ ] Extract reusable components
- [ ] Implement routing system
- [ ] Test UI functionality

### Week 4: Supporting Module Refactoring
- [ ] Refactor audio processing module
- [ ] Refactor LLM manager module
- [ ] Update import statements
- [ ] Test module integrations

### Week 5: Testing and Validation
- [ ] Create comprehensive unit tests
- [ ] Implement integration tests
- [ ] Performance testing
- [ ] Documentation updates

## Success Criteria

### Code Quality Metrics
- [ ] Average cyclomatic complexity < 15
- [ ] Maximum function length < 50 lines
- [ ] Maximum file length < 500 lines
- [ ] Test coverage > 80%

### Maintainability Improvements
- [ ] Clear separation of concerns
- [ ] Modular architecture
- [ ] Comprehensive documentation
- [ ] Automated testing

### Developer Experience
- [ ] Easy to understand code structure
- [ ] Simple to add new features
- [ ] Reliable testing framework
- [ ] Clear development workflow

## Risk Mitigation

### Backup Strategy
- Create complete backup before major refactoring
- Use feature branches for each refactoring step
- Maintain working version throughout process

### Testing Strategy
- Run full test suite after each refactoring step
- Maintain backward compatibility during transition
- Use integration tests to validate end-to-end functionality

### Rollback Plan
- Keep original files during transition
- Document all changes for easy reversal
- Test critical paths before removing old code

This refactoring plan will transform the codebase from monolithic files into a well-structured, modular, and maintainable system that follows Python best practices and modern software architecture principles.
