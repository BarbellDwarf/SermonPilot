#!/usr/bin/env python3
"""
Local Environment Check for SermonAudio Processor

This script verifies that all local dependencies and services are available
before running integration tests.

Checks:
- Python environment and package availability
- External services (Ollama, APIs)
- GPU/CUDA availability
- Configuration files
- Audio processing capabilities
"""

import os
import sys
import subprocess
import importlib
from pathlib import Path
import json
import requests
import torch
import yaml
from typing import Dict, List, Any

def check_python_environment() -> Dict[str, Any]:
    """Check Python version and virtual environment."""
    env_check = {
        'python_version': sys.version,
        'python_executable': sys.executable,
        'virtual_env': os.environ.get('VIRTUAL_ENV'),
        'uv_available': False,
        'pip_available': False
    }
    
    # Check UV availability
    try:
        result = subprocess.run(['uv', '--version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            env_check['uv_available'] = True
            env_check['uv_version'] = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    # Check pip availability
    try:
        result = subprocess.run([sys.executable, '-m', 'pip', '--version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            env_check['pip_available'] = True
            env_check['pip_version'] = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    return env_check

def check_required_packages() -> Dict[str, Any]:
    """Check if required Python packages are available."""
    required_packages = [
        'streamlit', 'requests', 'yaml', 'numpy', 'pandas',
        'torch', 'torchaudio', 'pydub', 'librosa', 'soundfile',
        'deepfilternet', 'ollama', 'openai', 'chromadb',
        'sentence_transformers', 'plotly', 'psutil', 'tenacity'
    ]
    
    optional_packages = [
        'resemble_enhance', 'voicefixer', 'speechbrain', 'demucs'
    ]
    
    package_check = {
        'required': {},
        'optional': {},
        'missing_required': [],
        'missing_optional': []
    }
    
    # Check required packages
    for package in required_packages:
        try:
            module = importlib.import_module(package)
            version = getattr(module, '__version__', 'unknown')
            package_check['required'][package] = {
                'available': True,
                'version': version
            }
        except ImportError as e:
            package_check['required'][package] = {
                'available': False,
                'error': str(e)
            }
            package_check['missing_required'].append(package)
    
    # Check optional packages
    for package in optional_packages:
        try:
            module = importlib.import_module(package)
            version = getattr(module, '__version__', 'unknown')
            package_check['optional'][package] = {
                'available': True,
                'version': version
            }
        except ImportError as e:
            package_check['optional'][package] = {
                'available': False,
                'error': str(e)
            }
            package_check['missing_optional'].append(package)
    
    return package_check

def check_gpu_cuda_availability() -> Dict[str, Any]:
    """Check GPU and CUDA availability for AI processing."""
    gpu_check = {
        'cuda_available': torch.cuda.is_available(),
        'cuda_version': None,
        'gpu_count': 0,
        'gpu_devices': [],
        'memory_info': {}
    }
    
    if gpu_check['cuda_available']:
        gpu_check['cuda_version'] = torch.version.cuda
        gpu_check['gpu_count'] = torch.cuda.device_count()
        
        for i in range(gpu_check['gpu_count']):
            device_props = torch.cuda.get_device_properties(i)
            gpu_info = {
                'name': device_props.name,
                'memory_total': device_props.total_memory,
                'memory_available': torch.cuda.get_device_properties(i).total_memory - torch.cuda.memory_allocated(i),
                'compute_capability': f"{device_props.major}.{device_props.minor}"
            }
            gpu_check['gpu_devices'].append(gpu_info)
    
    return gpu_check

def check_ollama_service() -> Dict[str, Any]:
    """Check if Ollama service is running and available."""
    ollama_check = {
        'service_running': False,
        'accessible': False,
        'models': [],
        'version': None,
        'error': None
    }
    
    try:
        # Check if service is accessible
        response = requests.get('http://localhost:11434/api/tags', timeout=10)
        if response.status_code == 200:
            ollama_check['accessible'] = True
            data = response.json()
            ollama_check['models'] = [model['name'] for model in data.get('models', [])]
            
            # Try to get version
            try:
                version_response = requests.get('http://localhost:11434/api/version', timeout=5)
                if version_response.status_code == 200:
                    ollama_check['version'] = version_response.json().get('version')
            except:
                pass
        
        ollama_check['service_running'] = True
    
    except requests.exceptions.RequestException as e:
        ollama_check['error'] = str(e)
    
    return ollama_check

def check_configuration_files(project_root: Path) -> Dict[str, Any]:
    """Check configuration files and their completeness."""
    config_check = {
        'config_yaml_exists': False,
        'config_example_exists': False,
        'config_valid': False,
        'has_api_credentials': False,
        'has_llm_config': False,
        'placeholder_count': 0,
        'errors': []
    }
    
    config_file = project_root / 'config.yaml'
    example_file = project_root / 'config.example.yaml'
    
    config_check['config_yaml_exists'] = config_file.exists()
    config_check['config_example_exists'] = example_file.exists()
    
    if config_check['config_yaml_exists']:
        try:
            with open(config_file, 'r') as f:
                config_data = yaml.safe_load(f)
            
            config_check['config_valid'] = True
            
            # Check for API credentials
            if config_data.get('api_key') and 'your-' not in config_data['api_key']:
                config_check['has_api_credentials'] = True
            
            # Check for LLM configuration
            if config_data.get('llm'):
                config_check['has_llm_config'] = True
            
            # Count placeholders
            def count_placeholders(obj, path=''):
                count = 0
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        count += count_placeholders(value, f"{path}.{key}" if path else key)
                elif isinstance(obj, str):
                    if any(placeholder in obj.lower() for placeholder in ['your-', 'placeholder', 'example', 'replace']):
                        count += 1
                return count
            
            config_check['placeholder_count'] = count_placeholders(config_data)
            
        except Exception as e:
            config_check['errors'].append(f"Config parsing error: {str(e)}")
    
    return config_check

def check_audio_processing_capabilities() -> Dict[str, Any]:
    """Check audio processing library availability and functionality."""
    audio_check = {
        'pydub_available': False,
        'librosa_available': False,
        'soundfile_available': False,
        'deepfilternet_available': False,
        'sample_rate_support': {},
        'format_support': {},
        'errors': []
    }
    
    # Check pydub
    try:
        import pydub
        audio_check['pydub_available'] = True
    except ImportError as e:
        audio_check['errors'].append(f"pydub import error: {str(e)}")
    
    # Check librosa
    try:
        import librosa
        audio_check['librosa_available'] = True
        # Test basic functionality
        try:
            librosa.note_to_hz('C4')  # Simple test
        except Exception as e:
            audio_check['errors'].append(f"librosa functionality error: {str(e)}")
    except ImportError as e:
        audio_check['errors'].append(f"librosa import error: {str(e)}")
    
    # Check soundfile
    try:
        import soundfile
        audio_check['soundfile_available'] = True
    except ImportError as e:
        audio_check['errors'].append(f"soundfile import error: {str(e)}")
    
    # Check DeepFilterNet
    try:
        import deepfilternet
        audio_check['deepfilternet_available'] = True
    except ImportError as e:
        audio_check['errors'].append(f"deepfilternet import error: {str(e)}")
    
    return audio_check

def check_database_connectivity() -> Dict[str, Any]:
    """Check ChromaDB and vector database connectivity."""
    db_check = {
        'chromadb_available': False,
        'sentence_transformers_available': False,
        'db_accessible': False,
        'embedding_model_available': False,
        'errors': []
    }
    
    # Check ChromaDB
    try:
        import chromadb
        db_check['chromadb_available'] = True
        
        # Try to create a test client
        try:
            client = chromadb.Client()
            db_check['db_accessible'] = True
        except Exception as e:
            db_check['errors'].append(f"ChromaDB client error: {str(e)}")
    except ImportError as e:
        db_check['errors'].append(f"ChromaDB import error: {str(e)}")
    
    # Check sentence transformers
    try:
        import sentence_transformers
        db_check['sentence_transformers_available'] = True
        
        # Try to load a simple model
        try:
            model = sentence_transformers.SentenceTransformer('all-MiniLM-L6-v2')
            db_check['embedding_model_available'] = True
        except Exception as e:
            db_check['errors'].append(f"Embedding model loading error: {str(e)}")
    except ImportError as e:
        db_check['errors'].append(f"sentence_transformers import error: {str(e)}")
    
    return db_check

def run_comprehensive_environment_check(project_root: Path) -> Dict[str, Any]:
    """Run all environment checks and compile results."""
    print("🔍 Starting comprehensive environment check...")
    
    results = {
        'timestamp': str(Path(__file__).stat().st_mtime),
        'project_root': str(project_root),
        'python_environment': check_python_environment(),
        'packages': check_required_packages(),
        'gpu_cuda': check_gpu_cuda_availability(),
        'ollama': check_ollama_service(),
        'configuration': check_configuration_files(project_root),
        'audio_processing': check_audio_processing_capabilities(),
        'database': check_database_connectivity(),
        'overall_status': 'unknown'
    }
    
    # Determine overall status
    critical_failures = []
    warnings = []
    
    # Check critical components
    if results['packages']['missing_required']:
        critical_failures.append(f"Missing required packages: {', '.join(results['packages']['missing_required'])}")
    
    if not results['configuration']['config_yaml_exists']:
        critical_failures.append("config.yaml file not found")
    elif not results['configuration']['config_valid']:
        critical_failures.append("config.yaml is invalid")
    
    if not results['ollama']['accessible']:
        warnings.append("Ollama service not accessible")
    
    if not results['gpu_cuda']['cuda_available']:
        warnings.append("CUDA not available - will use CPU for AI processing")
    
    if critical_failures:
        results['overall_status'] = 'failed'
        results['critical_failures'] = critical_failures
    elif warnings:
        results['overall_status'] = 'degraded'
        results['warnings'] = warnings
    else:
        results['overall_status'] = 'ready'
    
    return results

def generate_environment_report(results: Dict[str, Any]) -> str:
    """Generate a human-readable environment check report."""
    report = []
    report.append("# SermonAudio Processor Local Environment Check")
    report.append(f"**Generated**: {results['timestamp']}")
    report.append("")
    
    # Overall status
    status = results['overall_status']
    status_icon = {
        'ready': '✅',
        'degraded': '⚠️',
        'failed': '❌'
    }.get(status, '❓')
    
    report.append(f"## {status_icon} Overall Status: {status.upper()}")
    report.append("")
    
    if status == 'failed' and 'critical_failures' in results:
        report.append("### ❌ Critical Failures")
        for failure in results['critical_failures']:
            report.append(f"- {failure}")
        report.append("")
    
    if 'warnings' in results:
        report.append("### ⚠️ Warnings")
        for warning in results['warnings']:
            report.append(f"- {warning}")
        report.append("")
    
    # Python environment
    python_env = results['python_environment']
    report.append("## 🐍 Python Environment")
    report.append(f"- **Version**: {python_env['python_version'].split()[0]}")
    report.append(f"- **Executable**: {python_env['python_executable']}")
    report.append(f"- **Virtual Environment**: {'Yes' if python_env['virtual_env'] else 'No'}")
    report.append(f"- **UV Available**: {'Yes' if python_env['uv_available'] else 'No'}")
    report.append(f"- **Pip Available**: {'Yes' if python_env['pip_available'] else 'No'}")
    report.append("")
    
    # Package status
    packages = results['packages']
    report.append("## 📦 Package Status")
    report.append(f"- **Required Packages Missing**: {len(packages['missing_required'])}")
    report.append(f"- **Optional Packages Missing**: {len(packages['missing_optional'])}")
    
    if packages['missing_required']:
        report.append("### ❌ Missing Required Packages")
        for package in packages['missing_required']:
            report.append(f"- `{package}`")
        report.append("")
    
    # GPU/CUDA status
    gpu = results['gpu_cuda']
    report.append("## 🎮 GPU/CUDA Status")
    report.append(f"- **CUDA Available**: {'Yes' if gpu['cuda_available'] else 'No'}")
    if gpu['cuda_available']:
        report.append(f"- **CUDA Version**: {gpu['cuda_version']}")
        report.append(f"- **GPU Count**: {gpu['gpu_count']}")
        for i, device in enumerate(gpu['gpu_devices']):
            memory_gb = device['memory_total'] / (1024**3)
            report.append(f"- **GPU {i}**: {device['name']} ({memory_gb:.1f} GB)")
    report.append("")
    
    # Ollama status
    ollama = results['ollama']
    report.append("## 🤖 Ollama Service")
    report.append(f"- **Service Running**: {'Yes' if ollama['service_running'] else 'No'}")
    report.append(f"- **Accessible**: {'Yes' if ollama['accessible'] else 'No'}")
    if ollama['accessible']:
        report.append(f"- **Models Available**: {len(ollama['models'])}")
        for model in ollama['models'][:5]:  # Show first 5 models
            report.append(f"  - {model}")
        if len(ollama['models']) > 5:
            report.append(f"  - ... and {len(ollama['models']) - 5} more")
    elif ollama['error']:
        report.append(f"- **Error**: {ollama['error']}")
    report.append("")
    
    # Configuration status
    config = results['configuration']
    report.append("## ⚙️ Configuration")
    report.append(f"- **config.yaml exists**: {'Yes' if config['config_yaml_exists'] else 'No'}")
    report.append(f"- **Configuration valid**: {'Yes' if config['config_valid'] else 'No'}")
    report.append(f"- **Has API credentials**: {'Yes' if config['has_api_credentials'] else 'No'}")
    report.append(f"- **Has LLM config**: {'Yes' if config['has_llm_config'] else 'No'}")
    report.append(f"- **Placeholder values**: {config['placeholder_count']}")
    report.append("")
    
    # Audio processing
    audio = results['audio_processing']
    report.append("## 🎵 Audio Processing")
    report.append(f"- **Pydub**: {'Available' if audio['pydub_available'] else 'Missing'}")
    report.append(f"- **Librosa**: {'Available' if audio['librosa_available'] else 'Missing'}")
    report.append(f"- **Soundfile**: {'Available' if audio['soundfile_available'] else 'Missing'}")
    report.append(f"- **DeepFilterNet**: {'Available' if audio['deepfilternet_available'] else 'Missing'}")
    report.append("")
    
    # Database
    database = results['database']
    report.append("## 🗄️ Database & RAG")
    report.append(f"- **ChromaDB**: {'Available' if database['chromadb_available'] else 'Missing'}")
    report.append(f"- **Sentence Transformers**: {'Available' if database['sentence_transformers_available'] else 'Missing'}")
    report.append(f"- **Database Accessible**: {'Yes' if database['db_accessible'] else 'No'}")
    report.append(f"- **Embedding Model**: {'Available' if database['embedding_model_available'] else 'Missing'}")
    report.append("")
    
    # Next steps
    report.append("## 🚀 Next Steps")
    if status == 'failed':
        report.append("1. **Fix critical failures** listed above before proceeding")
        report.append("2. Install missing required packages")
        report.append("3. Create or fix config.yaml file")
        report.append("4. Re-run environment check")
    elif status == 'degraded':
        report.append("1. **Review warnings** - some features may be limited")
        report.append("2. Consider addressing warnings for full functionality")
        report.append("3. You can proceed with testing with reduced capabilities")
    else:
        report.append("1. **Environment is ready** for full testing")
        report.append("2. Run local integration tests")
        report.append("3. Launch Streamlit UI for manual testing")
    
    report.append("")
    
    return "\n".join(report)

def main():
    """Run environment check."""
    # Find project root
    current_dir = Path(__file__).parent
    project_root = current_dir.parent.parent
    
    # Run comprehensive check
    results = run_comprehensive_environment_check(project_root)
    
    # Generate report
    report = generate_environment_report(results)
    
    # Save results
    output_dir = project_root / 'Tests' / 'local-tests'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    report_file = output_dir / 'environment-check-report.md'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    json_file = output_dir / 'environment-check-data.json'
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"✅ Environment check complete!")
    print(f"📄 Report saved to: {report_file}")
    print(f"📊 Raw data saved to: {json_file}")
    
    # Print summary
    status = results['overall_status']
    print(f"\n📊 Summary: {status.upper()}")
    
    if status == 'failed':
        print("❌ Critical failures prevent testing - fix issues before proceeding")
        return 1
    elif status == 'degraded':
        print("⚠️  Some capabilities limited - proceed with caution")
        return 0
    else:
        print("✅ Environment ready for full testing")
        return 0

if __name__ == '__main__':
    sys.exit(main())