# ui/components/audio_waveform.py
import streamlit as st
import plotly.graph_objects as go
from typing import Optional, Tuple, List
import numpy as np


class AudioWaveformViewer:
    """Interactive waveform display component for audio editing."""
    
    def __init__(self, audio_data: np.ndarray, sample_rate: int):
        """
        Initialize the waveform viewer.
        
        Args:
            audio_data: Audio signal as numpy array
            sample_rate: Sample rate of the audio
        """
        self.audio_data = audio_data
        self.sample_rate = sample_rate
        self.segments = []  # List of (start_time, end_time, action) tuples
        self.duration = len(audio_data) / sample_rate

    def render_waveform(self) -> Optional[Tuple[float, float]]:
        """
        Render interactive waveform with selection capabilities.
        
        Returns:
            Selected region as (start_time, end_time) or None
        """
        # Create time axis
        time_axis = np.linspace(0, self.duration, len(self.audio_data))

        # Create plotly figure
        fig = go.Figure()

        # Add waveform trace
        fig.add_trace(go.Scatter(
            x=time_axis,
            y=self.audio_data,
            mode='lines',
            name='Audio Waveform',
            line=dict(color='blue', width=1),
            hovertemplate='Time: %{x:.2f}s<br>Amplitude: %{y:.3f}<extra></extra>'
        ))

        # Add segment overlays
        for start_time, end_time, action in self.segments:
            fig.add_vrect(
                x0=start_time, x1=end_time,
                fillcolor=self._get_action_color(action),
                opacity=0.3,
                layer="below",
                line_width=0,
                annotation_text=action.upper(),
                annotation_position="top left"
            )

        # Configure layout
        fig.update_layout(
            title="Audio Waveform Editor",
            xaxis_title="Time (seconds)",
            yaxis_title="Amplitude",
            height=400,
            dragmode='select',
            showlegend=False
        )

        # Add selection callback
        fig.update_layout(
            selectdirection="h",
            clickmode='event+select'
        )

        # Display the chart and capture selection
        selected_data = st.plotly_chart(fig, width='stretch', key="waveform_chart")
        
        # For now, return None as selection handling needs more complex implementation
        return None

    def _get_action_color(self, action: str) -> str:
        """Get color for different actions."""
        colors = {
            'keep': 'green',
            'remove': 'red',
            'amplify': 'yellow',
            'question': 'purple',
            'fade_in': 'orange',
            'fade_out': 'orange'
        }
        return colors.get(action, 'gray')

    def add_segment(self, start_time: float, end_time: float, action: str):
        """Add a segment with specific action."""
        if start_time < end_time and start_time >= 0 and end_time <= self.duration:
            self.segments.append((start_time, end_time, action))
            self._sort_segments()

    def remove_segment(self, index: int):
        """Remove a segment by index."""
        if 0 <= index < len(self.segments):
            self.segments.pop(index)

    def get_segments(self) -> List[Tuple[float, float, str]]:
        """Get all defined segments."""
        return self.segments.copy()

    def clear_segments(self):
        """Clear all segments."""
        self.segments.clear()

    def _sort_segments(self):
        """Sort segments by start time."""
        self.segments.sort(key=lambda x: x[0])

    def get_audio_info(self) -> dict:
        """Get basic audio information."""
        if len(self.audio_data) == 0:
            return {
                'duration': 0.0,
                'sample_rate': self.sample_rate,
                'samples': 0,
                'channels': 1,
                'max_amplitude': 0.0,
                'rms_level': 0.0
            }
        
        return {
            'duration': self.duration,
            'sample_rate': self.sample_rate,
            'samples': len(self.audio_data),
            'channels': 1 if self.audio_data.ndim == 1 else self.audio_data.shape[1],
            'max_amplitude': float(np.max(np.abs(self.audio_data))),
            'rms_level': float(np.sqrt(np.mean(self.audio_data**2)))
        }

    def render_audio_info(self):
        """Render audio information display."""
        info = self.get_audio_info()
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Duration", f"{info['duration']:.1f}s")
        with col2:
            st.metric("Sample Rate", f"{info['sample_rate']} Hz")
        with col3:
            st.metric("Max Level", f"{info['max_amplitude']:.3f}")
        with col4:
            st.metric("RMS Level", f"{info['rms_level']:.3f}")

    def render_segment_list(self):
        """Render the list of current segments."""
        if not self.segments:
            st.info("No segments defined. Use the editing controls to add segments.")
            return

        st.subheader("Current Segments")
        
        for i, (start, end, action) in enumerate(self.segments):
            col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
            
            with col1:
                st.write(f"**Start:** {start:.1f}s")
            with col2:
                st.write(f"**End:** {end:.1f}s")
            with col3:
                st.write(f"**Action:** {action.title()}")
            with col4:
                if st.button("❌", key=f"remove_segment_{i}", help="Remove segment"):
                    self.remove_segment(i)
                    st.rerun()