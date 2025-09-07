# ui/components/audio_editor.py
import streamlit as st
from typing import Optional, Dict, Any, Tuple
import numpy as np


class AudioEditor:
    """Audio editing controls component."""
    
    def __init__(self):
        """Initialize the audio editor."""
        self.editing_mode = "select"
        self.selected_region = None
        
        # Initialize session state for editor
        if 'audio_editor_state' not in st.session_state:
            st.session_state.audio_editor_state = {
                'mode': 'select',
                'selected_start': 0.0,
                'selected_end': 0.0,
                'selection_valid': False
            }

    def render_controls(self, duration: float = 60.0) -> Dict[str, Any]:
        """
        Render audio editing controls.
        
        Args:
            duration: Total audio duration for validation
            
        Returns:
            Dictionary containing editor state and actions
        """
        st.subheader("🎵 Audio Editor")

        # Mode selection buttons
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if st.button("✂️ Select", 
                        type="primary" if self.editing_mode == "select" else "secondary",
                        help="Select regions for editing"):
                self.editing_mode = "select"
                st.session_state.audio_editor_state['mode'] = "select"

        with col2:
            if st.button("🗑️ Remove", 
                        type="primary" if self.editing_mode == "remove" else "secondary",
                        help="Mark regions for removal"):
                self.editing_mode = "remove"
                st.session_state.audio_editor_state['mode'] = "remove"

        with col3:
            if st.button("🔊 Amplify", 
                        type="primary" if self.editing_mode == "amplify" else "secondary",
                        help="Mark regions for amplification"):
                self.editing_mode = "amplify"
                st.session_state.audio_editor_state['mode'] = "amplify"

        with col4:
            if st.button("❓ Mark Q&A", 
                        type="primary" if self.editing_mode == "question" else "secondary",
                        help="Mark question and answer segments"):
                self.editing_mode = "question"
                st.session_state.audio_editor_state['mode'] = "question"

        # Manual region selection
        st.subheader("Manual Region Selection")
        col1, col2, col3 = st.columns([2, 2, 1])
        
        with col1:
            start_time = st.number_input(
                "Start Time (seconds)", 
                min_value=0.0, 
                max_value=duration,
                value=0.0,
                step=0.1,
                key="selection_start"
            )
        
        with col2:
            end_time = st.number_input(
                "End Time (seconds)", 
                min_value=start_time, 
                max_value=duration,
                value=min(start_time + 5.0, duration),
                step=0.1,
                key="selection_end"
            )
            
        with col3:
            if st.button("📍 Add Segment", type="primary"):
                return {
                    'action': 'add_segment',
                    'start_time': start_time,
                    'end_time': end_time,
                    'mode': self.editing_mode,
                    'segment_action': self.editing_mode
                }

        # Advanced controls
        with st.expander("Advanced Editing Options"):
            advanced_controls = self._render_advanced_controls()

        return {
            'mode': self.editing_mode,
            'selected_region': (start_time, end_time),
            'advanced_controls': advanced_controls
        }

    def _render_advanced_controls(self) -> Dict[str, Any]:
        """Render advanced editing controls."""
        controls = {}

        # Fade controls
        st.subheader("Fade Effects")
        col1, col2 = st.columns(2)
        with col1:
            controls['fade_in_duration'] = st.slider(
                "Fade In Duration (seconds)", 
                0.0, 5.0, 0.5,
                step=0.1,
                help="Duration of fade-in effect"
            )
        with col2:
            controls['fade_out_duration'] = st.slider(
                "Fade Out Duration (seconds)", 
                0.0, 5.0, 0.5,
                step=0.1,
                help="Duration of fade-out effect"
            )

        # Volume adjustment
        st.subheader("Volume Adjustment")
        controls['volume_boost_db'] = st.slider(
            "Volume Boost (dB)", 
            -20.0, 20.0, 0.0,
            step=1.0,
            help="Positive values increase volume, negative values decrease"
        )

        # Normalization options
        st.subheader("Normalization")
        controls['normalize_enabled'] = st.checkbox(
            "Enable Normalization",
            value=True,
            help="Automatically adjust levels for consistent volume"
        )
        
        if controls['normalize_enabled']:
            controls['target_level_db'] = st.slider(
                "Target Level (dB)",
                -30.0, -6.0, -18.0,
                step=1.0,
                help="Target audio level after normalization"
            )

        # Quality settings
        st.subheader("Quality Settings")
        controls['preserve_dynamics'] = st.checkbox(
            "Preserve Dynamics",
            value=True,
            help="Maintain natural volume variations"
        )
        
        controls['gentle_processing'] = st.checkbox(
            "Gentle Processing",
            value=False,
            help="Use less aggressive processing for sensitive content"
        )

        return controls

    def apply_edit(self, audio_data: np.ndarray, sample_rate: int, 
                   start_time: float, end_time: float, action: str,
                   **kwargs) -> np.ndarray:
        """
        Apply editing operation to audio data.
        
        Args:
            audio_data: Input audio data
            sample_rate: Audio sample rate
            start_time: Start time of selection
            end_time: End time of selection
            action: Type of edit to apply
            **kwargs: Additional parameters
            
        Returns:
            Modified audio data
        """
        start_sample = int(start_time * sample_rate)
        end_sample = int(end_time * sample_rate)
        
        # Validate indices
        start_sample = max(0, start_sample)
        end_sample = min(len(audio_data), end_sample)
        
        if start_sample >= end_sample:
            return audio_data
        
        if action == "remove":
            return self._remove_region(audio_data, start_sample, end_sample)
        elif action == "amplify":
            return self._amplify_region(
                audio_data, start_sample, end_sample, 
                kwargs.get('volume_boost_db', 3.0)
            )
        elif action == "fade_in":
            return self._apply_fade_in(
                audio_data, start_sample, end_sample,
                kwargs.get('fade_duration', 0.5), sample_rate
            )
        elif action == "fade_out":
            return self._apply_fade_out(
                audio_data, start_sample, end_sample,
                kwargs.get('fade_duration', 0.5), sample_rate
            )
        else:
            # For 'select' and 'question' modes, just return original
            return audio_data

    def _remove_region(self, audio_data: np.ndarray, start_sample: int, end_sample: int) -> np.ndarray:
        """Remove selected region from audio."""
        return np.concatenate([audio_data[:start_sample], audio_data[end_sample:]])

    def _amplify_region(self, audio_data: np.ndarray, start_sample: int, 
                       end_sample: int, boost_db: float) -> np.ndarray:
        """Amplify selected region."""
        result = audio_data.copy()
        boost_factor = 10 ** (boost_db / 20)
        result[start_sample:end_sample] *= boost_factor
        
        # Prevent clipping
        result = np.clip(result, -1.0, 1.0)
        
        return result

    def _apply_fade_in(self, audio_data: np.ndarray, start_sample: int, 
                      end_sample: int, fade_duration: float, sample_rate: int) -> np.ndarray:
        """Apply fade-in effect to selected region."""
        result = audio_data.copy()
        
        fade_samples = int(fade_duration * sample_rate)
        actual_fade_samples = min(fade_samples, end_sample - start_sample)
        
        if actual_fade_samples > 0:
            fade_curve = np.linspace(0, 1, actual_fade_samples)
            result[start_sample:start_sample + actual_fade_samples] *= fade_curve
        
        return result

    def _apply_fade_out(self, audio_data: np.ndarray, start_sample: int, 
                       end_sample: int, fade_duration: float, sample_rate: int) -> np.ndarray:
        """Apply fade-out effect to selected region."""
        result = audio_data.copy()
        
        fade_samples = int(fade_duration * sample_rate)
        actual_fade_samples = min(fade_samples, end_sample - start_sample)
        
        if actual_fade_samples > 0:
            fade_curve = np.linspace(1, 0, actual_fade_samples)
            result[end_sample - actual_fade_samples:end_sample] *= fade_curve
        
        return result

    def split_audio(self, audio_data: np.ndarray, split_time: float, 
                   sample_rate: int) -> Tuple[np.ndarray, np.ndarray]:
        """
        Split audio at specified time.
        
        Args:
            audio_data: Input audio data
            split_time: Time to split at (seconds)
            sample_rate: Audio sample rate
            
        Returns:
            Tuple of (first_part, second_part)
        """
        split_sample = int(split_time * sample_rate)
        split_sample = max(0, min(len(audio_data), split_sample))
        
        return audio_data[:split_sample], audio_data[split_sample:]

    def get_editing_summary(self, segments: list) -> Dict[str, Any]:
        """
        Get summary of editing operations.
        
        Args:
            segments: List of (start, end, action) tuples
            
        Returns:
            Summary statistics
        """
        if not segments:
            return {"total_segments": 0, "actions": {}}
        
        actions = {}
        total_duration = 0
        
        for start, end, action in segments:
            duration = end - start
            total_duration += duration
            
            if action not in actions:
                actions[action] = {"count": 0, "duration": 0}
            
            actions[action]["count"] += 1
            actions[action]["duration"] += duration
        
        return {
            "total_segments": len(segments),
            "total_edited_duration": total_duration,
            "actions": actions
        }