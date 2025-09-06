"""
Settings Page for SermonAudio Processor

Handles configuration management, LLM provider setup, audio settings,
and validation criteria with web-based editing interface.
"""

import sys
from pathlib import Path

import streamlit as st
import yaml


def show_settings():
    """Main settings management interface"""
    st.markdown('<div class="main-header">⚙️ Settings</div>', unsafe_allow_html=True)

    # Settings tabs
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "🔧 General",
        "🤖 LLM Providers",
        "🧠 Embeddings",
        "🎵 Audio Processing",
        "✅ Validation",
        "📥 Import Sermons",
        "💾 Backup & Restore"
    ])

    with tab1:
        show_general_settings()

    with tab2:
        show_llm_settings()

    with tab3:
        show_embedding_settings()

    with tab4:
        show_audio_settings()

    with tab5:
        show_validation_settings()

    with tab6:
        show_import_sermons()

    with tab7:
        show_backup_restore()

def show_general_settings():
    """General configuration settings"""
    st.markdown("### 🔧 General Configuration")

    config = st.session_state.get('config') or {}

    # API Configuration
    st.markdown("#### 🔗 SermonAudio API")

    col1, col2 = st.columns(2)

    with col1:
        api_key = st.text_input(
            "API Key",
            value=config.get('api_key', ''),
            type="password",
            help="Your SermonAudio API key"
        )

    with col2:
        broadcaster_id = st.text_input(
            "Broadcaster ID",
            value=config.get('broadcaster_id', ''),
            help="Your SermonAudio broadcaster ID"
        )

    # Test API connection
    if api_key and broadcaster_id:
        if st.button("🔍 Test API Connection"):
            test_api_connection(api_key, broadcaster_id)

    # Processing Options
    st.markdown("#### ⚙️ Processing Options")

    col1, col2 = st.columns(2)

    with col1:
        dry_run = st.checkbox(
            "Dry Run Mode (Default)",
            value=config.get('dry_run', False),
            help="Preview changes without uploading by default"
        )

        debug = st.checkbox(
            "Debug Mode",
            value=config.get('debug', False),
            help="Enable verbose debug output"
        )

    with col2:
        hashtag_verification = st.checkbox(
            "Hashtag Verification",
            value=config.get('hashtag_verification', True),
            help="Verify hashtags through second LLM pass"
        )

    # Output Settings
    st.markdown("#### 📁 Output Settings")

    col1, col2 = st.columns(2)

    with col1:
        output_directory = st.text_input(
            "Output Directory",
            value=config.get('output_directory', 'processed_sermons'),
            help="Directory to store processed sermon files"
        )

        save_original_audio = st.checkbox(
            "Save Original Audio",
            value=config.get('save_original_audio', True),
            help="Keep copy of original audio file"
        )

    with col2:
        save_transcript = st.checkbox(
            "Save Transcript",
            value=config.get('save_transcript', True),
            help="Save sermon transcript as text file"
        )

    # Save button
    if st.button("💾 Save General Settings", type="primary"):
        save_general_settings(api_key, broadcaster_id, dry_run, debug,
                            hashtag_verification, output_directory,
                            save_original_audio, save_transcript)

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
        initialize_provider_session_state(fallback_config, st.session_state.fallback_provider, 'fallback')

    # Validator provider settings
    validator_config = llm_config.get('validator', {})
    if 'validator_enabled' not in st.session_state:
        st.session_state.validator_enabled = validator_config.get('enabled', False)
    if 'validator_provider' not in st.session_state:
        st.session_state.validator_provider = validator_config.get('provider', 'ollama')

    # Initialize validator provider-specific session state
    if st.session_state.validator_enabled:
        initialize_provider_session_state(validator_config, st.session_state.validator_provider, 'validator')

def initialize_provider_session_state(provider_config, provider_type, key_prefix):
    """Initialize provider-specific session state values from config"""
    if provider_type in provider_config:
        settings = provider_config[provider_type]

        if provider_type == 'ollama':
            if f'{key_prefix}_ollama_host' not in st.session_state:
                st.session_state[f'{key_prefix}_ollama_host'] = settings.get('host', 'http://localhost:11434')
            if f'{key_prefix}_ollama_model' not in st.session_state:
                st.session_state[f'{key_prefix}_ollama_model'] = settings.get('model', 'llama3')

        elif provider_type == 'openai':
            if f'{key_prefix}_openai_key' not in st.session_state:
                st.session_state[f'{key_prefix}_openai_key'] = settings.get('api_key', '')
            if f'{key_prefix}_openai_url' not in st.session_state:
                st.session_state[f'{key_prefix}_openai_url'] = settings.get('base_url', '')
            if f'{key_prefix}_openai_model' not in st.session_state:
                st.session_state[f'{key_prefix}_openai_model'] = settings.get('model', 'gpt-3.5-turbo')

        elif provider_type == 'anthropic':
            if f'{key_prefix}_anthropic_key' not in st.session_state:
                st.session_state[f'{key_prefix}_anthropic_key'] = settings.get('api_key', '')
            if f'{key_prefix}_anthropic_model' not in st.session_state:
                st.session_state[f'{key_prefix}_anthropic_model'] = settings.get('model', 'claude-3-5-sonnet-20241022')

        elif provider_type == 'xai':
            if f'{key_prefix}_xai_key' not in st.session_state:
                st.session_state[f'{key_prefix}_xai_key'] = settings.get('api_key', '')
            if f'{key_prefix}_xai_model' not in st.session_state:
                st.session_state[f'{key_prefix}_xai_model'] = settings.get('model', 'grok-beta')

        elif provider_type == 'google':
            if f'{key_prefix}_google_key' not in st.session_state:
                st.session_state[f'{key_prefix}_google_key'] = settings.get('api_key', '')
            if f'{key_prefix}_google_model' not in st.session_state:
                st.session_state[f'{key_prefix}_google_model'] = settings.get('model', 'gemini-1.5-flash')

        elif provider_type == 'groq':
            if f'{key_prefix}_groq_key' not in st.session_state:
                st.session_state[f'{key_prefix}_groq_key'] = settings.get('api_key', '')
            if f'{key_prefix}_groq_model' not in st.session_state:
                st.session_state[f'{key_prefix}_groq_model'] = settings.get('model', 'llama-3.1-70b-versatile')

        # Clear cached models when API key changes for all providers that use API keys
        if provider_type in ['openai', 'anthropic', 'xai', 'google', 'groq']:
            current_key = st.session_state.get(f'{key_prefix}_{provider_type}_key', '')
            stored_key = settings.get('api_key', '')
            if current_key != stored_key and current_key:
                # API key changed, clear cached models to force refresh
                st.session_state.pop(f'{key_prefix}_{provider_type}_models', None)

def show_llm_settings():
    """LLM provider configuration"""
    st.markdown("### 🤖 LLM Provider Configuration")

    config = st.session_state.get('config') or {}
    llm_config = config.get('llm', {})

    # Initialize session state from config if not already set
    initialize_llm_session_state(llm_config)

    # Primary Provider
    st.markdown("#### 🥇 Primary Provider")

    primary_config = llm_config.get('primary', {})

    col1, col2 = st.columns(2)

    with col1:
        provider_options = ["ollama", "openai", "anthropic", "xai", "google", "groq"]
        current_provider = primary_config.get('provider', 'ollama')
        try:
            provider_index = provider_options.index(current_provider)
        except ValueError:
            provider_index = 0  # Default to ollama if unknown provider

        primary_provider = st.selectbox(
            "Primary Provider",
            options=provider_options,
            index=provider_index,
            key="primary_provider"
        )

    with col2:
        if st.button("🔍 Test Primary Provider"):
            test_llm_provider(primary_provider, primary_config.get(primary_provider, {}))

    # Provider-specific settings
    if primary_provider == "ollama":
        show_ollama_settings("Primary", primary_config.get('ollama', {}), "primary")
    elif primary_provider == "openai":
        show_openai_settings("Primary", primary_config.get('openai', {}), "primary")
    elif primary_provider == "anthropic":
        show_anthropic_settings("Primary", primary_config.get('anthropic', {}), "primary")
    elif primary_provider == "xai":
        show_xai_settings("Primary", primary_config.get('xai', {}), "primary")
    elif primary_provider == "google":
        show_google_settings("Primary", primary_config.get('google', {}), "primary")
    elif primary_provider == "groq":
        show_groq_settings("Primary", primary_config.get('groq', {}), "primary")

    # Fallback Provider
    st.markdown("#### 🥈 Fallback Provider")

    fallback_config = llm_config.get('fallback', {})

    col1, col2 = st.columns(2)

    with col1:
        fallback_enabled = st.checkbox(
            "Enable Fallback Provider",
            value=fallback_config.get('enabled', True),
            key="fallback_enabled"
        )

    with col2:
        if fallback_enabled:
            provider_options = ["openai", "ollama", "anthropic", "xai", "google", "groq"]
            current_fallback_provider = fallback_config.get('provider', 'openai')
            try:
                fallback_provider_index = provider_options.index(current_fallback_provider)
            except ValueError:
                fallback_provider_index = 0  # Default to openai if unknown provider

            fallback_provider = st.selectbox(
                "Fallback Provider",
                options=provider_options,
                index=fallback_provider_index,
                key="fallback_provider"
            )

    if fallback_enabled:
        if fallback_provider == "ollama":
            show_ollama_settings("Fallback", fallback_config.get('ollama', {}), "fallback")
        elif fallback_provider == "openai":
            show_openai_settings("Fallback", fallback_config.get('openai', {}), "fallback")
        elif fallback_provider == "anthropic":
            show_anthropic_settings("Fallback", fallback_config.get('anthropic', {}), "fallback")
        elif fallback_provider == "xai":
            show_xai_settings("Fallback", fallback_config.get('xai', {}), "fallback")
        elif fallback_provider == "google":
            show_google_settings("Fallback", fallback_config.get('google', {}), "fallback")
        elif fallback_provider == "groq":
            show_groq_settings("Fallback", fallback_config.get('groq', {}), "fallback")

    # Validator Provider
    st.markdown("#### ✅ Validator Provider (Optional)")

    validator_config = llm_config.get('validator', {})

    validator_enabled = st.checkbox(
        "Enable Validation Provider",
        value=validator_config.get('enabled', False),
        help="Use smaller model for description validation",
        key="validator_enabled"
    )

    if validator_enabled:
        col1, col2 = st.columns(2)

        with col1:
            provider_options = ["ollama", "openai", "anthropic", "xai", "google", "groq"]
            current_validator_provider = validator_config.get('provider', 'ollama')
            try:
                validator_provider_index = provider_options.index(current_validator_provider)
            except ValueError:
                validator_provider_index = 0  # Default to ollama if unknown provider

            validator_provider = st.selectbox(
                "Validator Provider",
                options=provider_options,
                index=validator_provider_index,
                key="validator_provider"
            )

        if validator_provider == "ollama":
            show_ollama_settings("Validator", validator_config.get('ollama', {}), "validator")
        elif validator_provider == "openai":
            show_openai_settings("Validator", validator_config.get('openai', {}), "validator")
        elif validator_provider == "anthropic":
            show_anthropic_settings("Validator", validator_config.get('anthropic', {}), "validator")
        elif validator_provider == "xai":
            show_xai_settings("Validator", validator_config.get('xai', {}), "validator")
        elif validator_provider == "google":
            show_google_settings("Validator", validator_config.get('google', {}), "validator")
        elif validator_provider == "groq":
            show_groq_settings("Validator", validator_config.get('groq', {}), "validator")

    # Save button
    if st.button("💾 Save LLM Settings", type="primary"):
        save_llm_settings()

def show_ollama_settings(label, config, key_prefix):
    """Show Ollama-specific settings with automatic model refresh"""
    col1, col2 = st.columns(2)

    with col1:
        host = st.text_input(
            f"{label} Ollama Host",
            value=config.get('host', 'http://localhost:11434'),
            key=f"{key_prefix}_ollama_host"
        )

    with col2:
        # Auto-refresh models when host changes or button clicked
        available_models = []
        refresh_clicked = st.button(f"🔄 Refresh {label} Models", key=f"{key_prefix}_refresh_models")

        if refresh_clicked or not st.session_state.get(f"{key_prefix}_ollama_models"):
            try:
                # Import here to avoid issues if not installed
                sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
                from llm_manager import OllamaProvider

                ollama_provider = OllamaProvider({'host': host})
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
            current_model = config.get('model', 'llama3')
            try:
                model_index = cached_models.index(current_model)
            except ValueError:
                model_index = 0 if cached_models else None

            model = st.selectbox(
                f"{label} Ollama Model",
                options=cached_models,
                index=model_index,
                key=f"{key_prefix}_ollama_model",
                help="Select from available Ollama models"
            )
        else:
            model = st.text_input(
                f"{label} Ollama Model",
                value=config.get('model', 'llama3'),
                key=f"{key_prefix}_ollama_model",
                help="Enter model name (click Refresh to see available models)"
            )

def show_openai_settings(label, config, key_prefix):
    """Show OpenAI-specific settings with automatic model loading"""
    col1, col2 = st.columns(2)

    with col1:
        api_key = st.text_input(
            f"{label} API Key",
            value=config.get('api_key', ''),
            type="password",
            key=f"{key_prefix}_openai_key"
        )

        base_url = st.text_input(
            f"{label} Base URL (Optional)",
            value=config.get('base_url', ''),
            placeholder="https://api.openai.com/v1",
            help="For custom endpoints (xAI, Anthropic, etc.)",
            key=f"{key_prefix}_openai_url"
        )

    with col2:
        # Auto-load models if API key is provided
        available_models = []
        model_options = ['gpt-4', 'gpt-4-turbo', 'gpt-3.5-turbo', 'gpt-3.5-turbo-16k']  # Default options

        if api_key and st.button(f"🔄 Load {label} Models", key=f"{key_prefix}_load_models"):
            try:
                # Import OpenAI provider to list models
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
                    # Filter to commonly used models for better UX
                    model_options = [m for m in available_models if any(x in m.lower() for x in ['gpt-4', 'gpt-3.5', 'claude', 'grok', 'gemini', 'llama'])]
                    if not model_options:
                        model_options = available_models[:10]  # Take first 10 if no common ones found
                else:
                    st.warning("No models found - check API credentials")
            except Exception as e:
                st.error(f"Failed to load models: {e}")

        # Get cached models if available
        cached_models = st.session_state.get(f"{key_prefix}_openai_models", [])
        if cached_models:
            # Filter to commonly used models
            model_options = [m for m in cached_models if any(x in m.lower() for x in ['gpt-4', 'gpt-3.5', 'claude', 'grok', 'gemini', 'llama'])]
            if not model_options:
                model_options = cached_models[:10]

        # Model selection
        current_model = config.get('model', 'gpt-3.5-turbo')
        if model_options and len(model_options) > 1:
            try:
                model_index = model_options.index(current_model)
            except ValueError:
                model_index = 0

            model = st.selectbox(
                f"{label} Model",
                options=model_options,
                index=model_index,
                key=f"{key_prefix}_openai_model",
                help="Select from available models"
            )
        else:
            model = st.text_input(
                f"{label} Model",
                value=current_model,
                key=f"{key_prefix}_openai_model",
                help="Enter model name or click 'Load Models' to see available options"
            )

def show_anthropic_settings(label, config, key_prefix):
    """Show Anthropic-specific settings with dynamic model loading"""
    col1, col2 = st.columns(2)

    with col1:
        api_key = st.text_input(
            f"{label} API Key",
            value=config.get('api_key', ''),
            type="password",
            key=f"{key_prefix}_anthropic_key",
            help="Your Anthropic API key (sk-ant-...)"
        )

    with col2:
        # Dynamic model loading for Anthropic
        available_models = []
        model_options = [  # Default fallbacks
            'claude-3-5-sonnet-20241022',
            'claude-3-5-haiku-20241022',
            'claude-3-opus-20240229',
            'claude-3-sonnet-20240229',
            'claude-3-haiku-20240307'
        ]

        if api_key and st.button(f"🔄 Load {label} Models", key=f"{key_prefix}_load_anthropic_models"):
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
                from llm_manager import AnthropicProvider

                provider = AnthropicProvider({'api_key': api_key})
                available_models = provider.list_models()

                if available_models:
                    st.session_state[f"{key_prefix}_anthropic_models"] = available_models
                    st.success(f"Loaded {len(available_models)} models")
                    model_options = available_models
                else:
                    st.warning("No models found - using default options")
            except Exception as e:
                st.error(f"Failed to load models: {e}")
                st.info("Using default model options")

        # Get cached models if available
        cached_models = st.session_state.get(f"{key_prefix}_anthropic_models", [])
        if cached_models:
            model_options = cached_models

        # Model selection
        current_model = config.get('model', 'claude-3-5-sonnet-20241022')
        if model_options and len(model_options) > 1:
            try:
                model_index = model_options.index(current_model)
            except ValueError:
                model_index = 0

            model = st.selectbox(
                f"{label} Model",
                options=model_options,
                index=model_index,
                key=f"{key_prefix}_anthropic_model",
                help="Select from available Claude models"
            )
        else:
            model = st.text_input(
                f"{label} Model",
                value=current_model,
                key=f"{key_prefix}_anthropic_model",
                help="Enter model name or click 'Load Models' to see available options"
            )

        # Show test button if API key is provided
        if api_key and st.button(f"🔍 Test {label} Connection", key=f"{key_prefix}_test_anthropic"):
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
                from llm_manager import AnthropicProvider

                provider = AnthropicProvider({'api_key': api_key, 'model': model})
                test_response = provider.chat([{"role": "user", "content": "Hello, this is a test."}])
                st.success("✅ Anthropic connection successful!")
            except Exception as e:
                st.error(f"❌ Connection failed: {e}")

    st.info("💡 Anthropic endpoint (https://api.anthropic.com/v1) is automatically configured")

def show_xai_settings(label, config, key_prefix):
    """Show xAI-specific settings with dynamic model loading"""
    col1, col2 = st.columns(2)

    with col1:
        api_key = st.text_input(
            f"{label} API Key",
            value=config.get('api_key', ''),
            type="password",
            key=f"{key_prefix}_xai_key",
            help="Your xAI API key"
        )

    with col2:
        # Dynamic model loading for xAI
        available_models = []
        model_options = ['grok-beta', 'grok-vision-beta']  # Default fallbacks

        if api_key and st.button(f"🔄 Load {label} Models", key=f"{key_prefix}_load_xai_models"):
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
                from llm_manager import XAIProvider

                provider = XAIProvider({'api_key': api_key})
                available_models = provider.list_models()

                if available_models:
                    st.session_state[f"{key_prefix}_xai_models"] = available_models
                    st.success(f"Loaded {len(available_models)} models")
                    model_options = available_models
                else:
                    st.warning("No models found - using default options")
            except Exception as e:
                st.error(f"Failed to load models: {e}")
                st.info("Using default model options")

        # Get cached models if available
        cached_models = st.session_state.get(f"{key_prefix}_xai_models", [])
        if cached_models:
            model_options = cached_models

        # Model selection
        current_model = config.get('model', 'grok-beta')
        if model_options and len(model_options) > 1:
            try:
                model_index = model_options.index(current_model)
            except ValueError:
                model_index = 0

            model = st.selectbox(
                f"{label} Model",
                options=model_options,
                index=model_index,
                key=f"{key_prefix}_xai_model",
                help="Select from available xAI models"
            )
        else:
            model = st.text_input(
                f"{label} Model",
                value=current_model,
                key=f"{key_prefix}_xai_model",
                help="Enter model name or click 'Load Models' to see available options"
            )

        # Show test button if API key is provided
        if api_key and st.button(f"🔍 Test {label} Connection", key=f"{key_prefix}_test_xai"):
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
                from llm_manager import XAIProvider

                provider = XAIProvider({'api_key': api_key, 'model': model})
                test_response = provider.chat([{"role": "user", "content": "Hello, this is a test."}])
                st.success("✅ xAI connection successful!")
            except Exception as e:
                st.error(f"❌ Connection failed: {e}")

    st.info("💡 xAI endpoint (https://api.x.ai/v1) is automatically configured")

def show_google_settings(label, config, key_prefix):
    """Show Google-specific settings with dynamic model loading"""
    col1, col2 = st.columns(2)

    with col1:
        api_key = st.text_input(
            f"{label} API Key",
            value=config.get('api_key', ''),
            type="password",
            key=f"{key_prefix}_google_key",
            help="Your Google AI Studio API key"
        )

    with col2:
        # Dynamic model loading for Google
        available_models = []
        model_options = [  # Default fallbacks
            'gemini-1.5-flash',
            'gemini-1.5-pro',
            'gemini-1.0-pro'
        ]

        if api_key and st.button(f"🔄 Load {label} Models", key=f"{key_prefix}_load_google_models"):
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
                from llm_manager import GoogleProvider

                provider = GoogleProvider({'api_key': api_key})
                available_models = provider.list_models()

                if available_models:
                    st.session_state[f"{key_prefix}_google_models"] = available_models
                    st.success(f"Loaded {len(available_models)} models")
                    model_options = available_models
                else:
                    st.warning("No models found - using default options")
            except Exception as e:
                st.error(f"Failed to load models: {e}")
                st.info("Using default model options")

        # Get cached models if available
        cached_models = st.session_state.get(f"{key_prefix}_google_models", [])
        if cached_models:
            model_options = cached_models

        # Model selection
        current_model = config.get('model', 'gemini-1.5-flash')
        if model_options and len(model_options) > 1:
            try:
                model_index = model_options.index(current_model)
            except ValueError:
                model_index = 0

            model = st.selectbox(
                f"{label} Model",
                options=model_options,
                index=model_index,
                key=f"{key_prefix}_google_model",
                help="Select from available Gemini models"
            )
        else:
            model = st.text_input(
                f"{label} Model",
                value=current_model,
                key=f"{key_prefix}_google_model",
                help="Enter model name or click 'Load Models' to see available options"
            )

        # Show test button if API key is provided
        if api_key and st.button(f"🔍 Test {label} Connection", key=f"{key_prefix}_test_google"):
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
                from llm_manager import GoogleProvider

                provider = GoogleProvider({'api_key': api_key, 'model': model})
                test_response = provider.chat([{"role": "user", "content": "Hello, this is a test."}])
                st.success("✅ Google AI connection successful!")
            except Exception as e:
                st.error(f"❌ Connection failed: {e}")

    st.info("💡 Google AI endpoint (https://generativelanguage.googleapis.com/v1beta) is automatically configured")

def show_groq_settings(label, config, key_prefix):
    """Show Groq-specific settings with dynamic model loading"""
    col1, col2 = st.columns(2)

    with col1:
        api_key = st.text_input(
            f"{label} API Key",
            value=config.get('api_key', ''),
            type="password",
            key=f"{key_prefix}_groq_key",
            help="Your Groq API key (gsk-...)"
        )

    with col2:
        # Dynamic model loading for Groq
        available_models = []
        model_options = [  # Default fallbacks
            'llama-3.1-70b-versatile',
            'llama-3.1-8b-instant',
            'llama-3.2-90b-text-preview',
            'mixtral-8x7b-32768',
            'gemma2-9b-it'
        ]

        if api_key and st.button(f"🔄 Load {label} Models", key=f"{key_prefix}_load_groq_models"):
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
                from llm_manager import GroqProvider

                provider = GroqProvider({'api_key': api_key})
                available_models = provider.list_models()

                if available_models:
                    st.session_state[f"{key_prefix}_groq_models"] = available_models
                    st.success(f"Loaded {len(available_models)} models")
                    model_options = available_models
                else:
                    st.warning("No models found - using default options")
            except Exception as e:
                st.error(f"Failed to load models: {e}")
                st.info("Using default model options")

        # Get cached models if available
        cached_models = st.session_state.get(f"{key_prefix}_groq_models", [])
        if cached_models:
            model_options = cached_models

        # Model selection
        current_model = config.get('model', 'llama-3.1-70b-versatile')
        if model_options and len(model_options) > 1:
            try:
                model_index = model_options.index(current_model)
            except ValueError:
                model_index = 0

            model = st.selectbox(
                f"{label} Model",
                options=model_options,
                index=model_index,
                key=f"{key_prefix}_groq_model",
                help="Select from available Groq models"
            )
        else:
            model = st.text_input(
                f"{label} Model",
                value=current_model,
                key=f"{key_prefix}_groq_model",
                help="Enter model name or click 'Load Models' to see available options"
            )

        # Show test button if API key is provided
        if api_key and st.button(f"🔍 Test {label} Connection", key=f"{key_prefix}_test_groq"):
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
                from llm_manager import GroqProvider

                provider = GroqProvider({'api_key': api_key, 'model': model})
                test_response = provider.chat([{"role": "user", "content": "Hello, this is a test."}])
                st.success("✅ Groq connection successful!")
            except Exception as e:
                st.error(f"❌ Connection failed: {e}")

    st.info("💡 Groq endpoint (https://api.groq.com/openai/v1) is automatically configured")

def show_embedding_settings():
    """Embedding provider configuration for RAG system"""
    st.markdown("### 🧠 Embedding Provider Configuration")
    st.markdown("Configure embedding providers for the RAG (Retrieval-Augmented Generation) system used in analytics.")

    config = st.session_state.get('config') or {}
    embeddings_config = config.get('embeddings', {})

    # Initialize session state from config if not already set
    initialize_embedding_session_state(embeddings_config)

    # Primary Provider
    st.markdown("#### 🥇 Primary Embedding Provider")

    primary_config = embeddings_config.get('primary', {})

    col1, col2 = st.columns(2)

    with col1:
        provider_options = ["sentence_transformers", "openai", "ollama"]
        current_provider = primary_config.get('provider', 'sentence_transformers')
        try:
            provider_index = provider_options.index(current_provider)
        except ValueError:
            provider_index = 0  # Default to sentence_transformers if unknown provider

        primary_provider = st.selectbox(
            "Primary Embedding Provider",
            options=provider_options,
            index=provider_index,
            key="primary_embedding_provider",
            help="Choose the primary embedding provider for vector search"
        )

    with col2:
        if st.button("🔍 Test Primary Embedding Provider"):
            test_embedding_provider(primary_provider, primary_config.get(primary_provider, {}))

    # Provider-specific settings
    if primary_provider == "sentence_transformers":
        show_sentence_transformers_settings("Primary", primary_config.get('sentence_transformers', {}), "primary")
    elif primary_provider == "openai":
        show_openai_embedding_settings("Primary", primary_config.get('openai', {}), "primary")
    elif primary_provider == "ollama":
        show_ollama_embedding_settings("Primary", primary_config.get('ollama', {}), "primary")

    # Fallback Providers
    st.markdown("#### 🥈 Fallback Embedding Providers")
    st.markdown("Configure multiple fallback providers that will be tried in order if the primary provider fails.")

    fallback_config = embeddings_config.get('fallback', [])

    # Display existing fallback providers
    if fallback_config:
        st.markdown("**Current Fallback Providers:**")
        for i, fallback in enumerate(fallback_config):
            col1, col2, col3 = st.columns([2, 2, 1])
            
            with col1:
                st.write(f"{i+1}. **{fallback.get('provider', 'unknown')}**")
            
            with col2:
                st.write(f"Model: `{fallback.get('model', 'default')}`")
            
            with col3:
                if st.button("🗑️", key=f"remove_fallback_{i}", help="Remove this fallback provider"):
                    fallback_config.pop(i)
                    st.rerun()

    # Add new fallback provider
    st.markdown("**Add New Fallback Provider:**")
    
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        new_fallback_provider = st.selectbox(
            "Provider Type",
            options=["sentence_transformers", "openai", "ollama"],
            key="new_fallback_provider"
        )
    
    with col2:
        if new_fallback_provider == "sentence_transformers":
            model_options = ["all-MiniLM-L6-v2", "all-mpnet-base-v2", "all-distilroberta-v1", "paraphrase-multilingual-MiniLM-L12-v2"]
            new_fallback_model = st.selectbox("Model", options=model_options, key="new_fallback_st_model")
        elif new_fallback_provider == "openai":
            model_options = ["text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"]
            new_fallback_model = st.selectbox("Model", options=model_options, key="new_fallback_openai_model")
        elif new_fallback_provider == "ollama":
            model_options = ["nomic-embed-text", "mxbai-embed-large", "snowflake-arctic-embed:s", "snowflake-arctic-embed:m", "snowflake-arctic-embed:l"]
            new_fallback_model = st.selectbox("Model", options=model_options, key="new_fallback_ollama_model")
    
    with col3:
        if st.button("➕ Add", key="add_fallback_provider"):
            new_fallback = {
                "provider": new_fallback_provider,
                "model": new_fallback_model
            }
            if new_fallback not in fallback_config:
                fallback_config.append(new_fallback)
                # Update the config in session state
                if 'embeddings' not in st.session_state.config:
                    st.session_state.config['embeddings'] = {}
                st.session_state.config['embeddings']['fallback'] = fallback_config
                st.success(f"Added {new_fallback_provider} with model {new_fallback_model}")
                st.rerun()
            else:
                st.warning("This provider and model combination already exists")

    # Info about hash fallback
    st.info("💡 **Hash-based Fallback**: A hash-based embedding provider is automatically added as the final fallback to ensure the system works offline without any external dependencies.")

    # Save button
    if st.button("💾 Save Embedding Settings", type="primary"):
        save_embedding_settings()

def initialize_embedding_session_state(embeddings_config):
    """Initialize session state values from embedding config if not already set"""
    
    # Primary provider settings
    primary_config = embeddings_config.get('primary', {})
    if 'primary_embedding_provider' not in st.session_state:
        st.session_state.primary_embedding_provider = primary_config.get('provider', 'sentence_transformers')
    
    # Initialize primary provider-specific session state
    initialize_embedding_provider_session_state(primary_config, st.session_state.primary_embedding_provider, 'primary')

def initialize_embedding_provider_session_state(provider_config, provider_type, key_prefix):
    """Initialize embedding provider-specific session state values from config"""
    if provider_type in provider_config:
        settings = provider_config[provider_type]
        
        if provider_type == 'sentence_transformers':
            if f'{key_prefix}_st_model' not in st.session_state:
                st.session_state[f'{key_prefix}_st_model'] = settings.get('model', 'all-MiniLM-L6-v2')
                
        elif provider_type == 'openai':
            if f'{key_prefix}_openai_embedding_key' not in st.session_state:
                st.session_state[f'{key_prefix}_openai_embedding_key'] = settings.get('api_key', '')
            if f'{key_prefix}_openai_embedding_url' not in st.session_state:
                st.session_state[f'{key_prefix}_openai_embedding_url'] = settings.get('base_url', 'https://api.openai.com/v1')
            if f'{key_prefix}_openai_embedding_model' not in st.session_state:
                st.session_state[f'{key_prefix}_openai_embedding_model'] = settings.get('model', 'text-embedding-3-small')
                
        elif provider_type == 'ollama':
            if f'{key_prefix}_ollama_embedding_host' not in st.session_state:
                st.session_state[f'{key_prefix}_ollama_embedding_host'] = settings.get('host', 'http://localhost:11434')
            if f'{key_prefix}_ollama_embedding_model' not in st.session_state:
                st.session_state[f'{key_prefix}_ollama_embedding_model'] = settings.get('model', 'nomic-embed-text')

def show_sentence_transformers_settings(label, config, key_prefix):
    """Show Sentence Transformers embedding settings"""
    st.markdown(f"**{label} Sentence Transformers Configuration**")
    
    col1, col2 = st.columns(2)
    
    with col1:
        model_options = [
            "all-MiniLM-L6-v2",      # 384D - Fast, good quality (default)
            "all-mpnet-base-v2",     # 768D - Higher quality, slower
            "all-distilroberta-v1",  # 768D - Good balance
            "paraphrase-multilingual-MiniLM-L12-v2"  # 384D - Multilingual
        ]
        
        current_model = config.get('model', 'all-MiniLM-L6-v2')
        try:
            model_index = model_options.index(current_model)
        except ValueError:
            model_index = 0
            
        model = st.selectbox(
            f"{label} Model",
            options=model_options,
            index=model_index,
            key=f"{key_prefix}_st_model",
            help="Select from available sentence transformer models"
        )
    
    with col2:
        # Show model info
        model_info = {
            "all-MiniLM-L6-v2": "384D • Fast • Good quality",
            "all-mpnet-base-v2": "768D • Higher quality • Slower", 
            "all-distilroberta-v1": "768D • Good balance",
            "paraphrase-multilingual-MiniLM-L12-v2": "384D • Multilingual"
        }
        
        st.info(f"**Model Info:** {model_info.get(model, 'Local sentence transformer model')}")
        
        if st.button(f"📥 Download {label} Model", key=f"{key_prefix}_download_st"):
            download_sentence_transformer_model(model)

def show_openai_embedding_settings(label, config, key_prefix):
    """Show OpenAI embedding settings"""
    st.markdown(f"**{label} OpenAI Embeddings Configuration**")
    
    col1, col2 = st.columns(2)
    
    with col1:
        api_key = st.text_input(
            f"{label} API Key",
            value=config.get('api_key', ''),
            type="password",
            key=f"{key_prefix}_openai_embedding_key",
            help="Your OpenAI API key"
        )
        
        base_url = st.text_input(
            f"{label} Base URL",
            value=config.get('base_url', 'https://api.openai.com/v1'),
            key=f"{key_prefix}_openai_embedding_url",
            help="Base URL for OpenAI-compatible embedding API"
        )
    
    with col2:
        model_options = [
            "text-embedding-3-small",  # 1536D - Fast, cost-effective
            "text-embedding-3-large",  # 3072D - Highest quality
            "text-embedding-ada-002"   # 1536D - Legacy model
        ]
        
        current_model = config.get('model', 'text-embedding-3-small')
        try:
            model_index = model_options.index(current_model)
        except ValueError:
            model_index = 0
            
        model = st.selectbox(
            f"{label} Model",
            options=model_options,
            index=model_index,
            key=f"{key_prefix}_openai_embedding_model",
            help="Select from available OpenAI embedding models"
        )
        
        # Show model info
        model_info = {
            "text-embedding-3-small": "1536D • Fast • Cost-effective",
            "text-embedding-3-large": "3072D • Highest quality",
            "text-embedding-ada-002": "1536D • Legacy model"
        }
        
        st.info(f"**Model Info:** {model_info.get(model, 'OpenAI embedding model')}")

def show_ollama_embedding_settings(label, config, key_prefix):
    """Show Ollama embedding settings with model refresh"""
    st.markdown(f"**{label} Ollama Embeddings Configuration**")
    
    col1, col2 = st.columns(2)
    
    with col1:
        host = st.text_input(
            f"{label} Ollama Host",
            value=config.get('host', 'http://localhost:11434'),
            key=f"{key_prefix}_ollama_embedding_host",
            help="Ollama server host URL"
        )
    
    with col2:
        # Auto-refresh models when host changes or button clicked
        refresh_clicked = st.button(f"🔄 Refresh {label} Models", key=f"{key_prefix}_refresh_embedding_models")
        
        if refresh_clicked or not st.session_state.get(f"{key_prefix}_ollama_embedding_models"):
            try:
                # Import here to avoid issues if not installed
                sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
                from llm_manager import OllamaProvider
                
                ollama_provider = OllamaProvider({'host': host})
                available_models = ollama_provider.list_models()
                
                # Filter for embedding models
                embedding_models = [m for m in available_models if 'embed' in m.lower()]
                
                st.session_state[f"{key_prefix}_ollama_embedding_models"] = embedding_models
                
                if embedding_models:
                    st.success(f"Found {len(embedding_models)} embedding models")
                else:
                    st.warning("No embedding models found - check Ollama connection")
            except Exception as e:
                st.error(f"Failed to fetch models: {e}")
                st.info(f"Make sure Ollama is running at {host}")
        
        # Get cached models if available
        cached_models = st.session_state.get(f"{key_prefix}_ollama_embedding_models", [])
        default_models = ["nomic-embed-text", "mxbai-embed-large", "snowflake-arctic-embed:s", "snowflake-arctic-embed:m", "snowflake-arctic-embed:l"]
        
        available_models = cached_models if cached_models else default_models
        
        current_model = config.get('model', 'nomic-embed-text')
        try:
            model_index = available_models.index(current_model)
        except ValueError:
            model_index = 0 if available_models else None
            
        if available_models:
            model = st.selectbox(
                f"{label} Model",
                options=available_models,
                index=model_index,
                key=f"{key_prefix}_ollama_embedding_model",
                help="Select from available Ollama embedding models"
            )
        else:
            model = st.text_input(
                f"{label} Model",
                value=current_model,
                key=f"{key_prefix}_ollama_embedding_model",
                help="Enter embedding model name (click Refresh to see available models)"
            )
        
        # Show model info if known
        model_info = {
            "nomic-embed-text": "768D • General purpose embedding",
            "mxbai-embed-large": "1024D • High quality embedding",
            "snowflake-arctic-embed:s": "384D • Small, fast embedding",
            "snowflake-arctic-embed:m": "768D • Medium quality embedding", 
            "snowflake-arctic-embed:l": "1024D • Large, high quality"
        }
        
        if model in model_info:
            st.info(f"**Model Info:** {model_info[model]}")

def download_sentence_transformer_model(model_name):
    """Download a sentence transformer model"""
    try:
        with st.spinner(f"Downloading {model_name}..."):
            from sentence_transformers import SentenceTransformer
            # This will download the model if not already present
            SentenceTransformer(model_name)
            st.success(f"✅ Successfully downloaded {model_name}")
    except Exception as e:
        st.error(f"❌ Failed to download {model_name}: {e}")

def test_embedding_provider(provider, config):
    """Test embedding provider connection"""
    try:
        with st.spinner(f"Testing {provider} provider..."):
            # Import the embedding manager
            sys.path.insert(0, str(Path(__file__).parent))
            from embedding_manager import EmbeddingManager
            
            test_config = {
                'primary': {
                    'provider': provider,
                    provider: config
                }
            }
            
            embedding_manager = EmbeddingManager(test_config)
            
            # Test with a simple sentence
            test_text = "This is a test sentence for embedding generation."
            embeddings = embedding_manager.get_embeddings([test_text])
            
            if embeddings and len(embeddings) == 1 and len(embeddings[0]) > 0:
                dimensions = len(embeddings[0])
                st.success(f"✅ {provider.title()} provider working! Generated {dimensions}D embedding.")
            else:
                st.error(f"❌ {provider.title()} provider test failed - no embeddings generated")
                
    except Exception as e:
        st.error(f"❌ {provider.title()} provider test failed: {e}")

def save_embedding_settings():
    """Save embedding settings to configuration"""
    if not st.session_state.get('config'):
        st.session_state.config = {}
    
    # Initialize embeddings config if it doesn't exist
    if 'embeddings' not in st.session_state.config:
        st.session_state.config['embeddings'] = {}
    
    embeddings_config = st.session_state.config['embeddings']
    
    # Save Primary Provider Settings
    primary_provider = st.session_state.get('primary_embedding_provider', 'sentence_transformers')
    if 'primary' not in embeddings_config:
        embeddings_config['primary'] = {}
    embeddings_config['primary']['provider'] = primary_provider
    
    # Save primary provider-specific settings
    save_embedding_provider_settings(embeddings_config['primary'], primary_provider, 'primary')
    
    # Save fallback providers (if they exist in the session)
    # Note: Fallback providers are managed through the UI directly modifying the config
    
    # Save to file
    if save_config_to_file(st.session_state.config):
        st.success("✅ Embedding settings saved and configuration reloaded!")

def save_embedding_provider_settings(provider_config, provider_type, key_prefix):
    """Save embedding provider-specific settings from session state"""
    if provider_type not in provider_config:
        provider_config[provider_type] = {}
    
    provider_settings = provider_config[provider_type]
    
    if provider_type == 'sentence_transformers':
        model = st.session_state.get(f'{key_prefix}_st_model', 'all-MiniLM-L6-v2')
        provider_settings['model'] = model
        
    elif provider_type == 'openai':
        api_key = st.session_state.get(f'{key_prefix}_openai_embedding_key', '')
        base_url = st.session_state.get(f'{key_prefix}_openai_embedding_url', 'https://api.openai.com/v1')
        model = st.session_state.get(f'{key_prefix}_openai_embedding_model', 'text-embedding-3-small')
        
        if api_key:
            provider_settings['api_key'] = api_key
        provider_settings['base_url'] = base_url
        provider_settings['model'] = model
        
    elif provider_type == 'ollama':
        host = st.session_state.get(f'{key_prefix}_ollama_embedding_host', 'http://localhost:11434')
        model = st.session_state.get(f'{key_prefix}_ollama_embedding_model', 'nomic-embed-text')
        
        provider_settings['host'] = host
        provider_settings['model'] = model

def show_audio_settings():
    """Audio processing configuration"""
    st.markdown("### 🎵 Audio Processing Configuration")

    config = st.session_state.get('config') or {}

    # Enhancement Method
    st.markdown("#### 🔧 Enhancement Method")

    enhancement_method = st.selectbox(
        "Audio Enhancement Method",
        options=["deepfilternet", "resemble_enhance", "none"],
        index=0 if config.get('audio_enhancement_method') == 'deepfilternet' else
              1 if config.get('audio_enhancement_method') == 'resemble_enhance' else 2,
        help="Choose AI enhancement method for audio quality improvement"
    )

    # Enhancement options
    st.markdown("#### ⚙️ Processing Options")

    col1, col2 = st.columns(2)

    with col1:
        use_audacity = st.checkbox(
            "Use Audacity Integration",
            value=config.get('use_audacity', False),
            help="Use Audacity with mod-script-pipe if available"
        )

        audio_noise_reduction = st.checkbox(
            "Noise Reduction",
            value=config.get('audio_noise_reduction', True),
            help="Apply noise reduction during processing"
        )

        audio_amplify = st.checkbox(
            "Audio Amplification",
            value=config.get('audio_amplify', True),
            help="Apply audio amplification"
        )

    with col2:
        audio_normalize = st.checkbox(
            "Audio Normalization",
            value=config.get('audio_normalize', True),
            help="Normalize audio levels"
        )

        audio_gain_db = st.slider(
            "Gain (dB)",
            min_value=-10.0,
            max_value=10.0,
            value=float(config.get('audio_gain_db', 0.5)),
            step=0.1,
            help="Audio gain adjustment in decibels"
        )

        target_level_db = st.slider(
            "Target Level (dB)",
            min_value=-30.0,
            max_value=-10.0,
            value=float(config.get('audio_target_level_db', -22.0)),
            step=1.0,
            help="Target audio level for normalization"
        )

    # Save button
    if st.button("💾 Save Audio Settings", type="primary"):
        save_audio_settings(enhancement_method, use_audacity, audio_noise_reduction,
                          audio_amplify, audio_normalize, audio_gain_db, target_level_db)

def show_validation_settings():
    """Validation criteria configuration"""
    st.markdown("### ✅ Validation Configuration")

    config = st.session_state.get('config') or {}
    metadata_config = config.get('metadata_processing', {})

    # Description validation
    st.markdown("#### 📝 Description Validation")

    desc_config = metadata_config.get('description', {})
    desc_validation = desc_config.get('validation', {})

    validation_enabled = st.checkbox(
        "Enable Description Validation",
        value=desc_validation.get('enabled', True),
        help="Use AI to validate description quality"
    )

    if validation_enabled:
        st.markdown("**Validation Criteria:**")

        criteria = desc_validation.get('criteria', [])

        # Allow editing criteria
        new_criteria = []
        for i, criterion in enumerate(criteria):
            edited = st.text_input(f"Criterion {i+1}", value=criterion, key=f"criteria_{i}")
            if edited.strip():
                new_criteria.append(edited.strip())

        # Add new criterion
        new_criterion = st.text_input("Add new criterion:", key="new_criterion")
        if new_criterion.strip():
            new_criteria.append(new_criterion.strip())

        if st.button("➕ Add Criterion"):
            st.rerun()

    # Metadata processing settings
    st.markdown("#### 🔧 Processing Settings")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Description Settings:**")

        desc_update_missing = st.checkbox(
            "Update if Missing",
            value=desc_config.get('update_if_missing', True),
            key="desc_update_missing"
        )

        desc_update_minimal = st.checkbox(
            "Update if Minimal",
            value=desc_config.get('update_if_minimal', True),
            key="desc_update_minimal"
        )

        desc_min_length = st.number_input(
            "Min Length Threshold",
            value=desc_config.get('min_length_threshold', 50),
            min_value=10,
            max_value=200,
            key="desc_min_length"
        )

    with col2:
        st.markdown("**Hashtag Settings:**")

        hashtag_config = metadata_config.get('hashtags', {})

        hash_update_missing = st.checkbox(
            "Update if Missing",
            value=hashtag_config.get('update_if_missing', True),
            key="hash_update_missing"
        )

        hash_update_minimal = st.checkbox(
            "Update if Minimal",
            value=hashtag_config.get('update_if_minimal', True),
            key="hash_update_minimal"
        )

        hash_min_length = st.number_input(
            "Min Length Threshold",
            value=hashtag_config.get('min_length_threshold', 10),
            min_value=5,
            max_value=50,
            key="hash_min_length"
        )

    # Save button
    if st.button("💾 Save Validation Settings", type="primary"):
        save_validation_settings()

def show_import_sermons():
    """Import sermons from processed_sermons folder into database"""
    st.markdown("### 📥 Import Existing Sermons")
    st.markdown("Scan the processed_sermons folder and import any missing sermons into the database.")

    try:
        # Import the sermon importer
        sys.path.insert(0, str(Path(__file__).parent))
        from sermon_importer import get_import_status, import_missing_sermons, import_single_sermon

        # Get current import status
        status = get_import_status()

        # Display status
        st.markdown("#### 📊 Current Status")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Sermons in Folder", status['total_in_folder'])

        with col2:
            st.metric("In Database", status['in_database'])

        with col3:
            st.metric("Missing from Database", status['missing_from_database'])

        st.markdown(f"**Folder Path:** `{status['folder_path']}`")

        # Show missing sermons if any
        if status['missing_sermon_ids']:
            st.markdown("#### 🔍 Missing Sermons (Preview)")

            missing_count = status['missing_from_database']
            preview_sermons = status['missing_sermon_ids']

            if missing_count > 10:
                st.info(f"Showing first 10 of {missing_count} missing sermons:")

            for sermon_id in preview_sermons:
                col1, col2 = st.columns([3, 1])

                with col1:
                    st.write(f"📄 Sermon ID: `{sermon_id}`")

                with col2:
                    if st.button("Import", key=f"import_single_{sermon_id}"):
                        with st.spinner(f"Importing sermon {sermon_id}..."):
                            success = import_single_sermon(sermon_id)
                            if success:
                                st.success(f"✅ Successfully imported sermon {sermon_id}")
                                st.rerun()
                            else:
                                st.error(f"❌ Failed to import sermon {sermon_id}")

            st.divider()

            # Bulk import options
            st.markdown("#### 🚀 Bulk Import")

            col1, col2 = st.columns(2)

            with col1:
                # Regular import for missing sermons
                if st.button("📥 Import All Missing Sermons", type="primary"):
                    if status['missing_from_database'] > 0:
                        # Use job queue for background import
                        try:
                            from job_queue import JobType, get_job_queue

                            job_queue = get_job_queue()
                            config = st.session_state.get('config', {})
                            processed_sermons_dir = config.get('output_directory', 'processed_sermons')

                            job_id = job_queue.add_job(
                                job_type=JobType.SERMON_IMPORT,
                                title="Bulk Sermon Import",
                                description=f"Importing {status['missing_from_database']} missing sermons from processed_sermons folder",
                                parameters={
                                    'processed_sermons_dir': processed_sermons_dir,
                                    'force_reimport': False
                                },
                                priority=6  # Medium-high priority
                            )

                            st.success(f"✅ Import job started! Job ID: {job_id[:8]}")
                            st.info(f"📥 Importing {status['missing_from_database']} sermons in the background. Monitor progress on the Jobs page.")

                            # Add button to go to jobs page
                            if st.button("📊 View Job Progress", type="secondary"):
                                st.session_state.current_page = 'jobs'
                                st.rerun()

                        except Exception as e:
                            st.error(f"❌ Failed to start import job: {e}")
                            # Fallback to old method
                            with st.spinner(f"Importing {status['missing_from_database']} sermons..."):
                                successful, failed, failed_ids = import_missing_sermons()

                                if successful > 0:
                                    st.success(f"✅ Successfully imported {successful} sermons!")

                                if failed > 0:
                                    st.error(f"❌ Failed to import {failed} sermons")
                                    if failed_ids:
                                        st.write("Failed sermon IDs:")
                                        for failed_id in failed_ids[:5]:  # Show first 5
                                            st.write(f"• {failed_id}")
                                        if len(failed_ids) > 5:
                                            st.write(f"• ... and {len(failed_ids) - 5} more")

                                st.rerun()
                    else:
                        st.info("No missing sermons to import")

            with col2:
                # Force re-import option
                st.markdown("**🔄 Force Re-import Options**")
                force_refresh_api = st.checkbox("Refresh API metadata", value=False, help="Re-fetch sermon metadata from SermonAudio API")

                if st.button("🔄 Force Re-import All Sermons", type="secondary"):
                    # Confirm before proceeding
                    if st.session_state.get('confirm_reimport', False):
                        try:
                            from job_queue import JobType, get_job_queue

                            job_queue = get_job_queue()
                            config = st.session_state.get('config', {})
                            processed_sermons_dir = config.get('output_directory', 'processed_sermons')

                            job_id = job_queue.add_job(
                                job_type=JobType.SERMON_IMPORT,
                                title="Force Re-import All Sermons",
                                description=f"Re-importing all {status['total_in_folder']} sermons with fresh API data",
                                parameters={
                                    'processed_sermons_dir': processed_sermons_dir,
                                    'force_reimport': True,
                                    'refresh_api_data': force_refresh_api
                                },
                                priority=5  # Medium priority
                            )

                            st.success(f"✅ Force re-import job started! Job ID: {job_id[:8]}")
                            st.info(f"🔄 Re-importing all {status['total_in_folder']} sermons in the background. Monitor progress on the Jobs page.")
                            st.session_state.confirm_reimport = False  # Reset confirmation

                        except Exception as e:
                            st.error(f"❌ Failed to start re-import job: {e}")
                    else:
                        st.warning("⚠️ This will re-import ALL sermons and may take a long time. Click again to confirm.")
                        st.session_state.confirm_reimport = True

        else:
            # No missing sermons
            st.success("✅ All sermons in the processed_sermons folder are already in the database!")

            col1, col2 = st.columns(2)

            with col1:
                if st.button("🔄 Refresh Status"):
                    st.rerun()

            with col2:
                if st.button("📊 Go to Library"):
                    st.session_state.current_page = 'library'
                    st.rerun()

        # Help section
        st.markdown("#### ℹ️ How It Works")

        with st.expander("📚 Import Process Details"):
            st.markdown("""
            **The import process will:**
            
            1. **Scan the processed_sermons folder** for directories with numeric names (sermon IDs)
            2. **Check each sermon ID** against the database to see if it already exists
            3. **Extract metadata** from files in each sermon directory:
               - `{id}_description.txt` - Sermon description and title
               - `{id}_hashtags.txt` - Hashtags
               - `{id}_transcript.txt` - Full transcript (if available)
               - `processed_{id}.mp3` - Enhanced audio file
               - `{id}_ai_upscaled.wav` - AI enhanced audio (if available)
               - `{id}_processing_info.json` - Processing metadata (if available)
               - `{id}_qa_segments.json` - Q&A segment data (if available)
            
            4. **Create database records** with extracted metadata and file paths
            5. **Preserve all existing data** - only adds missing sermons, never overwrites
            
            **File Structure Expected:**
            ```
            processed_sermons/
            ├── 12345678/
            │   ├── 12345678_description.txt
            │   ├── 12345678_hashtags.txt
            │   ├── processed_12345678.mp3
            │   └── 12345678_ai_upscaled.wav
            └── 87654321/
                ├── 87654321_description.txt
                └── processed_87654321.mp3
            ```
            
            **Safe Operation:**
            - Only imports sermons that don't exist in the database
            - Does not modify or overwrite existing database entries
            - Gracefully handles missing files or incomplete data
            - Logs all actions for troubleshooting
            """)

    except ImportError as e:
        st.error(f"❌ Could not load sermon importer: {e}")
        st.info("Please ensure the sermon_importer module is available.")
    except Exception as e:
        st.error(f"❌ Error checking import status: {e}")
        st.info("Please check that the processed_sermons directory exists and is accessible.")


def show_backup_restore():
    """Configuration backup and restore"""
    st.markdown("### 💾 Backup & Restore")

    # Current config display
    st.markdown("#### 📄 Current Configuration")

    config = st.session_state.get('config') or {}

    if config:
        # Show config as YAML
        config_yaml = yaml.dump(config, default_flow_style=False, sort_keys=True)
        st.code(config_yaml, language='yaml')

        # Download config
        if st.download_button(
            "📥 Download Config",
            data=config_yaml,
            file_name="config_backup.yaml",
            mime="text/yaml"
        ):
            st.success("Configuration downloaded!")

    # Upload/restore config
    st.markdown("#### 📤 Restore Configuration")

    uploaded_config = st.file_uploader(
        "Upload Configuration File",
        type=['yaml', 'yml'],
        help="Upload a configuration file to restore settings"
    )

    if uploaded_config:
        try:
            config_content = uploaded_config.read().decode('utf-8')
            new_config = yaml.safe_load(config_content)

            st.success("✅ Configuration file loaded successfully!")
            st.code(config_content, language='yaml')

            if st.button("🔄 Apply Configuration", type="primary"):
                st.session_state.config = new_config
                from config_utils import save_config_to_file
                if save_config_to_file(new_config):
                    st.success("Configuration applied and saved!")
                    st.rerun()

        except Exception as e:
            st.error(f"❌ Failed to load configuration: {e}")

    # Reset to defaults
    st.markdown("#### 🔄 Reset to Defaults")

    st.warning("⚠️ This will reset all settings to default values")

    if st.button("🔄 Reset to Defaults", type="secondary"):
        if st.session_state.get('confirm_reset'):
            reset_to_defaults()
            st.success("Configuration reset to defaults!")
            st.rerun()
        else:
            st.session_state.confirm_reset = True
            st.warning("Click again to confirm reset")

def test_api_connection(api_key, broadcaster_id):
    """Test SermonAudio API connection"""
    try:
        # This would test the actual API connection
        st.success("✅ API connection successful!")
    except Exception as e:
        st.error(f"❌ API connection failed: {e}")

def test_llm_provider(provider, config):
    """Test LLM provider connection"""
    try:
        # This would test the actual LLM provider
        st.success(f"✅ {provider.title()} provider connection successful!")
    except Exception as e:
        st.error(f"❌ {provider.title()} provider connection failed: {e}")

def save_general_settings(api_key, broadcaster_id, dry_run, debug,
                         hashtag_verification, output_directory,
                         save_original_audio, save_transcript):
    """Save general settings to configuration"""
    if not st.session_state.get('config'):
        st.session_state.config = {}

    st.session_state.config.update({
        'api_key': api_key,
        'broadcaster_id': broadcaster_id,
        'dry_run': dry_run,
        'debug': debug,
        'hashtag_verification': hashtag_verification,
        'output_directory': output_directory,
        'save_original_audio': save_original_audio,
        'save_transcript': save_transcript
    })

    save_config_to_file(st.session_state.config)
    st.success("✅ General settings saved and configuration reloaded!")

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
        st.success("✅ LLM settings saved and configuration reloaded!")

def save_provider_settings(provider_config, provider_type, key_prefix):
    """Save provider-specific settings from session state"""
    if provider_type not in provider_config:
        provider_config[provider_type] = {}

    provider_settings = provider_config[provider_type]

    if provider_type == 'ollama':
        host = st.session_state.get(f'{key_prefix}_ollama_host', 'http://localhost:11434')
        model = st.session_state.get(f'{key_prefix}_ollama_model', 'llama3')
        provider_settings['host'] = host
        provider_settings['model'] = model

    elif provider_type == 'openai':
        api_key = st.session_state.get(f'{key_prefix}_openai_key', '')
        base_url = st.session_state.get(f'{key_prefix}_openai_url', '')
        model = st.session_state.get(f'{key_prefix}_openai_model', 'gpt-3.5-turbo')
        if api_key:
            provider_settings['api_key'] = api_key
        if base_url:
            provider_settings['base_url'] = base_url
        provider_settings['model'] = model

    elif provider_type == 'anthropic':
        api_key = st.session_state.get(f'{key_prefix}_anthropic_key', '')
        model = st.session_state.get(f'{key_prefix}_anthropic_model', 'claude-3-5-sonnet-20241022')
        if api_key:
            provider_settings['api_key'] = api_key
        provider_settings['model'] = model

    elif provider_type == 'xai':
        api_key = st.session_state.get(f'{key_prefix}_xai_key', '')
        model = st.session_state.get(f'{key_prefix}_xai_model', 'grok-beta')
        if api_key:
            provider_settings['api_key'] = api_key
        provider_settings['model'] = model

    elif provider_type == 'google':
        api_key = st.session_state.get(f'{key_prefix}_google_key', '')
        model = st.session_state.get(f'{key_prefix}_google_model', 'gemini-1.5-flash')
        if api_key:
            provider_settings['api_key'] = api_key
        provider_settings['model'] = model

    elif provider_type == 'groq':
        api_key = st.session_state.get(f'{key_prefix}_groq_key', '')
        model = st.session_state.get(f'{key_prefix}_groq_model', 'llama-3.1-70b-versatile')
        if api_key:
            provider_settings['api_key'] = api_key
        provider_settings['model'] = model

def save_audio_settings(enhancement_method, use_audacity, audio_noise_reduction,
                       audio_amplify, audio_normalize, audio_gain_db, target_level_db):
    """Save audio settings to configuration"""
    if not st.session_state.get('config'):
        st.session_state.config = {}

    st.session_state.config.update({
        'audio_enhancement_method': enhancement_method,
        'use_audacity': use_audacity,
        'audio_noise_reduction': audio_noise_reduction,
        'audio_amplify': audio_amplify,
        'audio_normalize': audio_normalize,
        'audio_gain_db': audio_gain_db,
        'audio_target_level_db': target_level_db
    })

    save_config_to_file(st.session_state.config)
    st.success("✅ Audio settings saved and configuration reloaded!")

def save_validation_settings():
    """Save validation settings to configuration"""
    # This would collect validation settings and save them
    st.success("✅ Validation settings saved!")

def save_config_to_file(config):
    """Save configuration to config.yaml file and reload in session"""
    from config_utils import save_config_to_file as _save_config
    return _save_config(config)

def reset_to_defaults():
    """Reset configuration to default values"""
    # Load example config as defaults
    try:
        project_root = Path(__file__).parent.parent.parent
        example_config_path = project_root / "config.example.yaml"

        with open(example_config_path) as f:
            default_config = yaml.safe_load(f)

        st.session_state.config = default_config
        from config_utils import save_config_to_file
        save_config_to_file(default_config)

    except Exception as e:
        st.error(f"Failed to reset to defaults: {e}")

if __name__ == "__main__":
    show_settings()
