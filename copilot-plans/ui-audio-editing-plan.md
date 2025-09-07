# UI Audio Editing and Enhanced Processing Plan

## Executive Summary

This plan outlines the implementation of advanced audio editing capabilities in the Streamlit UI and enhanced audio processing features specifically designed for educational content with Q&A sessions. The plan addresses the need for interactive audio editing tools and specialized processing modes for classes with questions that are often filtered out by standard noise reduction algorithms.

## Current Audio Processing Analysis

### Existing Audio Processing Capabilities
- **Basic Enhancement**: Noise reduction, amplification, normalization
- **AI Models**: DeepFilterNet, Resemble Enhance, SpeechBrain
- **Processing Pipeline**: Sequential enhancement steps
- **UI Integration**: Basic processing controls

### Identified Gaps
1. **No Audio Editing**: Users cannot trim, split, or modify audio files
2. **Question Detection Issues**: Q&A sessions get filtered out by aggressive noise reduction
3. **Limited Control**: No fine-grained processing options
4. **No Preview**: Cannot preview changes before processing

## Phase 1: Audio Editing UI Components (Week 1-2)

### 1.1 Audio Waveform Visualization

**Create interactive waveform display:**
```python
# ui/components/audio_waveform.py
import streamlit as st
import plotly.graph_objects as go
from typing import Optional, Tuple, List
import numpy as np
from pydub import AudioSegment

class AudioWaveformViewer:
    def __init__(self, audio_data: np.ndarray, sample_rate: int):
        self.audio_data = audio_data
        self.sample_rate = sample_rate
        self.segments = []  # List of (start_time, end_time, action) tuples

    def render_waveform(self) -> Tuple[float, float]:
        """Render interactive waveform with selection capabilities."""
        # Create time axis
        time_axis = np.linspace(0, len(self.audio_data) / self.sample_rate,
                               len(self.audio_data))

        # Create plotly figure
        fig = go.Figure()

        # Add waveform trace
        fig.add_trace(go.Scatter(
            x=time_axis,
            y=self.audio_data,
            mode='lines',
            name='Audio Waveform',
            line=dict(color='blue', width=1)
        ))

        # Add segment overlays
        for start_time, end_time, action in self.segments:
            fig.add_vrect(
                x0=start_time, x1=end_time,
                fillcolor=self._get_action_color(action),
                opacity=0.3,
                layer="below",
                line_width=0,
            )

        # Configure layout
        fig.update_layout(
            title="Audio Waveform Editor",
            xaxis_title="Time (seconds)",
            yaxis_title="Amplitude",
            height=300,
            dragmode='select'
        )

        # Add selection callback
        fig.update_layout(
            selectdirection="horizontal",
            clickmode='event+select'
        )

        return st.plotly_chart(fig, use_container_width=True)

    def _get_action_color(self, action: str) -> str:
        """Get color for different actions."""
        colors = {
            'keep': 'green',
            'remove': 'red',
            'amplify': 'yellow',
            'question': 'purple'
        }
        return colors.get(action, 'gray')

    def add_segment(self, start_time: float, end_time: float, action: str):
        """Add a segment with specific action."""
        self.segments.append((start_time, end_time, action))

    def get_segments(self) -> List[Tuple[float, float, str]]:
        """Get all defined segments."""
        return self.segments.copy()

    def clear_segments(self):
        """Clear all segments."""
        self.segments.clear()
```

### 1.2 Audio Editing Controls

**Create editing control panel:**
```python
# ui/components/audio_editor.py
import streamlit as st
from typing import Optional, Dict, Any
import numpy as np

class AudioEditor:
    def __init__(self):
        self.selected_region = None
        self.editing_mode = "select"

    def render_controls(self) -> Dict[str, Any]:
        """Render audio editing controls."""
        st.subheader("🎵 Audio Editor")

        # Mode selection
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if st.button("✂️ Select", type="primary" if self.editing_mode == "select" else "secondary"):
                self.editing_mode = "select"

        with col2:
            if st.button("🗑️ Remove", type="primary" if self.editing_mode == "remove" else "secondary"):
                self.editing_mode = "remove"

        with col3:
            if st.button("🔊 Amplify", type="primary" if self.editing_mode == "amplify" else "secondary"):
                self.editing_mode = "amplify"

        with col4:
            if st.button("❓ Mark Q&A", type="primary" if self.editing_mode == "question" else "secondary"):
                self.editing_mode = "question"

        # Advanced controls
        with st.expander("Advanced Editing"):
            return self._render_advanced_controls()

        return {
            'mode': self.editing_mode,
            'selected_region': self.selected_region
        }

    def _render_advanced_controls(self) -> Dict[str, Any]:
        """Render advanced editing controls."""
        controls = {}

        # Fade in/out
        st.subheader("Fade Controls")
        col1, col2 = st.columns(2)
        with col1:
            controls['fade_in'] = st.slider("Fade In (seconds)", 0.0, 5.0, 0.5)
        with col2:
            controls['fade_out'] = st.slider("Fade Out (seconds)", 0.0, 5.0, 0.5)

        # Volume adjustment
        st.subheader("Volume Adjustment")
        controls['volume_boost'] = st.slider("Volume Boost (dB)", -20.0, 20.0, 0.0)

        # Split controls
        st.subheader("Split Audio")
        if st.button("Split at Selection"):
            controls['split_action'] = True

        return controls

    def apply_edit(self, audio_data: np.ndarray, edit_params: Dict[str, Any]) -> np.ndarray:
        """Apply editing operation to audio data."""
        if self.editing_mode == "remove" and self.selected_region:
            return self._remove_region(audio_data, self.selected_region)
        elif self.editing_mode == "amplify" and self.selected_region:
            return self._amplify_region(audio_data, self.selected_region, edit_params.get('volume_boost', 3.0))
        elif edit_params.get('split_action'):
            return self._split_audio(audio_data, self.selected_region)

        return audio_data

    def _remove_region(self, audio_data: np.ndarray, region: Tuple[float, float]) -> np.ndarray:
        """Remove selected region from audio."""
        start_sample = int(region[0] * self.sample_rate)
        end_sample = int(region[1] * self.sample_rate)

        # Remove the selected region
        return np.concatenate([audio_data[:start_sample], audio_data[end_sample:]])

    def _amplify_region(self, audio_data: np.ndarray, region: Tuple[float, float], boost_db: float) -> np.ndarray:
        """Amplify selected region."""
        start_sample = int(region[0] * self.sample_rate)
        end_sample = int(region[1] * self.sample_rate)

        # Apply amplification to selected region
        boost_factor = 10 ** (boost_db / 20)
        audio_data[start_sample:end_sample] *= boost_factor

        return audio_data

    def _split_audio(self, audio_data: np.ndarray, region: Tuple[float, float]) -> Tuple[np.ndarray, np.ndarray]:
        """Split audio at selected region."""
        split_sample = int(region[0] * self.sample_rate)

        return audio_data[:split_sample], audio_data[split_sample:]
```

### 1.3 Audio Preview System

**Create audio preview functionality:**
```python
# ui/components/audio_preview.py
import streamlit as st
from typing import Optional, Dict, Any
import tempfile
import os
from pydub import AudioSegment
import base64

class AudioPreview:
    def __init__(self):
        self.temp_files = []

    def render_preview_controls(self) -> Dict[str, Any]:
        """Render audio preview controls."""
        st.subheader("🔊 Audio Preview")

        col1, col2, col3 = st.columns(3)

        controls = {}

        with col1:
            if st.button("▶️ Play Original"):
                controls['action'] = 'play_original'

        with col2:
            if st.button("▶️ Play Edited"):
                controls['action'] = 'play_edited'

        with col3:
            if st.button("🔄 Reset"):
                controls['action'] = 'reset'

        # Volume control
        controls['preview_volume'] = st.slider("Preview Volume", 0.0, 1.0, 0.7)

        return controls

    def create_preview_audio(self, audio_data: np.ndarray, sample_rate: int,
                           file_format: str = "wav") -> Optional[str]:
        """Create temporary audio file for preview."""
        try:
            # Convert numpy array to AudioSegment
            audio_segment = AudioSegment(
                audio_data.tobytes(),
                frame_rate=sample_rate,
                sample_width=2,  # 16-bit
                channels=1
            )

            # Create temporary file
            with tempfile.NamedTemporaryFile(suffix=f'.{file_format}', delete=False) as temp_file:
                audio_segment.export(temp_file.name, format=file_format)
                self.temp_files.append(temp_file.name)
                return temp_file.name

        except Exception as e:
            st.error(f"Failed to create preview: {e}")
            return None

    def render_audio_player(self, audio_file_path: str):
        """Render HTML audio player."""
        if not os.path.exists(audio_file_path):
            st.error("Audio file not found")
            return

        # Read file and encode as base64
        with open(audio_file_path, "rb") as f:
            audio_bytes = f.read()

        audio_base64 = base64.b64encode(audio_bytes).decode()

        # Create HTML audio player
        audio_html = f"""
        <audio controls style="width: 100%;">
            <source src="data:audio/wav;base64,{audio_base64}" type="audio/wav">
            Your browser does not support the audio element.
        </audio>
        """

        st.markdown(audio_html, unsafe_allow_html=True)

    def cleanup_temp_files(self):
        """Clean up temporary audio files."""
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except Exception:
                pass  # Ignore cleanup errors
        self.temp_files.clear()
```

## Phase 2: Enhanced Audio Processing for Q&A Content (Week 3-4)

### 2.1 Question Detection and Preservation

**Create specialized processing for Q&A segments:**
```python
# src/audio/question_processor.py
import numpy as np
from typing import List, Tuple, Dict, Any
import librosa
from scipy.signal import find_peaks

class QuestionProcessor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.sample_rate = config.get('sample_rate', 44100)

    def detect_question_segments(self, audio_data: np.ndarray) -> List[Tuple[float, float]]:
        """Detect potential question segments in audio."""
        # Convert to mono if stereo
        if audio_data.ndim > 1:
            audio_data = np.mean(audio_data, axis=0)

        # Calculate RMS energy
        frame_length = int(0.025 * self.sample_rate)  # 25ms frames
        hop_length = int(0.010 * self.sample_rate)    # 10ms hop

        rms = librosa.feature.rms(y=audio_data, frame_length=frame_length, hop_length=hop_length)[0]

        # Find peaks in RMS (potential speech segments)
        peaks, properties = find_peaks(rms, height=np.mean(rms), distance=int(0.5 * self.sample_rate / hop_length))

        # Analyze segments for question characteristics
        question_segments = []
        for peak in peaks:
            start_time = peak * hop_length / self.sample_rate
            segment = self._extract_segment(audio_data, start_time, 3.0)  # 3 second window

            if self._is_question_segment(segment):
                # Extend segment to include full question
                extended_segment = self._extend_segment(audio_data, start_time, segment)
                question_segments.append(extended_segment)

        return question_segments

    def _is_question_segment(self, segment: np.ndarray) -> bool:
        """Determine if a segment contains a question."""
        # Analyze pitch patterns (questions often have rising intonation)
        pitches, magnitudes = librosa.piptrack(y=segment, sr=self.sample_rate)

        # Look for rising pitch patterns
        pitch_trend = self._analyze_pitch_trend(pitches, magnitudes)

        # Analyze pause patterns (questions often followed by pauses)
        pauses = self._detect_pauses(segment)

        # Question words detection (if transcription available)
        question_words = self._detect_question_words(segment)

        # Combine indicators
        question_score = (
            pitch_trend * 0.4 +
            pauses * 0.3 +
            question_words * 0.3
        )

        return question_score > self.config.get('question_threshold', 0.6)

    def _analyze_pitch_trend(self, pitches: np.ndarray, magnitudes: np.ndarray) -> float:
        """Analyze pitch trend for rising intonation."""
        # Get dominant pitch over time
        dominant_pitches = []
        for i in range(pitches.shape[1]):
            pitch_values = pitches[:, i]
            mag_values = magnitudes[:, i]
            if np.max(mag_values) > 0.1:  # Significant magnitude
                dominant_pitch = pitch_values[np.argmax(mag_values)]
                if dominant_pitch > 75:  # Filter out noise
                    dominant_pitches.append(dominant_pitch)

        if len(dominant_pitches) < 5:
            return 0.0

        # Calculate trend (rising = positive slope)
        x = np.arange(len(dominant_pitches))
        slope = np.polyfit(x, dominant_pitches, 1)[0]

        # Normalize to 0-1 scale
        return max(0, min(1, (slope + 50) / 100))  # Adjust based on typical ranges

    def _detect_pauses(self, segment: np.ndarray) -> float:
        """Detect pauses that often follow questions."""
        # Calculate short-term energy
        frame_length = int(0.020 * self.sample_rate)  # 20ms frames
        hop_length = int(0.010 * self.sample_rate)    # 10ms hop

        rms = librosa.feature.rms(y=segment, frame_length=frame_length, hop_length=hop_length)[0]

        # Find low-energy regions (pauses)
        threshold = np.mean(rms) * 0.3
        pause_frames = np.sum(rms < threshold)

        return min(1.0, pause_frames / len(rms))

    def _detect_question_words(self, segment: np.ndarray) -> float:
        """Detect question words using speech recognition."""
        # This would integrate with speech-to-text
        # For now, return a placeholder based on segment characteristics
        return 0.5  # Placeholder

    def _extract_segment(self, audio_data: np.ndarray, start_time: float, duration: float) -> np.ndarray:
        """Extract audio segment."""
        start_sample = int(start_time * self.sample_rate)
        end_sample = int((start_time + duration) * self.sample_rate)
        return audio_data[start_sample:end_sample]

    def _extend_segment(self, audio_data: np.ndarray, start_time: float, segment: np.ndarray) -> Tuple[float, float]:
        """Extend segment to include full question context."""
        # Look for silence before and after to find boundaries
        start_sample = int(start_time * self.sample_rate)

        # Extend backward to find start of question
        extended_start = self._find_segment_start(audio_data, start_sample)

        # Extend forward to find end of question
        extended_end = self._find_segment_end(audio_data, start_sample + len(segment))

        return (extended_start / self.sample_rate, extended_end / self.sample_rate)

    def _find_segment_start(self, audio_data: np.ndarray, current_pos: int) -> int:
        """Find the start of a speech segment."""
        window_size = int(0.1 * self.sample_rate)  # 100ms window
        threshold = np.mean(np.abs(audio_data)) * 0.5

        for i in range(current_pos, max(0, current_pos - int(2 * self.sample_rate)), -window_size):
            window = audio_data[max(0, i - window_size):i]
            if np.mean(np.abs(window)) < threshold:
                return i

        return max(0, current_pos - int(1 * self.sample_rate))

    def _find_segment_end(self, audio_data: np.ndarray, current_pos: int) -> int:
        """Find the end of a speech segment."""
        window_size = int(0.1 * self.sample_rate)  # 100ms window
        threshold = np.mean(np.abs(audio_data)) * 0.5

        for i in range(current_pos, min(len(audio_data), current_pos + int(2 * self.sample_rate)), window_size):
            window = audio_data[i:i + window_size]
            if np.mean(np.abs(window)) < threshold:
                return i

        return min(len(audio_data), current_pos + int(1 * self.sample_rate))
```

### 2.2 Adaptive Noise Reduction

**Create context-aware noise reduction:**
```python
# src/audio/adaptive_processor.py
import numpy as np
from typing import Dict, Any, List, Tuple
from scipy.signal import butter, filtfilt

class AdaptiveAudioProcessor:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.question_segments = []

    def process_with_question_preservation(self, audio_data: np.ndarray,
                                         question_segments: List[Tuple[float, float]]) -> np.ndarray:
        """Process audio while preserving question segments."""
        self.question_segments = question_segments

        # Apply different processing strategies
        processed_audio = audio_data.copy()

        # Process non-question segments with standard noise reduction
        processed_audio = self._apply_adaptive_noise_reduction(processed_audio)

        # Process question segments with gentle enhancement
        processed_audio = self._enhance_question_segments(processed_audio)

        # Apply overall normalization
        processed_audio = self._apply_adaptive_normalization(processed_audio)

        return processed_audio

    def _apply_adaptive_noise_reduction(self, audio_data: np.ndarray) -> np.ndarray:
        """Apply noise reduction that's less aggressive near questions."""
        processed = audio_data.copy()

        for start_time, end_time in self.question_segments:
            # Create gentle noise reduction around question segments
            start_sample = int(start_time * self.config.get('sample_rate', 44100))
            end_sample = int(end_time * self.config.get('sample_rate', 44100))

            # Extend processing window
            window_start = max(0, start_sample - int(2 * self.config.get('sample_rate', 44100)))
            window_end = min(len(processed), end_sample + int(2 * self.config.get('sample_rate', 44100)))

            # Apply less aggressive noise reduction in this window
            processed[window_start:window_end] = self._gentle_noise_reduction(
                processed[window_start:window_end]
            )

        # Apply standard noise reduction to remaining segments
        mask = self._create_question_mask(len(processed))
        non_question_segments = processed[~mask]
        processed[~mask] = self._standard_noise_reduction(non_question_segments)

        return processed

    def _gentle_noise_reduction(self, audio_segment: np.ndarray) -> np.ndarray:
        """Apply gentle noise reduction for question segments."""
        # Use lighter spectral subtraction
        # Reduce noise by smaller factor
        reduction_factor = 0.3  # Less aggressive than standard 0.5-0.7

        # Simple noise gate for very quiet parts
        threshold = np.mean(np.abs(audio_segment)) * 0.2
        mask = np.abs(audio_segment) < threshold
        audio_segment[mask] *= 0.1  # Very gentle attenuation

        return audio_segment

    def _standard_noise_reduction(self, audio_segment: np.ndarray) -> np.ndarray:
        """Apply standard noise reduction."""
        # More aggressive noise reduction for non-question segments
        reduction_factor = 0.6

        # Spectral subtraction or other noise reduction method
        # This is a placeholder for the actual implementation
        return audio_segment * (1 - reduction_factor)

    def _enhance_question_segments(self, audio_data: np.ndarray) -> np.ndarray:
        """Apply enhancement specifically to question segments."""
        enhanced = audio_data.copy()

        for start_time, end_time in self.question_segments:
            start_sample = int(start_time * self.config.get('sample_rate', 44100))
            end_sample = int(end_time * self.config.get('sample_rate', 44100))

            segment = enhanced[start_sample:end_sample]

            # Apply gentle amplification
            segment = self._amplify_segment(segment, boost_db=2.0)

            # Apply subtle EQ to enhance clarity
            segment = self._apply_clarity_eq(segment)

            enhanced[start_sample:end_sample] = segment

        return enhanced

    def _amplify_segment(self, segment: np.ndarray, boost_db: float) -> np.ndarray:
        """Amplify audio segment."""
        boost_factor = 10 ** (boost_db / 20)
        return segment * boost_factor

    def _apply_clarity_eq(self, segment: np.ndarray) -> np.ndarray:
        """Apply subtle EQ to enhance speech clarity."""
        # Simple high-frequency boost for clarity
        # This is a placeholder for actual EQ implementation
        return segment * 1.1  # Slight overall boost

    def _apply_adaptive_normalization(self, audio_data: np.ndarray) -> np.ndarray:
        """Apply normalization that accounts for question segments."""
        # Calculate target level based on question segments
        question_levels = []
        for start_time, end_time in self.question_segments:
            start_sample = int(start_time * self.config.get('sample_rate', 44100))
            end_sample = int(end_time * self.config.get('sample_rate', 44100))
            segment = audio_data[start_sample:end_sample]
            question_levels.append(np.mean(np.abs(segment)))

        if question_levels:
            # Use slightly lower target to preserve question dynamics
            target_level = np.mean(question_levels) * 0.9
        else:
            # Standard normalization
            target_level = np.mean(np.abs(audio_data)) * 0.7

        # Apply normalization
        current_level = np.mean(np.abs(audio_data))
        if current_level > 0:
            normalization_factor = target_level / current_level
            audio_data *= normalization_factor

        return audio_data

    def _create_question_mask(self, length: int) -> np.ndarray:
        """Create boolean mask for question segments."""
        mask = np.zeros(length, dtype=bool)
        sample_rate = self.config.get('sample_rate', 44100)

        for start_time, end_time in self.question_segments:
            start_sample = int(start_time * sample_rate)
            end_sample = int(end_time * sample_rate)
            mask[start_sample:end_sample] = True

        return mask
```

### 2.3 UI Processing Mode Toggle

**Create UI controls for processing modes:**
```python
# ui/components/processing_modes.py
import streamlit as st
from typing import Dict, Any, List

class ProcessingModeSelector:
    def __init__(self):
        self.modes = {
            'standard': {
                'name': 'Standard Processing',
                'description': 'Balanced noise reduction and enhancement',
                'settings': {
                    'noise_reduction': 0.6,
                    'amplification': True,
                    'normalization': True,
                    'question_preservation': False
                }
            },
            'question_friendly': {
                'name': 'Question-Friendly Processing',
                'description': 'Gentle processing that preserves Q&A segments',
                'settings': {
                    'noise_reduction': 0.3,
                    'amplification': True,
                    'normalization': True,
                    'question_preservation': True,
                    'question_detection': True
                }
            },
            'lecture_mode': {
                'name': 'Lecture Mode',
                'description': 'Optimized for clear speech with minimal interruptions',
                'settings': {
                    'noise_reduction': 0.7,
                    'amplification': True,
                    'normalization': True,
                    'question_preservation': False,
                    'speech_enhancement': True
                }
            },
            'custom': {
                'name': 'Custom Settings',
                'description': 'Manually configure all processing options',
                'settings': {}
            }
        }

    def render_mode_selector(self) -> Dict[str, Any]:
        """Render processing mode selection UI."""
        st.subheader("🎛️ Processing Mode")

        # Mode selection
        mode_options = list(self.modes.keys())
        mode_names = [self.modes[mode]['name'] for mode in mode_options]

        selected_mode_name = st.selectbox(
            "Select Processing Mode",
            mode_names,
            help="Choose the processing mode that best fits your content type"
        )

        # Find selected mode key
        selected_mode = None
        for mode_key, mode_info in self.modes.items():
            if mode_info['name'] == selected_mode_name:
                selected_mode = mode_key
                break

        # Display mode description
        if selected_mode:
            st.info(self.modes[selected_mode]['description'])

            # Show mode-specific settings
            return self._render_mode_settings(selected_mode)

        return {}

    def _render_mode_settings(self, mode: str) -> Dict[str, Any]:
        """Render settings for the selected mode."""
        settings = self.modes[mode]['settings'].copy()

        if mode == 'custom':
            return self._render_custom_settings()
        else:
            # Show current settings for selected mode
            with st.expander("Current Settings"):
                for key, value in settings.items():
                    st.write(f"**{key.replace('_', ' ').title()}**: {value}")

            # Allow fine-tuning
            return self._render_fine_tuning(settings)

    def _render_custom_settings(self) -> Dict[str, Any]:
        """Render custom settings interface."""
        st.subheader("Custom Processing Settings")

        settings = {}

        # Noise reduction
        settings['noise_reduction'] = st.slider(
            "Noise Reduction Strength",
            0.0, 1.0, 0.5,
            help="Higher values remove more noise but may affect speech quality"
        )

        # Amplification
        settings['amplification'] = st.checkbox(
            "Enable Amplification",
            value=True,
            help="Automatically boost quiet sections"
        )

        if settings['amplification']:
            settings['amplification_boost'] = st.slider(
                "Amplification Boost (dB)",
                0.0, 12.0, 3.0
            )

        # Normalization
        settings['normalization'] = st.checkbox(
            "Enable Normalization",
            value=True,
            help="Balance audio levels across the recording"
        )

        # Question preservation
        settings['question_preservation'] = st.checkbox(
            "Preserve Q&A Segments",
            value=False,
            help="Use gentle processing for question and answer sections"
        )

        if settings['question_preservation']:
            settings['question_detection'] = st.checkbox(
                "Auto-detect Questions",
                value=True,
                help="Automatically detect and preserve question segments"
            )

        # Advanced options
        with st.expander("Advanced Options"):
            settings['speech_enhancement'] = st.checkbox(
                "Speech Enhancement",
                value=False,
                help="Apply AI speech enhancement (slower processing)"
            )

            settings['high_freq_boost'] = st.slider(
                "High Frequency Boost",
                0.0, 6.0, 0.0,
                help="Boost high frequencies for better clarity"
            )

        return settings

    def _render_fine_tuning(self, base_settings: Dict[str, Any]) -> Dict[str, Any]:
        """Render fine-tuning options for preset modes."""
        st.subheader("Fine-tune Settings")

        settings = base_settings.copy()

        # Allow adjustment of key parameters
        if st.checkbox("Customize Noise Reduction"):
            settings['noise_reduction'] = st.slider(
                "Noise Reduction",
                0.0, 1.0, base_settings.get('noise_reduction', 0.5)
            )

        if st.checkbox("Customize Amplification"):
            settings['amplification_boost'] = st.slider(
                "Amplification Boost (dB)",
                0.0, 12.0, base_settings.get('amplification_boost', 3.0)
            )

        return settings

    def get_processing_config(self, mode_settings: Dict[str, Any]) -> Dict[str, Any]:
        """Convert UI settings to processing configuration."""
        config = {
            'noise_reduction_strength': mode_settings.get('noise_reduction', 0.5),
            'enable_amplification': mode_settings.get('amplification', True),
            'amplification_boost_db': mode_settings.get('amplification_boost', 3.0),
            'enable_normalization': mode_settings.get('normalization', True),
            'preserve_questions': mode_settings.get('question_preservation', False),
            'auto_detect_questions': mode_settings.get('question_detection', True),
            'speech_enhancement': mode_settings.get('speech_enhancement', False),
            'high_freq_boost_db': mode_settings.get('high_freq_boost', 0.0)
        }

        return config
```

## Phase 3: Integration and UI Enhancement (Week 5-6)

### 3.1 New Sermon Upload Page

**Create enhanced upload page:**
```python
# ui/pages/new_sermon_enhanced.py
import streamlit as st
from typing import Optional, Dict, Any
import tempfile
import os
from pathlib import Path

from ui.components.audio_waveform import AudioWaveformViewer
from ui.components.audio_editor import AudioEditor
from ui.components.audio_preview import AudioPreview
from ui.components.processing_modes import ProcessingModeSelector
from src.audio.question_processor import QuestionProcessor
from src.audio.adaptive_processor import AdaptiveAudioProcessor

def render():
    """Render enhanced new sermon upload page."""
    st.header("🎵 New Sermon with Audio Editing")

    # File upload
    uploaded_file = st.file_uploader(
        "Upload Audio File",
        type=['mp3', 'wav', 'm4a', 'flac'],
        help="Supported formats: MP3, WAV, M4A, FLAC"
    )

    if uploaded_file is None:
        _render_upload_instructions()
        return

    # Process uploaded file
    with st.spinner("Loading audio file..."):
        audio_data, sample_rate, temp_file_path = _process_uploaded_file(uploaded_file)

    if audio_data is None:
        st.error("Failed to load audio file")
        return

    # Initialize components
    waveform_viewer = AudioWaveformViewer(audio_data, sample_rate)
    audio_editor = AudioEditor()
    audio_preview = AudioPreview()
    mode_selector = ProcessingModeSelector()

    # Create tabs for different stages
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Analyze Audio",
        "✂️ Edit Audio",
        "🎛️ Configure Processing",
        "▶️ Process & Upload"
    ])

    with tab1:
        _render_analysis_tab(waveform_viewer, audio_data, sample_rate)

    with tab2:
        _render_editing_tab(audio_editor, waveform_viewer, audio_preview, temp_file_path)

    with tab3:
        processing_config = _render_processing_tab(mode_selector)

    with tab4:
        _render_processing_tab(
            audio_data, sample_rate, processing_config,
            waveform_viewer.get_segments(), temp_file_path
        )

def _process_uploaded_file(uploaded_file) -> tuple:
    """Process uploaded audio file."""
    # Save to temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
        temp_file.write(uploaded_file.getvalue())
        temp_file_path = temp_file.name

    try:
        # Load audio data
        from pydub import AudioSegment
        audio = AudioSegment.from_file(temp_file_path)

        # Convert to numpy array
        import numpy as np
        audio_data = np.array(audio.get_array_of_samples(), dtype=np.float32)
        if audio.channels == 2:
            audio_data = audio_data.reshape((-1, 2))
            audio_data = np.mean(audio_data, axis=1)  # Convert to mono

        # Normalize to [-1, 1]
        audio_data = audio_data / (2**15)  # Assuming 16-bit audio

        return audio_data, audio.frame_rate, temp_file_path

    except Exception as e:
        st.error(f"Error processing audio file: {e}")
        return None, None, None

def _render_upload_instructions():
    """Render upload instructions."""
    st.info("📝 **How to use the enhanced audio editor:**")
    st.markdown("""
    1. **Upload** your audio file (MP3, WAV, M4A, FLAC)
    2. **Analyze** the audio to detect potential issues and Q&A segments
    3. **Edit** the audio by selecting regions to trim, amplify, or mark as questions
    4. **Configure** processing settings optimized for your content type
    5. **Process** the audio with AI enhancement and upload to SermonAudio
    """)

    st.subheader("✨ New Features")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Audio Editing:**")
        st.markdown("- ✂️ Trim unwanted sections")
        st.markdown("- 🔊 Amplify quiet parts")
        st.markdown("- ❓ Mark Q&A segments")
        st.markdown("- 🎚️ Adjust fade in/out")

    with col2:
        st.markdown("**Smart Processing:**")
        st.markdown("- 🧠 Auto-detect questions")
        st.markdown("- 🎯 Preserve Q&A audio quality")
        st.markdown("- 📊 Adaptive noise reduction")
        st.markdown("- 🔧 Multiple processing modes")

def _render_analysis_tab(waveform_viewer, audio_data, sample_rate):
    """Render audio analysis tab."""
    st.subheader("🔍 Audio Analysis")

    # Display basic audio info
    col1, col2, col3 = st.columns(3)
    with col1:
        duration = len(audio_data) / sample_rate
        st.metric("Duration", ".1f")
    with col2:
        st.metric("Sample Rate", f"{sample_rate} Hz")
    with col3:
        st.metric("Channels", "Mono")

    # Render waveform
    st.subheader("Waveform Visualization")
    selected_region = waveform_viewer.render_waveform()

    # Analysis options
    if st.button("🔍 Analyze for Issues"):
        with st.spinner("Analyzing audio..."):
            issues = _analyze_audio_issues(audio_data, sample_rate)
            if issues:
                st.warning("**Potential Issues Detected:**")
                for issue in issues:
                    st.write(f"• {issue}")
            else:
                st.success("No significant issues detected!")

    if st.button("❓ Detect Q&A Segments"):
        with st.spinner("Detecting question segments..."):
            question_processor = QuestionProcessor({'sample_rate': sample_rate})
            question_segments = question_processor.detect_question_segments(audio_data)

            if question_segments:
                st.success(f"Found {len(question_segments)} potential Q&A segments")

                # Mark segments on waveform
                for start_time, end_time in question_segments:
                    waveform_viewer.add_segment(start_time, end_time, 'question')

                # Display segment list
                st.subheader("Detected Q&A Segments")
                for i, (start, end) in enumerate(question_segments):
                    st.write(".1f")
            else:
                st.info("No Q&A segments automatically detected. You can mark them manually in the editing tab.")

def _render_editing_tab(audio_editor, waveform_viewer, audio_preview, temp_file_path):
    """Render audio editing tab."""
    st.subheader("🎵 Audio Editing")

    # Editing controls
    edit_params = audio_editor.render_controls()

    # Display current segments
    segments = waveform_viewer.get_segments()
    if segments:
        st.subheader("Current Edits")
        for i, (start, end, action) in enumerate(segments):
            col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
            with col1:
                st.write(".1f")
            with col2:
                st.write(".1f")
            with col3:
                st.write(f"**{action.title()}**")
            with col4:
                if st.button("❌", key=f"remove_segment_{i}"):
                    segments.pop(i)
                    waveform_viewer.clear_segments()
                    for seg in segments:
                        waveform_viewer.add_segment(*seg)
                    st.rerun()

    # Preview controls
    preview_controls = audio_preview.render_preview_controls()

    if preview_controls.get('action') == 'play_original':
        audio_preview.render_audio_player(temp_file_path)
    elif preview_controls.get('action') == 'reset':
        waveform_viewer.clear_segments()
        st.success("All edits cleared!")
        st.rerun()

def _render_processing_tab(mode_selector):
    """Render processing configuration tab."""
    return mode_selector.render_mode_selector()

def _render_processing_tab(audio_data, sample_rate, processing_config, segments, temp_file_path):
    """Render final processing and upload tab."""
    st.subheader("🚀 Process & Upload")

    # Sermon metadata form
    with st.form("sermon_metadata"):
        st.subheader("Sermon Information")

        title = st.text_input("Sermon Title", placeholder="Enter sermon title")
        speaker = st.text_input("Speaker", placeholder="Enter speaker name")
        date = st.date_input("Sermon Date")
        event_type = st.selectbox("Event Type", [
            "Sunday - AM", "Sunday - PM", "Wednesday - PM",
            "Special Event", "Conference", "Other"
        ])
        bible_text = st.text_input("Bible Text (optional)", placeholder="e.g., John 3:16")

        submitted = st.form_submit_button("🎵 Process Audio & Create Sermon")

    if submitted:
        if not title or not speaker:
            st.error("Please fill in at least title and speaker")
            return

        # Process audio with selected configuration
        with st.spinner("Processing audio..."):
            processed_audio = _process_audio_with_config(
                audio_data, sample_rate, processing_config, segments
            )

        # Save processed audio
        processed_file_path = _save_processed_audio(processed_audio, sample_rate)

        # Display results
        st.success("✅ Audio processed successfully!")

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Original Duration", ".1f")
        with col2:
            st.metric("Processed Duration", ".1f")

        # Upload to SermonAudio
        if st.button("📤 Upload to SermonAudio", type="primary"):
            _upload_to_sermonaudio(
                processed_file_path, title, speaker, date,
                event_type, bible_text
            )

def _analyze_audio_issues(audio_data, sample_rate) -> list:
    """Analyze audio for potential issues."""
    issues = []

    # Check for clipping
    if np.max(np.abs(audio_data)) > 0.95:
        issues.append("Audio may be clipped - consider reducing levels")

    # Check for low volume
    rms = np.sqrt(np.mean(audio_data**2))
    if rms < 0.01:
        issues.append("Audio levels are very low - will be amplified")

    # Check for DC offset
    dc_offset = np.mean(audio_data)
    if abs(dc_offset) > 0.01:
        issues.append("DC offset detected - will be corrected")

    return issues

def _process_audio_with_config(audio_data, sample_rate, config, segments):
    """Process audio with the selected configuration."""
    # Apply user edits first
    edited_audio = _apply_user_edits(audio_data, sample_rate, segments)

    # Apply processing based on configuration
    if config.get('preserve_questions'):
        question_processor = QuestionProcessor({'sample_rate': sample_rate})
        question_segments = question_processor.detect_question_segments(edited_audio)

        adaptive_processor = AdaptiveAudioProcessor({
            'sample_rate': sample_rate,
            **config
        })
        processed_audio = adaptive_processor.process_with_question_preservation(
            edited_audio, question_segments
        )
    else:
        # Standard processing
        processed_audio = _apply_standard_processing(edited_audio, config)

    return processed_audio

def _apply_user_edits(audio_data, sample_rate, segments):
    """Apply user-defined edits to audio."""
    edited_audio = audio_data.copy()

    for start_time, end_time, action in segments:
        start_sample = int(start_time * sample_rate)
        end_sample = int(end_time * sample_rate)

        if action == 'remove':
            edited_audio = np.concatenate([
                edited_audio[:start_sample],
                edited_audio[end_sample:]
            ])
        elif action == 'amplify':
            boost_factor = 10 ** (3.0 / 20)  # 3dB boost
            edited_audio[start_sample:end_sample] *= boost_factor

    return edited_audio

def _apply_standard_processing(audio_data, config):
    """Apply standard audio processing."""
    # Placeholder for standard processing pipeline
    processed = audio_data.copy()

    # Apply noise reduction
    if config.get('noise_reduction_strength', 0.5) > 0:
        noise_factor = config['noise_reduction_strength']
        processed *= (1 - noise_factor)

    # Apply amplification
    if config.get('enable_amplification'):
        boost_db = config.get('amplification_boost_db', 3.0)
        boost_factor = 10 ** (boost_db / 20)
        processed *= boost_factor

    # Apply normalization
    if config.get('enable_normalization'):
        target_level = np.mean(np.abs(processed)) * 0.7
        current_level = np.mean(np.abs(processed))
        if current_level > 0:
            processed *= (target_level / current_level)

    return processed

def _save_processed_audio(audio_data, sample_rate):
    """Save processed audio to temporary file."""
    from pydub import AudioSegment
    import tempfile

    # Convert back to AudioSegment
    audio_segment = AudioSegment(
        (audio_data * 32767).astype(np.int16).tobytes(),
        frame_rate=sample_rate,
        sample_width=2,
        channels=1
    )

    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_file:
        audio_segment.export(temp_file.name, format='mp3')
        return temp_file.name

def _upload_to_sermonaudio(file_path, title, speaker, date, event_type, bible_text):
    """Upload processed sermon to SermonAudio."""
    # Placeholder for SermonAudio upload logic
    st.info("📤 Upload functionality would be implemented here")
    st.write(f"**Title:** {title}")
    st.write(f"**Speaker:** {speaker}")
    st.write(f"**Date:** {date}")
    st.write(f"**Event Type:** {event_type}")
    st.write(f"**Bible Text:** {bible_text}")
    st.write(f"**File:** {file_path}")
```

## Implementation Timeline

### Week 1-2: Audio Editing UI
- [ ] Create AudioWaveformViewer component
- [ ] Implement AudioEditor controls
- [ ] Build AudioPreview system
- [ ] Integrate editing components into UI

### Week 3-4: Enhanced Processing
- [ ] Implement QuestionProcessor for Q&A detection
- [ ] Create AdaptiveAudioProcessor for context-aware processing
- [ ] Build ProcessingModeSelector UI component
- [ ] Test processing modes with different content types

### Week 5-6: Integration and Testing
- [ ] Create enhanced new sermon upload page
- [ ] Integrate all components into cohesive workflow
- [ ] Test end-to-end audio editing and processing
- [ ] Add comprehensive error handling and user feedback

## Success Criteria

### Audio Editing Features
- [ ] Users can visually select and edit audio regions
- [ ] Real-time preview of audio edits
- [ ] Support for trimming, amplification, and Q&A marking
- [ ] Intuitive waveform visualization

### Question Preservation
- [ ] Automatic detection of Q&A segments
- [ ] Adaptive noise reduction that preserves questions
- [ ] Specialized processing modes for educational content
- [ ] User controls for question preservation settings

### User Experience
- [ ] Clear workflow from upload to processing to upload
- [ ] Real-time feedback and progress indicators
- [ ] Comprehensive error handling and validation
- [ ] Accessible controls and helpful documentation

### Technical Performance
- [ ] Efficient audio processing without excessive memory usage
- [ ] Fast waveform rendering and real-time preview
- [ ] Reliable Q&A detection with configurable sensitivity
- [ ] Seamless integration with existing SermonAudio workflow

This plan provides a comprehensive solution for audio editing and enhanced processing, specifically addressing the challenges of processing educational content with Q&A segments while providing an intuitive user interface for content creators.
