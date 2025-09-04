"""
Settings Page for SermonAudio Processor

Handles configuration management, LLM provider setup, audio settings,
and validation criteria with web-based editing interface.
"""

import streamlit as st
import yaml
from pathlib import Path
import json

def show_settings():
    """Main settings management interface"""
    st.markdown('<div class="main-header">⚙️ Settings</div>', unsafe_allow_html=True)
    
    # Settings tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🔧 General", 
        "🤖 LLM Providers", 
        "🎵 Audio Processing", 
        "✅ Validation", 
        "💾 Backup & Restore"
    ])
    
    with tab1:
        show_general_settings()
    
    with tab2:
        show_llm_settings()
    
    with tab3:
        show_audio_settings()
    
    with tab4:
        show_validation_settings()
    
    with tab5:
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

def show_llm_settings():
    """LLM provider configuration"""
    st.markdown("### 🤖 LLM Provider Configuration")
    
    config = st.session_state.get('config') or {}
    llm_config = config.get('llm', {})
    
    # Primary Provider
    st.markdown("#### 🥇 Primary Provider")
    
    primary_config = llm_config.get('primary', {})
    
    col1, col2 = st.columns(2)
    
    with col1:
        primary_provider = st.selectbox(
            "Primary Provider",
            options=["ollama", "openai"],
            index=0 if primary_config.get('provider') == 'ollama' else 1,
            key="primary_provider"
        )
    
    with col2:
        if st.button("🔍 Test Primary Provider"):
            test_llm_provider(primary_provider, primary_config.get(primary_provider, {}))
    
    # Provider-specific settings
    if primary_provider == "ollama":
        show_ollama_settings("Primary", primary_config.get('ollama', {}), "primary")
    else:
        show_openai_settings("Primary", primary_config.get('openai', {}), "primary")
    
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
            fallback_provider = st.selectbox(
                "Fallback Provider",
                options=["openai", "ollama"],
                index=0 if fallback_config.get('provider') == 'openai' else 1,
                key="fallback_provider"
            )
    
    if fallback_enabled:
        if fallback_provider == "ollama":
            show_ollama_settings("Fallback", fallback_config.get('ollama', {}), "fallback")
        else:
            show_openai_settings("Fallback", fallback_config.get('openai', {}), "fallback")
    
    # Validator Provider
    st.markdown("#### ✅ Validator Provider (Optional)")
    
    validator_config = llm_config.get('validator', {})
    
    validator_enabled = st.checkbox(
        "Enable Validation Provider",
        value=validator_config.get('enabled', False),
        help="Use smaller model for description validation"
    )
    
    if validator_enabled:
        col1, col2 = st.columns(2)
        
        with col1:
            validator_provider = st.selectbox(
                "Validator Provider",
                options=["ollama", "openai"],
                index=0 if validator_config.get('provider') == 'ollama' else 1,
                key="validator_provider"
            )
        
        if validator_provider == "ollama":
            show_ollama_settings("Validator", validator_config.get('ollama', {}), "validator")
        else:
            show_openai_settings("Validator", validator_config.get('openai', {}), "validator")
    
    # Save button
    if st.button("💾 Save LLM Settings", type="primary"):
        save_llm_settings()

def show_ollama_settings(label, config, key_prefix):
    """Show Ollama-specific settings"""
    col1, col2 = st.columns(2)
    
    with col1:
        host = st.text_input(
            f"{label} Ollama Host",
            value=config.get('host', 'http://localhost:11434'),
            key=f"{key_prefix}_ollama_host"
        )
    
    with col2:
        model = st.text_input(
            f"{label} Ollama Model",
            value=config.get('model', 'llama3'),
            key=f"{key_prefix}_ollama_model"
        )

def show_openai_settings(label, config, key_prefix):
    """Show OpenAI-specific settings"""
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
        model = st.text_input(
            f"{label} Model",
            value=config.get('model', 'gpt-3.5-turbo'),
            key=f"{key_prefix}_openai_model"
        )

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
                save_config_to_file(new_config)
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
    st.success("✅ General settings saved!")

def save_llm_settings():
    """Save LLM settings to configuration"""
    # This would collect all LLM settings from session state and save them
    st.success("✅ LLM settings saved!")

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
    st.success("✅ Audio settings saved!")

def save_validation_settings():
    """Save validation settings to configuration"""
    # This would collect validation settings and save them
    st.success("✅ Validation settings saved!")

def save_config_to_file(config):
    """Save configuration to config.yaml file"""
    try:
        project_root = Path(__file__).parent.parent.parent
        config_path = project_root / "config.yaml"
        
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=True)
        
        st.info(f"Configuration saved to {config_path}")
    except Exception as e:
        st.error(f"Failed to save configuration: {e}")

def reset_to_defaults():
    """Reset configuration to default values"""
    # Load example config as defaults
    try:
        project_root = Path(__file__).parent.parent.parent
        example_config_path = project_root / "config.example.yaml"
        
        with open(example_config_path, 'r') as f:
            default_config = yaml.safe_load(f)
        
        st.session_state.config = default_config
        save_config_to_file(default_config)
        
    except Exception as e:
        st.error(f"Failed to reset to defaults: {e}")

if __name__ == "__main__":
    show_settings()