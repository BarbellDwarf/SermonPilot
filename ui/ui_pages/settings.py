"""
Settings Page for SermonPilot

Handles configuration management, LLM provider setup, audio settings,
and validation criteria with web-based editing interface.
"""

import sys
from pathlib import Path

import streamlit as st
import yaml

from ui.ui_state import managed_expander

OPENAI_PRESETS = {
    "OpenAI": {
        "base_url": "",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
    },
    "Azure OpenAI": {
        "base_url": "https://YOUR_RESOURCE.openai.azure.com",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4"],
    },
    "Groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
        ],
    },
    "OpenRouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "models": [
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "anthropic/claude-3.5-sonnet",
            "google/gemini-2.0-flash-exp",
        ],
    },
    "xAI": {"base_url": "https://api.x.ai/v1", "models": ["grok-beta", "grok-2-1212"]},
    "DeepSeek": {
        "base_url": "https://api.deepseek.com",
        "models": ["deepseek-chat", "deepseek-reasoner"],
    },
    "Together AI": {
        "base_url": "https://api.together.xyz/v1",
        "models": [
            "mistralai/Mixtral-8x22B-Instruct-v0.1",
            "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        ],
    },
    "Perplexity": {"base_url": "https://api.perplexity.ai", "models": ["sonar-pro", "sonar"]},
    "Fireworks AI": {
        "base_url": "https://api.fireworks.ai/inference/v1",
        "models": [
            "accounts/fireworks/models/llama-v3p3-70b-instruct",
            "accounts/fireworks/models/llama-v3p1-8b-instruct",
        ],
    },
    "Anyscale": {
        "base_url": "https://api.endpoints.anyscale.com/v1",
        "models": ["meta-llama/Meta-Llama-3.1-70B-Instruct"],
    },
}


def show_settings():
    """Main settings management interface"""
    st.markdown('<div class="main-header">Settings</div>', unsafe_allow_html=True)

    feedback = st.session_state.pop('settings_feedback', None)
    if feedback:
        st.success(feedback)

    st.markdown(
        """
        <style>
        .stTabs [data-baseweb="tab-list"] { flex-wrap: wrap; gap: 0.25rem; }
        .stTabs [data-baseweb="tab"] { padding-left: 0.75rem; padding-right: 0.75rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "General",
        "LLM",
        "Audio",
        "Transcription",
        "Validation",
        "Advanced",
        "Templates",
    ], key="settings_tabs")

    with tab1:
        show_general_settings()

    with tab2:
        show_llm_settings()

    with tab3:
        show_audio_settings()

    with tab4:
        show_transcription_settings()

    with tab5:
        show_validation_settings()

    with tab6:
        show_advanced_settings()

    with tab7:
        show_prompt_templates()

def show_general_settings():
    """General configuration settings"""
    st.markdown("### General Configuration")

    config = st.session_state.get('config') or {}

    _init_general_session_state(config)

    if st.button("Save General Settings", type="primary", key="save_general_button"):
        save_general_settings()

    # API Configuration
    st.markdown("#### SermonAudio API")

    col1, col2 = st.columns(2)

    with col1:
        st.text_input(
            "API Key",
            key="settings_api_key",
            type="password",
            help="Your SermonAudio API key"
        )

    with col2:
        st.text_input(
            "Broadcaster ID",
            key="settings_broadcaster_id",
            help="Your SermonAudio broadcaster ID"
        )

    # Test API connection
    if st.session_state.get("settings_api_key") and st.session_state.get("settings_broadcaster_id"):
        if st.button("Test API Connection"):
            test_api_connection(
                st.session_state.get("settings_api_key", ""),
                st.session_state.get("settings_broadcaster_id", ""),
            )

    # Processing Options
    st.markdown("#### Processing Options")

    col1, col2 = st.columns(2)

    with col1:
        st.checkbox(
            "Dry Run Mode (Default)",
            key="settings_dry_run",
            help="Preview changes without uploading by default"
        )

        st.checkbox(
            "Debug Mode",
            key="settings_debug",
            help="Enable verbose debug output"
        )

    with col2:
        st.checkbox(
            "Hashtag Verification",
            key="settings_hashtag_verification",
            help="Verify hashtags through second LLM pass"
        )

    # Output Settings
    st.markdown("#### Output Settings")

    col1, col2 = st.columns(2)

    with col1:
        st.text_input(
            "Output Directory",
            key="settings_output_directory",
            help="Directory to store processed sermon files"
        )

        st.checkbox(
            "Save Original Audio",
            key="settings_save_original_audio",
            help="Keep copy of original audio file"
        )

    with col2:
        st.checkbox(
            "Save Transcript",
            key="settings_save_transcript",
            help="Save sermon transcript as text file"
        )

def initialize_llm_session_state(llm_config):
    """Initialize session state values from config if not already set"""

    # Primary provider settings
    primary_config = llm_config.get('primary', {})
    if 'primary_provider' not in st.session_state:
        st.session_state.primary_provider = primary_config.get('provider', 'ollama')

    # Initialize primary provider-specific session state
    initialize_provider_session_state(primary_config, st.session_state.primary_provider, 'primary')

    # Fallback provider settings
    fallback_config = llm_config.get('fallback', {})
    if 'fallback_enabled' not in st.session_state:
        st.session_state.fallback_enabled = fallback_config.get('enabled', False)
    if 'fallback_provider' not in st.session_state:
        st.session_state.fallback_provider = fallback_config.get('provider', 'openai')

    # Initialize fallback provider-specific session state
    if st.session_state.fallback_enabled:
        initialize_provider_session_state(
            fallback_config, st.session_state.fallback_provider, 'fallback'
        )

    # Validator provider settings
    validator_config = llm_config.get('validator', {})
    if 'validator_enabled' not in st.session_state:
        st.session_state.validator_enabled = validator_config.get('enabled', False)
    if 'validator_provider' not in st.session_state:
        st.session_state.validator_provider = validator_config.get('provider', 'ollama')

    # Initialize validator provider-specific session state
    if st.session_state.validator_enabled:
        initialize_provider_session_state(
            validator_config, st.session_state.validator_provider, 'validator'
        )

def initialize_provider_session_state(provider_config, provider_type, key_prefix):
    """Initialize provider-specific session state values from config"""
    if provider_type in provider_config:
        settings = provider_config[provider_type]

        if provider_type == 'ollama':
            if f'{key_prefix}_ollama_host' not in st.session_state:
                st.session_state[f'{key_prefix}_ollama_host'] = settings.get('host', 'http://localhost:11434')
            if f'{key_prefix}_ollama_model' not in st.session_state:
                st.session_state[f'{key_prefix}_ollama_model'] = settings.get('model', '')
            if f'{key_prefix}_ollama_api_key' not in st.session_state:
                st.session_state[f'{key_prefix}_ollama_api_key'] = settings.get('api_key', '')

        elif provider_type == 'openai':
            preset = settings.get('preset', 'OpenAI')
            if f'{key_prefix}_openai_preset' not in st.session_state:
                st.session_state[f'{key_prefix}_openai_preset'] = preset
            if f'{key_prefix}_openai_key' not in st.session_state:
                st.session_state[f'{key_prefix}_openai_key'] = settings.get('api_key', '')
            if f'{key_prefix}_openai_url' not in st.session_state:
                st.session_state[f'{key_prefix}_openai_url'] = settings.get('base_url', '')
            if f'{key_prefix}_openai_model' not in st.session_state:
                st.session_state[f'{key_prefix}_openai_model'] = settings.get(
                    'model', 'gpt-4o-mini'
                )

        elif provider_type in ('xai', 'groq', 'openrouter'):
            default_models = {
                'xai': 'grok-beta',
                'groq': 'llama-3.1-70b-versatile',
                'openrouter': 'openai/gpt-4o-mini',
            }
            if f'{key_prefix}_openai_preset' not in st.session_state:
                st.session_state[f'{key_prefix}_openai_preset'] = provider_type.title()
            if f'{key_prefix}_openai_key' not in st.session_state:
                st.session_state[f'{key_prefix}_openai_key'] = settings.get('api_key', '')
            if f'{key_prefix}_openai_url' not in st.session_state:
                st.session_state[f'{key_prefix}_openai_url'] = settings.get('base_url', '')
            if f'{key_prefix}_openai_model' not in st.session_state:
                st.session_state[f'{key_prefix}_openai_model'] = settings.get(
                    'model', default_models[provider_type]
                )

        # Clear cached models when API key changes
        if provider_type in ['openai', 'xai', 'groq', 'openrouter']:
            current_key = st.session_state.get(f'{key_prefix}_{provider_type}_key', '')
            stored_key = settings.get('api_key', '')
            if current_key != stored_key and current_key:
                # API key changed, clear cached models to force refresh
                st.session_state.pop(f'{key_prefix}_{provider_type}_models', None)

def show_llm_settings():
    """LLM provider configuration"""
    st.markdown("### LLM Provider Configuration")

    config = st.session_state.get('config') or {}
    llm_config = config.get('llm', {})

    # Initialize session state from config if not already set
    initialize_llm_session_state(llm_config)

    if st.button("Save LLM Settings", type="primary", key="save_llm_button"):
        save_llm_settings()

    # Primary Provider
    st.markdown("#### Primary Provider")

    primary_config = llm_config.get('primary', {})

    col1, col2 = st.columns(2)

    with col1:
        provider_options = ["ollama", "openai", "xai", "groq", "openrouter"]
        current_provider = primary_config.get('provider', 'ollama')
        if current_provider not in provider_options:
            current_provider = 'openai'

        primary_provider = st.selectbox(
            "Primary Provider",
            options=provider_options,
            key="primary_provider"
        )

    with col2:
        if st.button("Test Primary Provider"):
            test_llm_provider(primary_provider, primary_config.get(primary_provider, {}))

    if primary_provider == "ollama":
        show_ollama_settings("Primary", primary_config.get('ollama', {}), "primary")
    elif primary_provider == "openai":
        show_openai_settings("Primary", primary_config.get('openai', {}), "primary")
    elif primary_provider in ("xai", "groq", "openrouter"):
        show_openai_settings("Primary", primary_config.get(primary_provider, {}), "primary")

    # Fallback Provider
    st.markdown("#### Fallback Provider")

    fallback_config = llm_config.get('fallback', {})

    col1, col2 = st.columns(2)

    with col1:
        fallback_enabled = st.checkbox(
            "Enable Fallback Provider",
            key="fallback_enabled"
        )

    with col2:
        if fallback_enabled:
            provider_options = ["openai", "ollama", "xai", "groq", "openrouter"]
            current_fallback_provider = fallback_config.get('provider', 'openai')
            if current_fallback_provider not in provider_options:
                current_fallback_provider = 'openai'
            fallback_provider = st.selectbox(
                "Fallback Provider",
                options=provider_options,
                key="fallback_provider"
            )

    if fallback_enabled:
        if fallback_provider == "ollama":
            show_ollama_settings("Fallback", fallback_config.get('ollama', {}), "fallback")
        elif fallback_provider == "openai":
            show_openai_settings("Fallback", fallback_config.get('openai', {}), "fallback")
        elif fallback_provider in ("xai", "groq", "openrouter"):
            show_openai_settings("Fallback", fallback_config.get(fallback_provider, {}), "fallback")

    # Validator Provider
    st.markdown("#### Validator Provider (Optional)")

    validator_config = llm_config.get('validator', {})

    validator_enabled = st.checkbox(
        "Enable Validation Provider",
        help="Use smaller model for description validation",
        key="validator_enabled"
    )

    if validator_enabled:
        col1, col2 = st.columns(2)

        with col1:
            provider_options = ["ollama", "openai", "xai", "groq", "openrouter"]
            current_validator_provider = validator_config.get('provider', 'ollama')
            if current_validator_provider not in provider_options:
                current_validator_provider = 'openai'
            validator_provider = st.selectbox(
                "Validator Provider",
                options=provider_options,
                key="validator_provider"
            )

        if validator_provider == "ollama":
            show_ollama_settings("Validator", validator_config.get('ollama', {}), "validator")
        elif validator_provider == "openai":
            show_openai_settings("Validator", validator_config.get('openai', {}), "validator")
        elif validator_provider in ("xai", "groq", "openrouter"):
            cfg = validator_config.get(validator_provider, {})
            show_openai_settings("Validator", cfg, "validator")

def show_ollama_settings(label, config, key_prefix):
    """Show Ollama-specific settings with automatic model refresh"""
    col1, col2 = st.columns(2)

    with col1:
        host = st.text_input(
            f"{label} Ollama Host",
            key=f"{key_prefix}_ollama_host"
        )

        api_key = st.text_input(
            f"{label} Ollama API Key (Optional)",
            type="password",
            key=f"{key_prefix}_ollama_api_key",
            help="Required if Ollama is behind an authenticated proxy"
        )

    with col2:
        # Auto-refresh models when host changes or button clicked
        available_models = []
        refresh_clicked = st.button(
            f"Refresh {label} Models", key=f"{key_prefix}_refresh_models"
        )

        if refresh_clicked:
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
                from llm_manager import OllamaProvider

                with st.spinner(f"Fetching models from {host}..."):
                    ollama_provider = OllamaProvider({'host': host, 'api_key': api_key})
                    available_models = ollama_provider.list_models()
                st.session_state[f"{key_prefix}_ollama_models"] = available_models

                if available_models:
                    st.success(f"Found {len(available_models)} models")
                else:
                    st.warning("No models found - check Ollama connection")
            except Exception as e:
                st.error(f"Failed to fetch models: {e}")
                st.info(f"Make sure Ollama is running at {host}")

        # Get cached models if available
        cached_models = st.session_state.get(f"{key_prefix}_ollama_models", [])

        if cached_models:
            st.selectbox(
                f"{label} Ollama Model",
                options=cached_models,
                key=f"{key_prefix}_ollama_model",
                help="Select from available Ollama models"
            )
        else:
            st.text_input(
                f"{label} Ollama Model",
                key=f"{key_prefix}_ollama_model",
                help="Enter model name (click Refresh to see available models)"
            )

def show_openai_settings(label, config, key_prefix):
    """Show OpenAI-compatible provider settings with preset dropdown"""
    preset_names = list(OPENAI_PRESETS.keys())
    stored_preset = config.get('preset', 'OpenAI')
    if stored_preset not in preset_names:
        stored_preset = 'OpenAI'

    selected_preset = st.selectbox(
        f"{label} API Type",
        options=preset_names,
        key=f"{key_prefix}_openai_preset",
        help="Select the OpenAI-compatible API provider"
    )

    preset = OPENAI_PRESETS[selected_preset]

    col1, col2 = st.columns(2)

    with col1:
        api_key = st.text_input(
            f"{label} API Key",
            type="password",
            key=f"{key_prefix}_openai_key"
        )

        base_url = st.text_input(
            f"{label} Base URL",
            placeholder=preset['base_url'] or "https://api.openai.com/v1",
            help=f"Base URL for {selected_preset} API",
            key=f"{key_prefix}_openai_url"
        )

    with col2:
        model_options = list(preset['models'])

        if api_key and st.button(f"Load {label} Models", key=f"{key_prefix}_load_models"):
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
                from llm_manager import OpenAIProvider

                provider_config = {'api_key': api_key}
                if base_url:
                    provider_config['base_url'] = base_url

                openai_provider = OpenAIProvider(provider_config)
                available_models = openai_provider.list_models()

                if available_models:
                    st.session_state[f"{key_prefix}_openai_models"] = available_models
                    st.success(f"Loaded {len(available_models)} models")
                    model_options = available_models[:20]
                else:
                    st.warning("No models found - check API credentials")
            except Exception as e:
                st.error(f"Failed to load models: {e}")

        cached_models = st.session_state.get(f"{key_prefix}_openai_models", [])
        if cached_models:
            model_options = cached_models[:20]

        if model_options and len(model_options) > 1:
            st.selectbox(
                f"{label} Model",
                options=model_options,
                key=f"{key_prefix}_openai_model"
            )
        else:
            st.text_input(
                f"{label} Model",
                key=f"{key_prefix}_openai_model"
            )


def show_audio_settings():
    """Audio processing configuration"""
    st.markdown("### Audio Processing Configuration")

    config = st.session_state.get('config') or {}

    _init_audio_session_state(config)

    if st.button("Save Audio Settings", type="primary", key="save_audio_button"):
        save_audio_settings()

    # Enhancement Method
    st.markdown("#### Enhancement Method")

    methods = ["deepfilternet", "clear-natural", "clear-studio", "custom", "none"]

    enhancement_method = st.selectbox(
        "Audio Enhancement Method",
        options=methods,
        key="settings_enhancement_method",
        help=(
            "DeepFilterNet: standard (best for speech). Clear-Natural: gentler noise "
            "suppression. Clear-Studio: aggressive, podcast-ready. Custom: point to any "
            "ONNX model on HuggingFace."
        )
    )

    if enhancement_method == "custom":
        st.caption("Configure a custom ONNX model from HuggingFace:")
        st.text_input(
            "HF Repo (e.g. tonythethompson/DeepFilterNet3-ONNX)",
            key="settings_custom_repo",
        )
        st.text_input(
            "ONNX filename (e.g. model.onnx)",
            key="settings_custom_file",
        )
        if (
            st.session_state.get("settings_custom_repo")
            and st.session_state.get("settings_custom_file")
        ):
            st.info(
                f"Will use: **{st.session_state['settings_custom_repo']}"
                f"/{st.session_state['settings_custom_file']}**"
            )
        else:
            st.warning("Enter both a HuggingFace repo and ONNX filename.")

    st.selectbox(
        "Enhancement Device",
        options=["auto", "cpu", "cuda"],
        key="settings_enhancement_device",
        help=(
            "auto: use the GPU unless its total VRAM is below the configured "
            "threshold, then run enhancement on CPU so whisper keeps the card. "
            "cpu: always enhance on CPU (slower, but leaves the GPU free). "
            "cuda: always enhance on the GPU."
        ),
    )

    # Enhancement options
    st.markdown("#### Processing Options")

    col1, col2 = st.columns(2)

    with col1:
        st.checkbox(
            "Noise Reduction",
            key="settings_noise_reduction",
            help="Apply noise reduction during processing"
        )

        st.checkbox(
            "Audio Amplification",
            key="settings_amplify",
            help="Apply audio amplification"
        )

    with col2:
        st.checkbox(
            "Audio Normalization",
            key="settings_normalize",
            help="Normalize audio levels"
        )

        st.slider(
            "Gain (dB)",
            min_value=-10.0,
            max_value=10.0,
            step=0.1,
            key="settings_gain_db",
            format="%.1f dB",
            help="Audio gain adjustment in decibels"
        )

        st.slider(
            "Target Level (dB)",
            min_value=-30.0,
            max_value=-10.0,
            step=1.0,
            key="settings_target_level_db",
            format="%.0f dB",
            help="Target audio level for normalization"
        )

def show_transcription_settings():
    """Transcription configuration"""
    st.markdown("### Transcription Configuration")

    config = st.session_state.get('config') or {}
    transcription_cfg = config.get('transcription', {})

    _init_transcription_session_state(transcription_cfg)

    if st.button("Save Transcription Settings", type="primary", key="save_transcription_button"):
        save_transcription_settings()

    st.markdown("#### Backend")
    backend_options = ["faster_whisper_local", "whisper_openai", "whisper_openrouter"]
    display_names = {
        "faster_whisper_local": "Faster Whisper (Local)",
        "whisper_openai": "OpenAI Whisper API",
        "whisper_openrouter": "OpenRouter Whisper API",
    }
    backend_key = st.selectbox(
        "Transcription Backend",
        options=backend_options,
        format_func=lambda x: display_names.get(x, x),
        key="settings_trans_backend",
        help="Local Whisper (runs on your machine) or API-based transcription"
    )

    if backend_key == "faster_whisper_local":
        st.markdown("#### Local Whisper Settings")
        col1, col2 = st.columns(2)

        with col1:
            model_options = [
                "tiny", "tiny.en", "base", "base.en", "small", "small.en", "medium",
                "medium.en", "large", "large-v2", "large-v3", "large-v3-turbo",
            ]
            st.selectbox(
                "Model",
                options=model_options,
                key="settings_trans_local_model",
                help="Model size. Larger = better accuracy but slower"
            )
            st.selectbox(
                "Device",
                options=["auto", "cpu", "cuda"],
                key="settings_trans_device",
                help="Compute device"
            )

        with col2:
            st.selectbox(
                "Compute Type",
                options=["auto", "float16", "float32", "int8_float16", "int8"],
                key="settings_trans_compute_type",
                help="auto: int8 on cpu, float16 on cuda (recommended for 8 GB cards)"
            )
            st.text_input(
                "Language",
                key="settings_trans_language",
                help="Language code (e.g. 'en' for English)"
            )

    elif backend_key == "whisper_openai":
        st.markdown("#### OpenAI API Settings")
        col1, col2 = st.columns(2)

        with col1:
            st.text_input(
                "API Key",
                key="settings_trans_openai_key",
                type="password",
                help="OpenAI API key (or set OPENAI_API_KEY env var)"
            )
            st.text_input(
                "Base URL",
                key="settings_trans_openai_base_url",
                help="OpenAI-compatible API endpoint"
            )

        with col2:
            st.text_input(
                "Model",
                key="settings_trans_openai_model",
                help="API model name (e.g. whisper-1)"
            )

    elif backend_key == "whisper_openrouter":
        st.markdown("#### OpenRouter API Settings")
        col1, col2 = st.columns(2)

        with col1:
            st.text_input(
                "API Key",
                key="settings_trans_or_key",
                type="password",
                help="OpenRouter API key (or set OPENROUTER_API_KEY env var)"
            )
            st.text_input(
                "Base URL",
                key="settings_trans_or_base_url",
                help="OpenRouter API endpoint"
            )

        with col2:
            st.text_input(
                "Model",
                key="settings_trans_or_model",
                help="API model name"
            )

def save_transcription_settings():
    """Save transcription settings to configuration"""
    if not st.session_state.get('config'):
        st.session_state.config = {}
    config = st.session_state.config
    if 'transcription' not in config:
        config['transcription'] = {}

    backend = st.session_state.get('settings_trans_backend', 'faster_whisper_local')
    config['transcription']['backend'] = backend

    if backend in ("whisper_local", "faster_whisper_local"):
        if backend not in config['transcription']:
            config['transcription'][backend] = {}
        config['transcription'][backend]['model'] = st.session_state.get(
            'settings_trans_local_model', 'base'
        )
        config['transcription'][backend]['device'] = st.session_state.get(
            'settings_trans_device', 'auto'
        )
        config['transcription']['compute_type'] = st.session_state.get(
            'settings_trans_compute_type', 'auto'
        )
        config['transcription'][backend]['compute_type'] = config['transcription']['compute_type']
        config['transcription'][backend]['language'] = st.session_state.get(
            'settings_trans_language', 'en'
        )

    elif backend == "whisper_openai":
        if 'whisper_openai' not in config['transcription']:
            config['transcription']['whisper_openai'] = {}
        api_key = st.session_state.get('settings_trans_openai_key', '')
        if api_key:
            config['transcription']['whisper_openai']['api_key'] = api_key
        config['transcription']['whisper_openai']['base_url'] = st.session_state.get(
            'settings_trans_openai_base_url', 'https://api.openai.com/v1'
        )
        config['transcription']['whisper_openai']['model'] = st.session_state.get(
            'settings_trans_openai_model', 'whisper-1'
        )

    elif backend == "whisper_openrouter":
        if 'whisper_openrouter' not in config['transcription']:
            config['transcription']['whisper_openrouter'] = {}
        api_key = st.session_state.get('settings_trans_or_key', '')
        if api_key:
            config['transcription']['whisper_openrouter']['api_key'] = api_key
        config['transcription']['whisper_openrouter']['base_url'] = st.session_state.get(
            'settings_trans_or_base_url', 'https://openrouter.ai/api/v1'
        )
        config['transcription']['whisper_openrouter']['model'] = st.session_state.get(
            'settings_trans_or_model', 'openai/whisper-large-v3'
        )

    from config_utils import save_config_to_file as _save_config
    if _save_config(config):
        st.success("Transcription settings saved and configuration reloaded!")

def show_validation_settings():
    """Validation criteria configuration"""
    st.markdown("### Validation Configuration")

    config = st.session_state.get('config') or {}
    metadata_config = config.get('metadata_processing', {})

    _init_validation_session_state(metadata_config)

    if st.button("Save Validation Settings", type="primary", key="save_validation_button"):
        save_validation_settings()

    # Description validation
    st.markdown("#### Description Validation")

    desc_config = metadata_config.get('description', {})
    desc_validation = desc_config.get('validation', {})

    validation_enabled = st.checkbox(
        "Enable Description Validation",
        key="validation_enabled",
        help="Use AI to validate description quality"
    )

    if validation_enabled:
        st.markdown("**Validation Criteria:**")

        criteria = desc_validation.get('criteria', [])
        mirror = st.session_state.get('settings_validation_criteria')
        if mirror is None or len(mirror) != len(criteria):
            st.session_state['settings_validation_criteria'] = list(criteria)
        mirror = st.session_state['settings_validation_criteria']

        edited = []
        for i, _criterion in enumerate(criteria):
            edited.append(
                st.text_input(
                    f"Criterion {i+1}",
                    value=mirror[i] if i < len(mirror) else '',
                    placeholder="Validation criterion text",
                ).strip()
            )
        st.session_state['settings_validation_criteria'] = edited

        if st.session_state.pop('clear_new_criterion', False):
            st.session_state['new_criterion'] = ''

        st.text_input(
            "Add new criterion:",
            key="new_criterion",
            placeholder="e.g. Contains a scripture reference",
        )

        if st.button("Add Criterion", key="add_criterion_button"):
            _add_validation_criterion()

    # Metadata processing settings
    st.markdown("#### Processing Settings")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Description Settings:**")

        st.checkbox(
            "Update if Missing",
            key="desc_update_missing",
        )

        st.checkbox(
            "Update if Minimal",
            key="desc_update_minimal",
        )

        st.number_input(
            "Min Length Threshold",
            min_value=10,
            max_value=200,
            key="desc_min_length",
        )

    with col2:
        st.markdown("**Hashtag Settings:**")

        st.checkbox(
            "Update if Missing",
            key="hash_update_missing",
        )

        st.checkbox(
            "Update if Minimal",
            key="hash_update_minimal",
        )

        st.number_input(
            "Min Length Threshold",
            min_value=5,
            max_value=50,
            key="hash_min_length",
        )




def show_prompt_templates():
    """Prompt template editor for LLM generation tasks."""
    st.markdown("### Prompt Templates")
    st.caption("Customize the instructions sent to the LLM for each generation task. "
               "Changes take effect immediately on save.")

    config = st.session_state.get('config') or {}
    templates = config.get('prompt_templates', {})

    _init_prompt_template_state(templates)

    if st.button("Save Prompt Templates", type="primary", key="save_prompt_templates_button"):
        save_prompt_templates()
        st.success("Prompt templates saved!")

    template_names = {
        "title": "Title Generation",
        "short_title": "Short Title Generation",
        "description": "Description Generation",
        "hashtags": "Hashtag Generation",
        "hashtag_verification": "Hashtag Verification",
        "description_validation": "Description Validation",
    }

    for key, label in template_names.items():
        with managed_expander(label, expanded=False):
            st.checkbox("Enabled", key=f"pt_{key}_enabled")
            st.text_area(
                "System Prompt",
                height=60,
                key=f"pt_{key}_system",
                help="System-level instruction for the LLM. Leave empty to omit."
            )
            st.text_area(
                "User Prompt",
                height=200,
                key=f"pt_{key}_user",
                help="User message template. Use {variable} placeholders for dynamic content."
            )
            st.caption(f"Available variables: {_get_template_vars(key)}")


def _get_template_vars(template_key: str) -> str:
    vars_map = {
        "title": "{context}, {transcript}",
        "short_title": "{full_title}",
        "description": "{role_desc}, {body_desc}, {transcript}, {speaker_instruction}",
        "hashtags": "{text}",
        "hashtag_verification": "{initial_hashtags}, {original_text}",
        "description_validation": "{context_info}, {criteria_text}, {description}",
    }
    return vars_map.get(template_key, "{}")


def save_prompt_templates():
    """Save prompt templates from session state to config."""
    config = st.session_state.get('config', {})
    if 'prompt_templates' not in config:
        config['prompt_templates'] = {}

    template_keys = [
        "title", "short_title", "description", "hashtags",
        "hashtag_verification", "description_validation",
    ]

    for key in template_keys:
        enabled = st.session_state.get(f"pt_{key}_enabled", True)
        system_val = st.session_state.get(f"pt_{key}_system", "")
        user_val = st.session_state.get(f"pt_{key}_user", "")
        config['prompt_templates'][key] = {
            'enabled': enabled,
            'system': system_val,
            'user': user_val,
        }

    from config_utils import save_config_to_file as _save_config
    _save_config(config)


def show_advanced_settings():
    """Backup, restore, and config management"""
    sub_tab1, sub_tab2 = st.tabs(["YAML Backup & Restore", "SQL Config Manager"])

    with sub_tab1:
        show_yaml_backup_restore()

    with sub_tab2:
        show_sql_config_management()

def show_yaml_backup_restore():
    """Simple YAML-based backup and restore"""
    st.markdown("### YAML Backup & Restore")

    config = st.session_state.get('config') or {}

    if config:
        masked_config = _mask_secrets(config)
        config_yaml = yaml.dump(masked_config, default_flow_style=False, sort_keys=True)
        with managed_expander("Current Configuration", expanded=True):
            st.code(config_yaml, language='yaml')
        st.download_button(
            "Download Config",
            data=config_yaml,
            file_name="config_backup.yaml",
            mime="text/yaml",
            help=(
                "Secrets are masked as '***' in this export. "
                "Masked values cannot be restored directly."
            ),
        )

    st.markdown("#### Restore Configuration")
    uploaded_config = st.file_uploader(
        "Upload Configuration File",
        type=['yaml', 'yml'],
        help="Upload a configuration file to restore settings"
    )

    if uploaded_config:
        try:
            config_content = uploaded_config.read().decode('utf-8')
            new_config = yaml.safe_load(config_content)
            st.success("Configuration file loaded successfully!")
            if isinstance(new_config, dict):
                masked_paths = _find_masked_secrets(new_config)
                if masked_paths:
                    st.error(
                        "This backup contains masked secrets ('***') where API keys "
                        "should be. Applying it would overwrite your real keys with "
                        "the mask, so the restore was rejected. "
                        "Edit the file to remove masked values or paste the real "
                        "keys first. Affected keys: "
                        + ", ".join(masked_paths[:10])
                        + ("…" if len(masked_paths) > 10 else "")
                    )
                else:
                    masked_preview = yaml.dump(
                        _mask_secrets(new_config), default_flow_style=False, sort_keys=True
                    )
                    st.code(masked_preview, language='yaml')
                    if st.button("Apply Configuration", type="primary"):
                        st.session_state.config = new_config
                        from config_utils import save_config_to_file
                        if save_config_to_file(new_config):
                            _clear_settings_widget_keys()
                            st.session_state['settings_feedback'] = (
                                "Configuration applied and saved!"
                            )
                            st.rerun()
            else:
                st.error("Configuration file must contain a YAML mapping at the top level.")
        except Exception as e:
            st.error(f"Failed to load configuration: {e}")

    st.markdown("#### Reset to Defaults")
    st.warning("This will reset all settings to default values")
    if st.button("Reset to Defaults", type="secondary"):
        if st.session_state.get('confirm_reset'):
            reset_to_defaults()
            st.session_state.pop('confirm_reset', None)
            _clear_settings_widget_keys()
            st.session_state['settings_feedback'] = "Configuration reset to defaults!"
            st.rerun()
        else:
            st.session_state.confirm_reset = True
            st.warning("Click again to confirm reset")

def show_sql_config_management():
    """SQL-based config management editor, import/export, history"""
    from ui.ui_pages.config_management import (
        SQL_CONFIG_AVAILABLE,
        show_config_editor,
        show_config_history,
        show_import_export,
    )

    if not SQL_CONFIG_AVAILABLE:
        st.error("SQL Configuration system is not available.")
        return

    db_path = "sermon_config.db"
    import os
    db_exists = os.path.exists(db_path)

    if not db_exists:
        st.info("Configuration database not found. Create one below.")
        from ui.ui_pages.config_management import show_database_setup
        show_database_setup(db_path)
        return

    cm_tab1, cm_tab2, cm_tab3 = st.tabs([
        "Edit Config",
        "Import/Export",
        "History"
    ])

    with cm_tab1:
        show_config_editor(db_path)

    with cm_tab2:
        show_import_export(db_path)

    with cm_tab3:
        show_config_history(db_path)

def test_api_connection(api_key, broadcaster_id):
    """Test SermonAudio API connection"""
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from sermonaudio_api import SermonAudioAPI

        api = SermonAudioAPI(api_key=api_key, broadcaster_id=broadcaster_id)
        result = api.test_connection()
        if result:
            st.success("API connection successful!")
        else:
            st.error("API connection failed")
    except Exception as e:
        st.error(f"API connection failed: {e}")

def test_llm_provider(provider, config):
    """Test LLM provider connection"""
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
        from llm_manager import LLMManager

        full_config = st.session_state.get('config', {})
        llm_manager = LLMManager(full_config)
        test_response = llm_manager.chat([{"role": "user", "content": "Reply with just: OK"}])
        if test_response:
            cleaned = str(test_response).strip().strip('"').strip("'").strip()
            if cleaned.upper() == 'OK' or 'OK' in cleaned.upper():
                st.success(f"{provider.title()} provider connection successful!")
            else:
                st.warning(f"{provider.title()} responded but unexpected: {cleaned[:100]}")
        else:
            st.error(f"{provider.title()} returned empty response")
    except Exception as e:
        st.error(f"{provider.title()} provider connection failed: {e}")

def save_general_settings():
    """Save general settings to configuration"""
    if not st.session_state.get('config'):
        st.session_state.config = {}

    st.session_state.config.update({
        'api_key': st.session_state.get('settings_api_key', ''),
        'broadcaster_id': st.session_state.get('settings_broadcaster_id', ''),
        'dry_run': st.session_state.get('settings_dry_run', False),
        'debug': st.session_state.get('settings_debug', False),
        'hashtag_verification': st.session_state.get('settings_hashtag_verification', True),
        'output_directory': st.session_state.get('settings_output_directory', 'processed_sermons'),
        'save_original_audio': st.session_state.get('settings_save_original_audio', True),
        'save_transcript': st.session_state.get('settings_save_transcript', True),
    })

    save_config_to_file(st.session_state.config)
    st.success("General settings saved and configuration reloaded!")

def save_llm_settings():
    """Save LLM settings to configuration"""
    if not st.session_state.get('config'):
        st.session_state.config = {}

    # Initialize LLM config if it doesn't exist
    if 'llm' not in st.session_state.config:
        st.session_state.config['llm'] = {}

    llm_config = st.session_state.config['llm']

    # Save Primary Provider Settings
    primary_provider = st.session_state.get('primary_provider', 'ollama')
    if 'primary' not in llm_config:
        llm_config['primary'] = {}
    llm_config['primary']['provider'] = primary_provider

    # Save primary provider-specific settings
    save_provider_settings(llm_config['primary'], primary_provider, 'primary')

    # Save Fallback Provider Settings
    fallback_enabled = st.session_state.get('fallback_enabled', False)
    if 'fallback' not in llm_config:
        llm_config['fallback'] = {}
    llm_config['fallback']['enabled'] = fallback_enabled

    if fallback_enabled:
        fallback_provider = st.session_state.get('fallback_provider', 'openai')
        llm_config['fallback']['provider'] = fallback_provider
        save_provider_settings(llm_config['fallback'], fallback_provider, 'fallback')

    # Save Validator Provider Settings
    validator_enabled = st.session_state.get('validator_enabled', False)
    if 'validator' not in llm_config:
        llm_config['validator'] = {}
    llm_config['validator']['enabled'] = validator_enabled

    if validator_enabled:
        validator_provider = st.session_state.get('validator_provider', 'ollama')
        llm_config['validator']['provider'] = validator_provider
        save_provider_settings(llm_config['validator'], validator_provider, 'validator')

    # Save to file
    if save_config_to_file(st.session_state.config):
        st.success("LLM settings saved and configuration reloaded!")

def save_provider_settings(provider_config, provider_type, key_prefix):
    """Save provider-specific settings from session state"""
    if provider_type not in provider_config:
        provider_config[provider_type] = {}

    provider_settings = provider_config[provider_type]

    if provider_type == 'ollama':
        host = st.session_state.get(f'{key_prefix}_ollama_host', 'http://localhost:11434')
        model = st.session_state.get(f'{key_prefix}_ollama_model', '')
        api_key = st.session_state.get(f'{key_prefix}_ollama_api_key', '')
        provider_settings['host'] = host
        if model:
            provider_settings['model'] = model
        else:
            provider_settings.pop('model', None)
        if api_key:
            provider_settings['api_key'] = api_key

    elif provider_type == 'openai':
        preset = st.session_state.get(f'{key_prefix}_openai_preset', 'OpenAI')
        api_key = st.session_state.get(f'{key_prefix}_openai_key', '')
        base_url = st.session_state.get(f'{key_prefix}_openai_url', '')
        model = st.session_state.get(f'{key_prefix}_openai_model', 'gpt-4o-mini')
        provider_settings['preset'] = preset
        if api_key:
            provider_settings['api_key'] = api_key
        if base_url:
            provider_settings['base_url'] = base_url
        provider_settings['model'] = model

    elif provider_type in ('xai', 'groq', 'openrouter'):
        api_key = st.session_state.get(f'{key_prefix}_openai_key', '')
        base_url = st.session_state.get(f'{key_prefix}_openai_url', '')
        model = st.session_state.get(f'{key_prefix}_openai_model', '')
        if api_key:
            provider_settings['api_key'] = api_key
        if base_url:
            provider_settings['base_url'] = base_url
        provider_settings['model'] = model

def save_audio_settings():
    """Save audio settings to configuration"""
    if not st.session_state.get('config'):
        st.session_state.config = {}

    enhancement = dict(st.session_state.config.get('enhancement') or {})
    enhancement['device'] = st.session_state.get('settings_enhancement_device', 'auto')

    st.session_state.config.update({
        'audio_enhancement_method': st.session_state.get(
            'settings_enhancement_method', 'deepfilternet'
        ),
        'audio_noise_reduction': st.session_state.get('settings_noise_reduction', True),
        'audio_amplify': st.session_state.get('settings_amplify', True),
        'audio_normalize': st.session_state.get('settings_normalize', True),
        'audio_gain_db': st.session_state.get('settings_gain_db', 0.5),
        'audio_target_level_db': st.session_state.get('settings_target_level_db', -22.0),
        'enhancement': enhancement,
    })

    save_config_to_file(st.session_state.config)
    st.success("Audio settings saved and configuration reloaded!")

def save_validation_settings():
    """Save validation settings to configuration"""
    if not st.session_state.get('config'):
        st.session_state.config = {}

    config = st.session_state.config
    if 'metadata_processing' not in config:
        config['metadata_processing'] = {}

    mp = config['metadata_processing']

    criteria = [
        c for c in st.session_state.get('settings_validation_criteria', []) if c.strip()
    ]
    new_val = st.session_state.get('new_criterion', '')
    if new_val.strip():
        criteria.append(new_val.strip())
        st.session_state['new_criterion'] = ''

    if 'description' not in mp:
        mp['description'] = {}
    mp['description']['validation'] = {
        'enabled': st.session_state.get('validation_enabled', True),
        'criteria': criteria,
    }
    mp['description']['update_if_missing'] = st.session_state.get('desc_update_missing', True)
    mp['description']['update_if_minimal'] = st.session_state.get('desc_update_minimal', True)
    mp['description']['min_length_threshold'] = st.session_state.get('desc_min_length', 50)

    if 'hashtags' not in mp:
        mp['hashtags'] = {}
    mp['hashtags']['update_if_missing'] = st.session_state.get('hash_update_missing', True)
    mp['hashtags']['update_if_minimal'] = st.session_state.get('hash_update_minimal', True)
    mp['hashtags']['min_length_threshold'] = st.session_state.get('hash_min_length', 10)

    save_config_to_file(config)
    st.success("Validation settings saved!")

def save_config_to_file(config):
    """Persist configuration to the settings database and reload the session"""
    from config_utils import save_config_to_file as _save_config
    return _save_config(config)

def _init_general_session_state(config):
    """Initialize General tab widget keys from config if not already set"""
    defaults = {
        "settings_api_key": config.get('api_key', ''),
        "settings_broadcaster_id": config.get('broadcaster_id', ''),
        "settings_dry_run": config.get('dry_run', False),
        "settings_debug": config.get('debug', False),
        "settings_hashtag_verification": config.get('hashtag_verification', True),
        "settings_output_directory": config.get('output_directory', 'processed_sermons'),
        "settings_save_original_audio": config.get('save_original_audio', True),
        "settings_save_transcript": config.get('save_transcript', True),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def _init_audio_session_state(config):
    """Initialize Audio tab widget keys from config if not already set"""
    methods = ["deepfilternet", "clear-natural", "clear-studio", "custom", "none"]
    method = config.get('audio_enhancement_method', 'deepfilternet')
    if method not in methods:
        method = methods[0]

    enhancement_device = (config.get('enhancement') or {}).get('device', 'auto')
    if enhancement_device not in ("auto", "cpu", "cuda"):
        enhancement_device = "auto"

    defaults = {
        "settings_enhancement_method": method,
        "settings_enhancement_device": enhancement_device,
        "settings_custom_repo": config.get('clear_custom_repo', ''),
        "settings_custom_file": config.get('clear_custom_file', ''),
        "settings_noise_reduction": config.get('audio_noise_reduction', True),
        "settings_amplify": config.get('audio_amplify', True),
        "settings_normalize": config.get('audio_normalize', True),
        "settings_gain_db": float(config.get('audio_gain_db', 0.5)),
        "settings_target_level_db": float(config.get('audio_target_level_db', -22.0)),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def _init_transcription_session_state(transcription_cfg):
    """Initialize Transcription tab widget keys from config if not already set"""
    local_cfg = transcription_cfg.get('faster_whisper_local', {})
    openai_cfg = transcription_cfg.get('whisper_openai', {})
    or_cfg = transcription_cfg.get('whisper_openrouter', {})

    backend_options = ["faster_whisper_local", "whisper_openai", "whisper_openrouter"]
    model_options = [
        "tiny", "tiny.en", "base", "base.en", "small", "small.en", "medium",
        "medium.en", "large", "large-v2", "large-v3", "large-v3-turbo",
    ]
    device_options = ["auto", "cpu", "cuda"]
    compute_options = ["auto", "float16", "float32", "int8_float16", "int8"]

    backend = transcription_cfg.get('backend', 'faster_whisper_local')
    if backend not in backend_options:
        backend = backend_options[0]

    model = local_cfg.get('model', 'base')
    if model not in model_options:
        model = 'base'

    device = local_cfg.get('device', 'auto')
    if device not in device_options:
        device = device_options[0]

    compute_type = transcription_cfg.get('compute_type') or local_cfg.get('compute_type') or 'auto'
    if compute_type not in compute_options:
        compute_type = 'auto'

    defaults = {
        "settings_trans_backend": backend,
        "settings_trans_local_model": model,
        "settings_trans_device": device,
        "settings_trans_compute_type": compute_type,
        "settings_trans_language": local_cfg.get('language', 'en'),
        "settings_trans_openai_key": openai_cfg.get('api_key', ''),
        "settings_trans_openai_base_url": openai_cfg.get('base_url', 'https://api.openai.com/v1'),
        "settings_trans_openai_model": openai_cfg.get('model', 'whisper-1'),
        "settings_trans_or_key": or_cfg.get('api_key', ''),
        "settings_trans_or_base_url": or_cfg.get('base_url', 'https://openrouter.ai/api/v1'),
        "settings_trans_or_model": or_cfg.get('model', 'openai/whisper-large-v3'),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def _init_validation_session_state(metadata_config):
    """Initialize Validation tab widget keys from config if not already set"""
    desc_config = metadata_config.get('description', {})
    desc_validation = desc_config.get('validation', {})
    hashtag_config = metadata_config.get('hashtags', {})

    defaults = {
        "validation_enabled": desc_validation.get('enabled', True),
        "desc_update_missing": desc_config.get('update_if_missing', True),
        "desc_update_minimal": desc_config.get('update_if_minimal', True),
        "desc_min_length": desc_config.get('min_length_threshold', 50),
        "hash_update_missing": hashtag_config.get('update_if_missing', True),
        "hash_update_minimal": hashtag_config.get('update_if_minimal', True),
        "hash_min_length": hashtag_config.get('min_length_threshold', 10),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def _add_validation_criterion():
    """Persist the pending criterion to the live config and refresh the form"""
    pending = st.session_state.get("new_criterion", "").strip()
    if not pending:
        st.warning("Enter a criterion before adding it.")
        return
    if not st.session_state.get('config'):
        st.session_state.config = {}
    config = st.session_state.config
    mp = config.setdefault('metadata_processing', {})
    desc = mp.setdefault('description', {})
    validation = desc.setdefault('validation', {})
    criteria = [
        c for c in st.session_state.get('settings_validation_criteria', []) if c.strip()
    ]
    criteria.append(pending)
    validation['criteria'] = criteria
    st.session_state['settings_validation_criteria'] = criteria
    st.session_state['clear_new_criterion'] = True
    from config_utils import save_config_to_file
    save_config_to_file(config)
    st.rerun()

def _init_prompt_template_state(templates):
    """Initialize Prompt Templates widget keys from config if not already set"""
    template_keys = [
        "title", "short_title", "description", "hashtags",
        "hashtag_verification", "description_validation",
    ]
    for key in template_keys:
        tmpl = templates.get(key, {})
        defaults = {
            f"pt_{key}_enabled": tmpl.get('enabled', True),
            f"pt_{key}_system": tmpl.get('system', ''),
            f"pt_{key}_user": tmpl.get('user', ''),
        }
        for k, value in defaults.items():
            if k not in st.session_state:
                st.session_state[k] = value

def _mask_secrets(value):
    """Return a copy of a config value with secret-bearing keys masked"""
    if isinstance(value, dict):
        masked = {}
        for key, item in value.items():
            if 'key' in str(key).lower() and isinstance(item, str) and item:
                masked[key] = '***'
            else:
                masked[key] = _mask_secrets(item)
        return masked
    if isinstance(value, list):
        return [_mask_secrets(item) for item in value]
    return value

def _find_masked_secrets(value, prefix: str = "") -> list[str]:
    """Return the config paths whose value is the '***' mask sentinel"""
    paths: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if item == '***':
                paths.append(path)
            else:
                paths.extend(_find_masked_secrets(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            path = f"{prefix}[{index}]"
            if item == '***':
                paths.append(path)
            else:
                paths.extend(_find_masked_secrets(item, path))
    return paths


def _clear_settings_widget_keys():
    """Drop Settings widget keys so they re-initialize from the new config"""
    keys = [
        "settings_api_key", "settings_broadcaster_id", "settings_dry_run", "settings_debug",
        "settings_hashtag_verification", "settings_output_directory",
        "settings_save_original_audio", "settings_save_transcript",
        "primary_provider", "fallback_enabled", "fallback_provider",
        "validator_enabled", "validator_provider",
        "primary_embedding_provider",
        "settings_enhancement_method", "settings_custom_repo", "settings_custom_file",
        "settings_noise_reduction", "settings_amplify",
        "settings_normalize", "settings_gain_db", "settings_target_level_db",
        "settings_trans_backend", "settings_trans_local_model", "settings_trans_device",
        "settings_trans_compute_type", "settings_trans_language",
        "settings_trans_openai_key", "settings_trans_openai_base_url",
        "settings_trans_openai_model", "settings_trans_or_key",
        "settings_trans_or_base_url", "settings_trans_or_model",
        "validation_enabled", "new_criterion", "settings_validation_criteria",
        "desc_update_missing", "desc_update_minimal", "desc_min_length",
        "hash_update_missing", "hash_update_minimal", "hash_min_length",
        "confirm_reset",
    ]
    for prefix in ("primary_", "fallback_", "validator_"):
        for suffix in (
            "ollama_host", "ollama_model", "ollama_api_key",
            "openai_preset", "openai_key", "openai_url", "openai_model",
                "st_model", "openai_embedding_key", "openai_embedding_url",
            "openai_embedding_model", "ollama_embedding_host", "ollama_embedding_model",
        ):
            keys.append(f"{prefix}{suffix}")
    for name in (
        "title", "short_title", "description", "hashtags",
        "hashtag_verification", "description_validation",
    ):
        keys.append(f"pt_{name}_enabled")
        keys.append(f"pt_{name}_system")
        keys.append(f"pt_{name}_user")
    for key in keys:
        st.session_state.pop(key, None)

def reset_to_defaults():
    """Reset configuration to default values"""
    # Load example config as defaults
    try:
        project_root = Path(__file__).parent.parent.parent
        example_config_path = project_root / "config" / "config.example.yaml"

        with open(example_config_path) as f:
            default_config = yaml.safe_load(f)

        st.session_state.config = default_config
        from config_utils import save_config_to_file
        save_config_to_file(default_config)

    except Exception as e:
        st.error(f"Failed to reset to defaults: {e}")

if __name__ == "__main__":
    show_settings()
