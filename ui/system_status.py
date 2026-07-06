"""
System Status Manager - Real-time status indicators for sidebar

Provides accurate system status checking for:
- SermonAudio API connection and authentication
- Database connectivity and health
- LLM provider status (primary and fallback)
- Audio enhancement availability
- Local storage status and capacity
- Processing queue status
"""

import logging
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

# Add parent directory to path for imports
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))
sys.path.insert(0, str(parent_dir / "src"))

# Import sermonaudio only if available (not critical for status check)
try:
    import sermonaudio
    sermonaudio_available = True
except ImportError:
    sermonaudio_available = False

from database import SermonRepository

logger = logging.getLogger(__name__)

class SystemStatusManager:
    """Manages real-time system status checks"""

    def __init__(self, config: dict[str, Any]):
        """Initialize with configuration"""
        self.config = config
        self.api_key = config.get('api_key')
        self.broadcaster_id = config.get('broadcaster_id')
        self.output_directory = Path(config.get('output_directory', 'processed_sermons'))

        # Initialize SermonAudio API if credentials available (but not required for basic checks)
        if self.api_key and sermonaudio_available:
            sermonaudio.set_api_key(self.api_key)

    def get_comprehensive_status(self) -> dict[str, dict[str, Any]]:
        """Get comprehensive system status"""
        return {
            'sermonaudio_api': self.check_sermonaudio_api(),
            'database': self.check_database(),
            'llm_primary': self.check_llm_provider('primary'),
            'llm_fallback': self.check_llm_provider('fallback'),
            'audio_enhancement': self.check_audio_enhancement(),
            'local_storage': self.check_local_storage(),
            'processing_queue': self.check_processing_queue(),
            'system_resources': self.check_system_resources()
        }

    def check_sermonaudio_api(self) -> dict[str, Any]:
        """Check SermonAudio API connection and authentication"""
        try:
            if not self.api_key or not self.broadcaster_id:
                return {
                    'status': 'error',
                    'message': 'API credentials not configured',
                    'details': 'Missing api_key or broadcaster_id in config',
                    'timestamp': datetime.now()
                }

            # Test API connection with the correct SermonAudio API format
            try:
                # Use the correct API base URL and authentication method
                base_url = 'https://api.sermonaudio.com/v2/'
                headers = {
                    'X-Api-Key': self.api_key,
                    'Content-Type': 'application/json'
                }

                # Test with a simple sermon query limited to 1 result
                params = {
                    'broadcasterID': self.broadcaster_id,
                    'pageSize': 1,
                    'lite': 'true',
                    'cache': 'true'
                }

                response = requests.get(
                    f"{base_url}node/sermons",
                    headers=headers,
                    params=params,
                    timeout=10
                )

                if response.status_code == 200:
                    data = response.json()
                    sermon_count = data.get('count', 0)
                    return {
                        'status': 'ok',
                        'message': 'API connected and authenticated',
                        'details': f'Successfully connected to SermonAudio API ({sermon_count} sermons available)',
                        'timestamp': datetime.now()
                    }
                elif response.status_code == 401:
                    return {
                        'status': 'error',
                        'message': 'Authentication failed',
                        'details': 'Invalid API key or insufficient permissions',
                        'timestamp': datetime.now()
                    }
                elif response.status_code == 403:
                    return {
                        'status': 'error',
                        'message': 'Access forbidden',
                        'details': 'API key lacks permission for broadcaster',
                        'timestamp': datetime.now()
                    }
                elif response.status_code == 404:
                    return {
                        'status': 'error',
                        'message': 'Broadcaster not found',
                        'details': f'Broadcaster ID {self.broadcaster_id} not found',
                        'timestamp': datetime.now()
                    }
                else:
                    return {
                        'status': 'warning',
                        'message': f'API responded with status {response.status_code}',
                        'details': f'Unexpected response: {response.text[:100]}',
                        'timestamp': datetime.now()
                    }

            except requests.exceptions.Timeout:
                return {
                    'status': 'warning',
                    'message': 'API connection timeout',
                    'details': 'SermonAudio API is slow or unreachable',
                    'timestamp': datetime.now()
                }
            except requests.exceptions.ConnectionError:
                return {
                    'status': 'error',
                    'message': 'Cannot connect to SermonAudio API',
                    'details': 'Network connection issue or API is down',
                    'timestamp': datetime.now()
                }

        except Exception as e:
            return {
                'status': 'error',
                'message': 'API check failed',
                'details': str(e),
                'timestamp': datetime.now()
            }

    def check_database(self) -> dict[str, Any]:
        """Check database connection and health"""
        try:
            repo = SermonRepository()

            # Test basic database operations
            stats = repo.get_processing_stats()

            # Check database size and performance
            db_path = repo.db.db_path
            if db_path.exists():
                db_size_mb = db_path.stat().st_size / (1024 * 1024)

                # Test query performance
                start_time = datetime.now()
                with repo.db.get_connection() as conn:
                    conn.execute("SELECT COUNT(*) FROM sermons").fetchone()
                query_time = (datetime.now() - start_time).total_seconds()

                status_details = f"Database size: {db_size_mb:.1f}MB, Query time: {query_time:.3f}s"

                if query_time > 1.0:  # Slow query warning
                    status = 'warning'
                    message = f"Database slow ({query_time:.3f}s query time)"
                else:
                    status = 'ok'
                    message = f"Database healthy ({stats['total_sermons']} sermons)"

                return {
                    'status': status,
                    'message': message,
                    'details': status_details,
                    'timestamp': datetime.now()
                }
            else:
                return {
                    'status': 'warning',
                    'message': 'Database file not found',
                    'details': f'Database will be created at: {db_path}',
                    'timestamp': datetime.now()
                }

        except sqlite3.Error as e:
            return {
                'status': 'error',
                'message': 'Database error',
                'details': str(e),
                'timestamp': datetime.now()
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': 'Database check failed',
                'details': str(e),
                'timestamp': datetime.now()
            }

    def check_llm_provider(self, provider_type: str = 'primary') -> dict[str, Any]:
        """Check LLM provider status (primary or fallback)"""
        try:
            llm_config = self.config.get('llm', {}).get(provider_type, {})

            if not llm_config.get('provider'):
                return {
                    'status': 'error',
                    'message': f'{provider_type.title()} LLM not configured',
                    'details': f'No {provider_type} LLM provider configured',
                    'timestamp': datetime.now()
                }

            provider = llm_config['provider']

            if provider == 'ollama':
                return self._check_ollama_status(llm_config, provider_type)
            elif provider in ['openai', 'anthropic', 'xai', 'google', 'groq', 'openrouter']:
                return self._check_api_llm_status(llm_config, provider_type)
            else:
                return {
                    'status': 'warning',
                    'message': f'Unknown {provider_type} LLM provider: {provider}',
                    'details': f'Provider {provider} not recognized',
                    'timestamp': datetime.now()
                }

        except Exception as e:
            return {
                'status': 'error',
                'message': f'{provider_type.title()} LLM check failed',
                'details': str(e),
                'timestamp': datetime.now()
            }

    def _check_ollama_status(self, llm_config: dict, provider_type: str) -> dict[str, Any]:
        """Check Ollama server status"""
        try:
            host = llm_config.get('ollama', {}).get('host', 'http://localhost:11434')
            model = llm_config.get('ollama', {}).get('model', 'unknown')

            # Check if Ollama server is running
            response = requests.get(f"{host}/api/tags", timeout=5)

            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = []
                for m in models:
                    try:
                        model_names.append(m.get('model') or m.get('name'))
                    except Exception:
                        continue
                model_names = [n for n in model_names if n]

                if model in model_names:
                    return {
                        'status': 'ok',
                        'message': f'{provider_type.title()} Ollama ready ({model})',
                        'details': f'Ollama server running with {len(models)} models',
                        'timestamp': datetime.now()
                    }
                else:
                    return {
                        'status': 'warning',
                        'message': f'{provider_type.title()} model not found',
                        'details': f'Model "{model}" not available. Available: {", ".join(model_names[:3])}{"..." if len(model_names) > 3 else ""}',
                        'timestamp': datetime.now()
                    }
            else:
                return {
                    'status': 'error',
                    'message': f'{provider_type.title()} Ollama server error',
                    'details': f'Server responded with status {response.status_code}',
                    'timestamp': datetime.now()
                }

        except requests.exceptions.ConnectionError:
            return {
                'status': 'error',
                'message': f'{provider_type.title()} Ollama server not running',
                'details': f'Cannot connect to Ollama at {host}',
                'timestamp': datetime.now()
            }
        except requests.exceptions.Timeout:
            return {
                'status': 'warning',
                'message': f'{provider_type.title()} Ollama server slow',
                'details': 'Ollama server is responding slowly',
                'timestamp': datetime.now()
            }

    def _check_api_llm_status(self, llm_config: dict, provider_type: str) -> dict[str, Any]:
        """Check API-based LLM provider status"""
        provider = llm_config['provider']
        provider_config = llm_config.get(provider, {})

        api_key = provider_config.get('api_key')
        model = provider_config.get('model', 'unknown')

        if not api_key:
            return {
                'status': 'error',
                'message': f'{provider_type.title()} {provider} API key missing',
                'details': f'No API key configured for {provider}',
                'timestamp': datetime.now()
            }

        # Just check that configuration is present - actual API calls would be expensive
        return {
            'status': 'ok',
            'message': f'{provider_type.title()} {provider} configured ({model})',
            'details': f'API key configured for {provider}',
            'timestamp': datetime.now()
        }

    def check_audio_enhancement(self) -> dict[str, Any]:
        """Check audio enhancement availability"""
        try:
            method = self.config.get('audio_enhancement_method', 'none')

            if method == 'none':
                return {
                    'status': 'warning',
                    'message': 'Audio enhancement disabled',
                    'details': 'Set audio_enhancement_method in config to enable',
                    'timestamp': datetime.now()
                }

            # Check if required packages are available
            if method == 'deepfilternet':
                try:
                    import df  # DeepFilterNet uses 'df' package name
                    return {
                        'status': 'ok',
                        'message': 'DeepFilterNet ready',
                        'details': 'DeepFilterNet package available',
                        'timestamp': datetime.now()
                    }
                except ImportError:
                    return {
                        'status': 'error',
                        'message': 'DeepFilterNet not installed',
                        'details': 'Install with: pip install deepfilternet',
                        'timestamp': datetime.now()
                    }

            else:
                return {
                    'status': 'warning',
                    'message': f'Unknown enhancement method: {method}',
                    'details': 'Check audio_enhancement_method in config',
                    'timestamp': datetime.now()
                }

        except Exception as e:
            return {
                'status': 'error',
                'message': 'Audio enhancement check failed',
                'details': str(e),
                'timestamp': datetime.now()
            }

    def check_local_storage(self) -> dict[str, Any]:
        """Check local storage status and capacity"""
        try:
            output_dir = self.output_directory

            if not output_dir.exists():
                return {
                    'status': 'warning',
                    'message': 'Output directory does not exist',
                    'details': f'Directory will be created: {output_dir}',
                    'timestamp': datetime.now()
                }

            # Count local sermons
            from src.sermon_paths import discover_sermons
            sermon_dirs = discover_sermons(output_dir)
            local_count = len(sermon_dirs)

            # Calculate total size
            total_size = 0
            audio_files = 0
            for sermon_dir in sermon_dirs:
                for file_path in sermon_dir.rglob('*'):
                    if file_path.is_file():
                        total_size += file_path.stat().st_size
                        if file_path.suffix.lower() == '.mp3':
                            audio_files += 1

            total_size_gb = total_size / (1024 * 1024 * 1024)

            # Check available disk space
            import shutil
            total, used, free = shutil.disk_usage(output_dir)
            free_gb = free / (1024 * 1024 * 1024)

            details = f"{local_count} sermons, {audio_files} audio files, {total_size_gb:.1f}GB used, {free_gb:.1f}GB free"

            if free_gb < 1.0:  # Less than 1GB free
                status = 'warning'
                message = 'Low disk space'
            else:
                status = 'ok'
                message = f'{local_count} local sermons'

            return {
                'status': status,
                'message': message,
                'details': details,
                'timestamp': datetime.now()
            }

        except Exception as e:
            return {
                'status': 'error',
                'message': 'Storage check failed',
                'details': str(e),
                'timestamp': datetime.now()
            }

    def check_processing_queue(self) -> dict[str, Any]:
        """Check processing queue status"""
        try:
            repo = SermonRepository()

            with repo.db.get_connection() as conn:
                # Count sermons by status
                status_counts = conn.execute("""
                    SELECT status, COUNT(*) as count
                    FROM sermons
                    GROUP BY status
                """).fetchall()

                # Count pending processing tasks
                pending_count = conn.execute("""
                    SELECT COUNT(*) as count
                    FROM processing_status
                    WHERE status IN ('pending', 'processing')
                """).fetchone()

            status_dict = {row['status']: row['count'] for row in status_counts}
            pending = pending_count['count'] if pending_count else 0

            processing = status_dict.get('processing', 0)
            failed = status_dict.get('failed', 0)

            if processing > 0:
                status = 'processing'
                message = f'{processing} sermons processing'
            elif pending > 0:
                status = 'warning'
                message = f'{pending} sermons pending'
            elif failed > 0:
                status = 'warning'
                message = f'{failed} sermons failed'
            else:
                status = 'ok'
                message = 'No active processing'

            details = f"Processing: {processing}, Pending: {pending}, Failed: {failed}"

            return {
                'status': status,
                'message': message,
                'details': details,
                'timestamp': datetime.now()
            }

        except Exception as e:
            return {
                'status': 'error',
                'message': 'Queue check failed',
                'details': str(e),
                'timestamp': datetime.now()
            }

    def check_system_resources(self) -> dict[str, Any]:
        """Check system resource availability"""
        try:
            import psutil

            # CPU and memory usage
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            memory_percent = memory.percent

            # GPU availability (if CUDA available)
            gpu_available = False
            gpu_info = "Not available"

            try:
                import torch
                if torch.cuda.is_available():
                    gpu_available = True
                    gpu_count = torch.cuda.device_count()
                    gpu_name = torch.cuda.get_device_name(0) if gpu_count > 0 else "Unknown"
                    gpu_info = f"{gpu_count} GPU(s) - {gpu_name}"
            except ImportError:
                pass

            details = f"CPU: {cpu_percent:.1f}%, Memory: {memory_percent:.1f}%, GPU: {gpu_info}"

            if cpu_percent > 90 or memory_percent > 90:
                status = 'warning'
                message = 'High resource usage'
            else:
                status = 'ok'
                message = 'Resources available'

            return {
                'status': status,
                'message': message,
                'details': details,
                'timestamp': datetime.now()
            }

        except ImportError:
            return {
                'status': 'warning',
                'message': 'Resource monitoring unavailable',
                'details': 'Install psutil for resource monitoring',
                'timestamp': datetime.now()
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': 'Resource check failed',
                'details': str(e),
                'timestamp': datetime.now()
            }

# Global instance
_status_manager = None

def get_status_manager(config: dict[str, Any] | None = None) -> SystemStatusManager:
    """Get global status manager instance"""
    global _status_manager

    if _status_manager is None:
        if config is None:
            # Load default config
            try:
                import yaml
                with open('config.yaml') as f:
                    config = yaml.safe_load(f)
            except FileNotFoundError:
                config = {}

        _status_manager = SystemStatusManager(config)

    return _status_manager

def get_status_emoji(status: str) -> str:
    """Get emoji for status"""
    status_map = {
        'ok': '✅',
        'warning': '⚠️',
        'error': '❌',
        'processing': '⏳'
    }
    return status_map.get(status, '❓')
