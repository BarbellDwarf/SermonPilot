# ui/components/processing_modes.py
import streamlit as st
from typing import Dict, Any, List, Optional
import json


class ProcessingModeSelector:
    """UI component for selecting and configuring audio processing modes."""
    
    def __init__(self):
        """Initialize the processing mode selector."""
        self.modes = {
            'standard': {
                'name': 'Standard Processing',
                'description': 'Balanced noise reduction and enhancement for typical recordings',
                'icon': '🎯',
                'settings': {
                    'noise_reduction_strength': 0.6,
                    'enable_amplification': True,
                    'amplification_boost_db': 3.0,
                    'enable_normalization': True,
                    'preserve_questions': False,
                    'question_detection': False,
                    'high_freq_boost_db': 0.0
                },
                'use_cases': ['Standard sermons', 'Single speaker presentations', 'Music with speech']
            },
            'question_friendly': {
                'name': 'Question-Friendly Processing',
                'description': 'Gentle processing that preserves Q&A segments and audience questions',
                'icon': '❓',
                'settings': {
                    'noise_reduction_strength': 0.3,
                    'enable_amplification': True,
                    'amplification_boost_db': 2.0,
                    'enable_normalization': True,
                    'preserve_questions': True,
                    'question_detection': True,
                    'question_amplification_db': 2.0,
                    'high_freq_boost_db': 1.0
                },
                'use_cases': ['Interactive lectures', 'Q&A sessions', 'Panel discussions']
            },
            'lecture_mode': {
                'name': 'Lecture Mode',
                'description': 'Optimized for clear speech with minimal interruptions',
                'icon': '🎓',
                'settings': {
                    'noise_reduction_strength': 0.7,
                    'enable_amplification': True,
                    'amplification_boost_db': 4.0,
                    'enable_normalization': True,
                    'preserve_questions': False,
                    'speech_enhancement': True,
                    'high_freq_boost_db': 2.0
                },
                'use_cases': ['Educational lectures', 'Training sessions', 'Webinars']
            },
            'gentle_enhancement': {
                'name': 'Gentle Enhancement',
                'description': 'Minimal processing for high-quality recordings',
                'icon': '🌿',
                'settings': {
                    'noise_reduction_strength': 0.2,
                    'enable_amplification': True,
                    'amplification_boost_db': 1.0,
                    'enable_normalization': True,
                    'preserve_questions': True,
                    'gentle_processing': True,
                    'high_freq_boost_db': 0.5
                },
                'use_cases': ['High-quality recordings', 'Professional productions', 'Studio recordings']
            },
            'aggressive_cleanup': {
                'name': 'Aggressive Cleanup',
                'description': 'Strong noise reduction for challenging recordings',
                'icon': '🔧',
                'settings': {
                    'noise_reduction_strength': 0.8,
                    'enable_amplification': True,
                    'amplification_boost_db': 5.0,
                    'enable_normalization': True,
                    'preserve_questions': False,
                    'speech_enhancement': True,
                    'high_freq_boost_db': 3.0
                },
                'use_cases': ['Noisy environments', 'Poor quality recordings', 'Background noise issues']
            },
            'custom': {
                'name': 'Custom Settings',
                'description': 'Manually configure all processing options',
                'icon': '⚙️',
                'settings': {},
                'use_cases': ['Specific requirements', 'Fine-tuned control', 'Experimental processing']
            }
        }

    def render_mode_selector(self) -> Dict[str, Any]:
        """
        Render processing mode selection UI.
        
        Returns:
            Dictionary containing selected mode and settings
        """
        st.subheader("🎛️ Audio Processing Mode")

        # Mode selection with visual cards
        selected_mode = self._render_mode_cards()
        
        if not selected_mode:
            return {}

        # Display mode information
        mode_info = self.modes[selected_mode]
        
        # Show mode description and use cases
        with st.expander(f"ℹ️ About {mode_info['name']}", expanded=False):
            st.write(mode_info['description'])
            if 'use_cases' in mode_info:
                st.write("**Best for:**")
                for use_case in mode_info['use_cases']:
                    st.write(f"• {use_case}")

        # Get mode settings
        if selected_mode == 'custom':
            settings = self._render_custom_settings()
        else:
            settings = self._render_preset_settings(selected_mode)

        # Processing preview
        self._render_processing_preview(selected_mode, settings)

        return {
            'mode': selected_mode,
            'mode_name': mode_info['name'],
            'settings': settings,
            'processing_config': self.get_processing_config(settings)
        }

    def _render_mode_cards(self) -> Optional[str]:
        """Render mode selection as visual cards."""
        # Create columns for mode cards
        modes_list = list(self.modes.keys())
        
        # Display in rows of 3
        selected_mode = None
        
        for i in range(0, len(modes_list), 3):
            cols = st.columns(3)
            row_modes = modes_list[i:i+3]
            
            for j, mode_key in enumerate(row_modes):
                mode = self.modes[mode_key]
                
                with cols[j]:
                    # Create a card-like button
                    if st.button(
                        f"{mode['icon']} {mode['name']}", 
                        key=f"mode_{mode_key}",
                        help=mode['description'],
                        use_container_width=True
                    ):
                        selected_mode = mode_key
                        st.session_state.selected_processing_mode = mode_key

        # Use session state to persist selection
        if 'selected_processing_mode' in st.session_state:
            return st.session_state.selected_processing_mode
        
        return selected_mode

    def _render_preset_settings(self, mode: str) -> Dict[str, Any]:
        """Render settings for a preset mode with optional fine-tuning."""
        mode_info = self.modes[mode]
        settings = mode_info['settings'].copy()

        st.subheader(f"⚙️ {mode_info['name']} Settings")
        
        # Show current settings
        with st.expander("Current Settings", expanded=False):
            self._display_settings_table(settings)

        # Fine-tuning options
        with st.expander("Fine-tune Settings", expanded=False):
            settings = self._render_fine_tuning_controls(settings)

        return settings

    def _render_custom_settings(self) -> Dict[str, Any]:
        """Render custom settings interface."""
        st.subheader("⚙️ Custom Processing Settings")

        settings = {}

        # Core processing settings
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Noise Reduction**")
            settings['noise_reduction_strength'] = st.slider(
                "Noise Reduction Strength",
                0.0, 1.0, 0.5,
                step=0.1,
                help="Higher values remove more noise but may affect speech quality"
            )
            
            st.markdown("**Amplification**")
            settings['enable_amplification'] = st.checkbox(
                "Enable Amplification",
                value=True,
                help="Automatically boost quiet sections"
            )
            
            if settings['enable_amplification']:
                settings['amplification_boost_db'] = st.slider(
                    "Amplification Boost (dB)",
                    0.0, 12.0, 3.0,
                    step=0.5,
                    help="Amount of amplification to apply"
                )

        with col2:
            st.markdown("**Normalization**")
            settings['enable_normalization'] = st.checkbox(
                "Enable Normalization",
                value=True,
                help="Balance audio levels across the recording"
            )
            
            if settings['enable_normalization']:
                settings['target_level_db'] = st.slider(
                    "Target Level (dB)",
                    -30.0, -6.0, -18.0,
                    step=1.0,
                    help="Target audio level after normalization"
                )

        # Question preservation settings
        st.markdown("**Question & Answer Handling**")
        settings['preserve_questions'] = st.checkbox(
            "Preserve Q&A Segments",
            value=False,
            help="Use gentle processing for question and answer sections"
        )

        if settings['preserve_questions']:
            col1, col2 = st.columns(2)
            with col1:
                settings['question_detection'] = st.checkbox(
                    "Auto-detect Questions",
                    value=True,
                    help="Automatically detect and preserve question segments"
                )
            with col2:
                settings['question_amplification_db'] = st.slider(
                    "Question Amplification (dB)",
                    0.0, 6.0, 2.0,
                    step=0.5,
                    help="Extra amplification for question segments"
                )

        # Advanced options
        with st.expander("Advanced Processing Options"):
            settings.update(self._render_advanced_options())

        return settings

    def _render_advanced_options(self) -> Dict[str, Any]:
        """Render advanced processing options."""
        advanced_settings = {}

        col1, col2 = st.columns(2)
        
        with col1:
            advanced_settings['speech_enhancement'] = st.checkbox(
                "AI Speech Enhancement",
                value=False,
                help="Apply AI-powered speech enhancement (slower processing)"
            )
            
            advanced_settings['gentle_processing'] = st.checkbox(
                "Gentle Processing Mode",
                value=False,
                help="Use less aggressive processing for sensitive content"
            )
            
            advanced_settings['preserve_dynamics'] = st.checkbox(
                "Preserve Dynamics",
                value=True,
                help="Maintain natural volume variations"
            )

        with col2:
            advanced_settings['high_freq_boost_db'] = st.slider(
                "High Frequency Boost (dB)",
                0.0, 6.0, 0.0,
                step=0.5,
                help="Boost high frequencies for better clarity"
            )
            
            advanced_settings['compression_ratio'] = st.slider(
                "Compression Ratio",
                1.0, 10.0, 3.0,
                step=0.5,
                help="Dynamic range compression ratio"
            )
            
            advanced_settings['gate_threshold_db'] = st.slider(
                "Noise Gate Threshold (dB)",
                -60.0, -20.0, -40.0,
                step=5.0,
                help="Threshold for noise gate (lower = more aggressive)"
            )

        return advanced_settings

    def _render_fine_tuning_controls(self, base_settings: Dict[str, Any]) -> Dict[str, Any]:
        """Render fine-tuning controls for preset modes."""
        settings = base_settings.copy()

        # Key parameters that users commonly want to adjust
        if st.checkbox("Adjust Noise Reduction", key="adjust_noise"):
            settings['noise_reduction_strength'] = st.slider(
                "Noise Reduction Strength",
                0.0, 1.0, base_settings.get('noise_reduction_strength', 0.5),
                step=0.1,
                key="fine_noise"
            )

        if st.checkbox("Adjust Amplification", key="adjust_amp"):
            settings['amplification_boost_db'] = st.slider(
                "Amplification Boost (dB)",
                0.0, 12.0, base_settings.get('amplification_boost_db', 3.0),
                step=0.5,
                key="fine_amp"
            )

        if base_settings.get('preserve_questions') and st.checkbox("Adjust Question Processing", key="adjust_q"):
            settings['question_amplification_db'] = st.slider(
                "Question Amplification (dB)",
                0.0, 6.0, base_settings.get('question_amplification_db', 2.0),
                step=0.5,
                key="fine_q_amp"
            )

        return settings

    def _display_settings_table(self, settings: Dict[str, Any]):
        """Display settings in a formatted table."""
        # Group settings by category
        categories = {
            'Noise Reduction': ['noise_reduction_strength'],
            'Amplification': ['enable_amplification', 'amplification_boost_db'],
            'Normalization': ['enable_normalization', 'target_level_db'],
            'Questions': ['preserve_questions', 'question_detection', 'question_amplification_db'],
            'Enhancement': ['speech_enhancement', 'high_freq_boost_db']
        }

        for category, keys in categories.items():
            category_settings = {k: v for k, v in settings.items() if k in keys}
            if category_settings:
                st.markdown(f"**{category}:**")
                for key, value in category_settings.items():
                    display_key = key.replace('_', ' ').title()
                    if isinstance(value, bool):
                        status = "✅ Enabled" if value else "❌ Disabled"
                        st.write(f"• {display_key}: {status}")
                    elif isinstance(value, (int, float)):
                        if 'db' in key.lower():
                            st.write(f"• {display_key}: {value} dB")
                        else:
                            st.write(f"• {display_key}: {value}")
                    else:
                        st.write(f"• {display_key}: {value}")

    def _render_processing_preview(self, mode: str, settings: Dict[str, Any]):
        """Render a preview of what processing will be applied."""
        st.subheader("🔍 Processing Preview")
        
        # Estimate processing intensity
        intensity = self._calculate_processing_intensity(settings)
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Processing intensity meter
            st.metric(
                "Processing Intensity",
                f"{intensity:.0%}",
                help="Estimated processing intensity (higher = more aggressive)"
            )
            
            # Estimated processing time
            processing_time = self._estimate_processing_time(settings)
            st.metric(
                "Est. Processing Time",
                f"{processing_time}x",
                help="Estimated processing time relative to audio length"
            )

        with col2:
            # Quality indicators
            quality_score = self._estimate_quality_impact(settings)
            st.metric(
                "Quality Preservation",
                f"{quality_score:.0%}",
                help="Estimated audio quality preservation"
            )
            
            # Compatibility
            compatibility = self._check_compatibility(settings)
            st.metric(
                "Feature Compatibility",
                f"{compatibility:.0%}",
                help="Percentage of features available on this system"
            )

        # Processing summary
        with st.expander("Processing Summary"):
            self._render_processing_summary(settings)

    def _calculate_processing_intensity(self, settings: Dict[str, Any]) -> float:
        """Calculate processing intensity score."""
        intensity = 0.0
        
        # Noise reduction contribution
        noise_strength = settings.get('noise_reduction_strength', 0.5)
        intensity += noise_strength * 0.3
        
        # Amplification contribution
        if settings.get('enable_amplification', False):
            amp_boost = settings.get('amplification_boost_db', 3.0)
            intensity += min(amp_boost / 12.0, 1.0) * 0.2
        
        # Enhancement features
        if settings.get('speech_enhancement', False):
            intensity += 0.3
        
        if settings.get('preserve_questions', False):
            intensity += 0.1
        
        # High frequency boost
        hf_boost = settings.get('high_freq_boost_db', 0.0)
        intensity += min(hf_boost / 6.0, 1.0) * 0.1
        
        return min(intensity, 1.0)

    def _estimate_processing_time(self, settings: Dict[str, Any]) -> float:
        """Estimate processing time multiplier."""
        base_time = 1.0
        
        if settings.get('speech_enhancement', False):
            base_time *= 3.0
        
        if settings.get('preserve_questions', False) and settings.get('question_detection', False):
            base_time *= 1.5
        
        noise_strength = settings.get('noise_reduction_strength', 0.5)
        base_time *= (1.0 + noise_strength * 0.5)
        
        return round(base_time, 1)

    def _estimate_quality_impact(self, settings: Dict[str, Any]) -> float:
        """Estimate quality preservation score."""
        quality = 1.0
        
        # Noise reduction impact
        noise_strength = settings.get('noise_reduction_strength', 0.5)
        quality -= noise_strength * 0.2
        
        # Gentle processing bonus
        if settings.get('gentle_processing', False):
            quality += 0.1
        
        # Question preservation bonus
        if settings.get('preserve_questions', False):
            quality += 0.05
        
        return max(min(quality, 1.0), 0.5) * 100

    def _check_compatibility(self, settings: Dict[str, Any]) -> float:
        """Check feature compatibility with current system."""
        total_features = 0
        available_features = 0
        
        # Check each feature
        features = [
            'noise_reduction_strength',
            'enable_amplification',
            'enable_normalization',
            'preserve_questions',
            'speech_enhancement',
            'high_freq_boost_db'
        ]
        
        for feature in features:
            total_features += 1
            if feature in settings:
                available_features += 1
        
        # AI features require additional dependencies
        if settings.get('speech_enhancement', False):
            try:
                import librosa
                available_features += 0  # Already counted
            except ImportError:
                available_features -= 0.5
        
        return (available_features / total_features) * 100 if total_features > 0 else 100

    def _render_processing_summary(self, settings: Dict[str, Any]):
        """Render a summary of processing steps."""
        steps = []
        
        # Noise reduction
        noise_strength = settings.get('noise_reduction_strength', 0.0)
        if noise_strength > 0:
            if noise_strength < 0.3:
                steps.append("• Light noise reduction")
            elif noise_strength < 0.6:
                steps.append("• Moderate noise reduction")
            else:
                steps.append("• Strong noise reduction")
        
        # Question processing
        if settings.get('preserve_questions', False):
            if settings.get('question_detection', False):
                steps.append("• Automatic question detection and preservation")
            else:
                steps.append("• Manual question segment preservation")
        
        # Amplification
        if settings.get('enable_amplification', False):
            boost = settings.get('amplification_boost_db', 0)
            steps.append(f"• Audio amplification ({boost} dB)")
        
        # Enhancement
        if settings.get('speech_enhancement', False):
            steps.append("• AI speech enhancement")
        
        # High frequency boost
        hf_boost = settings.get('high_freq_boost_db', 0.0)
        if hf_boost > 0:
            steps.append(f"• High frequency clarity boost ({hf_boost} dB)")
        
        # Normalization
        if settings.get('enable_normalization', False):
            steps.append("• Audio level normalization")
        
        if not steps:
            st.write("No processing selected - audio will be passed through unchanged.")
        else:
            st.write("Processing steps to be applied:")
            for step in steps:
                st.write(step)

    def get_processing_config(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert UI settings to processing configuration.
        
        Args:
            settings: UI settings dictionary
            
        Returns:
            Processing configuration dictionary
        """
        config = {
            # Core processing
            'noise_reduction_strength': settings.get('noise_reduction_strength', 0.5),
            'gentle_noise_reduction': settings.get('noise_reduction_strength', 0.5) * 0.5,  # Half strength for gentle areas
            'standard_noise_reduction': settings.get('noise_reduction_strength', 0.5),
            
            # Amplification
            'enable_amplification': settings.get('enable_amplification', True),
            'amplification_boost_db': settings.get('amplification_boost_db', 3.0),
            
            # Normalization
            'enable_normalization': settings.get('enable_normalization', True),
            'target_level_db': settings.get('target_level_db', -18.0),
            
            # Question handling
            'preserve_questions': settings.get('preserve_questions', False),
            'auto_detect_questions': settings.get('question_detection', True),
            'question_amplification_db': settings.get('question_amplification_db', 2.0),
            
            # Enhancement
            'speech_enhancement': settings.get('speech_enhancement', False),
            'high_freq_boost_db': settings.get('high_freq_boost_db', 0.0),
            'gentle_processing': settings.get('gentle_processing', False),
            
            # Advanced
            'preserve_dynamics': settings.get('preserve_dynamics', True),
            'compression_ratio': settings.get('compression_ratio', 3.0),
            'gate_threshold_db': settings.get('gate_threshold_db', -40.0),
            
            # Processing parameters
            'sample_rate': 44100,  # Default sample rate
        }
        
        return config

    def save_custom_preset(self, name: str, settings: Dict[str, Any]) -> bool:
        """
        Save custom preset to session state.
        
        Args:
            name: Preset name
            settings: Settings to save
            
        Returns:
            Success status
        """
        try:
            if 'custom_presets' not in st.session_state:
                st.session_state.custom_presets = {}
            
            st.session_state.custom_presets[name] = settings.copy()
            return True
        except Exception:
            return False

    def load_custom_preset(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Load custom preset from session state.
        
        Args:
            name: Preset name
            
        Returns:
            Settings dictionary or None if not found
        """
        if 'custom_presets' in st.session_state:
            return st.session_state.custom_presets.get(name)
        return None

    def get_available_presets(self) -> List[str]:
        """Get list of available custom presets."""
        if 'custom_presets' in st.session_state:
            return list(st.session_state.custom_presets.keys())
        return []