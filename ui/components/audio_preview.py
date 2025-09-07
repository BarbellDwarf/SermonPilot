# ui/components/audio_preview.py
import streamlit as st
from typing import Optional, Dict, Any
import tempfile
import os
from pathlib import Path
import base64
import numpy as np


class AudioPreview:
    """Audio preview component for playing and comparing audio."""
    
    def __init__(self):
        """Initialize the audio preview system."""
        self.temp_files = []
        
        # Ensure temp directory exists
        self.temp_dir = Path(tempfile.gettempdir()) / "sermon_audio_preview"
        self.temp_dir.mkdir(exist_ok=True)

    def render_preview_controls(self) -> Dict[str, Any]:
        """
        Render audio preview controls.
        
        Returns:
            Dictionary containing preview actions and settings
        """
        st.subheader("🔊 Audio Preview")

        # Preview action buttons
        col1, col2, col3, col4 = st.columns(4)

        controls = {}

        with col1:
            if st.button("▶️ Play Original", help="Play original audio"):
                controls['action'] = 'play_original'

        with col2:
            if st.button("▶️ Play Edited", help="Play edited audio"):
                controls['action'] = 'play_edited'

        with col3:
            if st.button("🔄 Compare A/B", help="Toggle between original and edited"):
                controls['action'] = 'compare'

        with col4:
            if st.button("🔄 Reset Edits", help="Clear all edits"):
                controls['action'] = 'reset'

        # Preview settings
        with st.expander("Preview Settings"):
            controls['preview_volume'] = st.slider(
                "Preview Volume", 
                0.0, 1.0, 0.7,
                step=0.1,
                help="Adjust volume for preview playback"
            )
            
            controls['preview_region'] = st.checkbox(
                "Preview Selected Region Only",
                value=False,
                help="Only play the currently selected region"
            )
            
            if controls['preview_region']:
                col1, col2 = st.columns(2)
                with col1:
                    controls['region_start'] = st.number_input(
                        "Start (seconds)", min_value=0.0, value=0.0, step=0.1
                    )
                with col2:
                    controls['region_end'] = st.number_input(
                        "End (seconds)", min_value=0.0, value=10.0, step=0.1
                    )

        return controls

    def create_preview_audio(self, audio_data: np.ndarray, sample_rate: int,
                           file_format: str = "wav", volume: float = 1.0) -> Optional[str]:
        """
        Create temporary audio file for preview.
        
        Args:
            audio_data: Audio data as numpy array
            sample_rate: Sample rate
            file_format: Output format ('wav', 'mp3')
            volume: Volume adjustment (0.0 to 1.0)
            
        Returns:
            Path to temporary audio file or None if failed
        """
        try:
            # Import pydub here to avoid issues if not available
            from pydub import AudioSegment
            
            # Apply volume adjustment
            adjusted_audio = audio_data * volume
            
            # Ensure audio is in valid range
            adjusted_audio = np.clip(adjusted_audio, -1.0, 1.0)
            
            # Convert to 16-bit integers
            audio_int16 = (adjusted_audio * 32767).astype(np.int16)
            
            # Create AudioSegment
            audio_segment = AudioSegment(
                audio_int16.tobytes(),
                frame_rate=sample_rate,
                sample_width=2,  # 16-bit
                channels=1
            )

            # Create temporary file
            temp_file = self.temp_dir / f"preview_{len(self.temp_files)}.{file_format}"
            audio_segment.export(str(temp_file), format=file_format)
            
            self.temp_files.append(str(temp_file))
            return str(temp_file)

        except Exception as e:
            st.error(f"Failed to create preview: {e}")
            return None

    def extract_region(self, audio_data: np.ndarray, sample_rate: int,
                      start_time: float, end_time: float) -> np.ndarray:
        """
        Extract a specific region from audio data.
        
        Args:
            audio_data: Full audio data
            sample_rate: Sample rate
            start_time: Start time in seconds
            end_time: End time in seconds
            
        Returns:
            Extracted audio region
        """
        start_sample = int(start_time * sample_rate)
        end_sample = int(end_time * sample_rate)
        
        # Validate bounds
        start_sample = max(0, start_sample)
        end_sample = min(len(audio_data), end_sample)
        
        if start_sample >= end_sample:
            return np.array([])
        
        return audio_data[start_sample:end_sample]

    def render_audio_player(self, audio_file_path: str, label: str = "Audio"):
        """
        Render HTML audio player for the given file.
        
        Args:
            audio_file_path: Path to audio file
            label: Label for the audio player
        """
        if not os.path.exists(audio_file_path):
            st.error(f"Audio file not found: {audio_file_path}")
            return

        try:
            # Read file and encode as base64
            with open(audio_file_path, "rb") as f:
                audio_bytes = f.read()

            audio_base64 = base64.b64encode(audio_bytes).decode()
            
            # Determine MIME type based on file extension
            ext = Path(audio_file_path).suffix.lower()
            mime_type = {
                '.wav': 'audio/wav',
                '.mp3': 'audio/mp3',
                '.m4a': 'audio/mp4',
                '.flac': 'audio/flac'
            }.get(ext, 'audio/wav')

            # Create HTML audio player
            audio_html = f"""
            <div style="margin: 10px 0;">
                <p><strong>{label}</strong></p>
                <audio controls style="width: 100%;">
                    <source src="data:{mime_type};base64,{audio_base64}" type="{mime_type}">
                    Your browser does not support the audio element.
                </audio>
            </div>
            """

            st.markdown(audio_html, unsafe_allow_html=True)
            
        except Exception as e:
            st.error(f"Failed to load audio player: {e}")

    def render_comparison_player(self, original_path: str, edited_path: str):
        """
        Render side-by-side comparison audio players.
        
        Args:
            original_path: Path to original audio file
            edited_path: Path to edited audio file
        """
        st.subheader("Audio Comparison")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Original Audio**")
            self.render_audio_player(original_path, "Original")
            
        with col2:
            st.markdown("**Edited Audio**")
            self.render_audio_player(edited_path, "Edited")

    def create_preview_with_edits(self, original_audio: np.ndarray, sample_rate: int,
                                 segments: list, volume: float = 1.0) -> Optional[str]:
        """
        Create preview with all edits applied.
        
        Args:
            original_audio: Original audio data
            sample_rate: Sample rate
            segments: List of (start, end, action) tuples
            volume: Preview volume
            
        Returns:
            Path to processed preview file
        """
        try:
            # Apply edits in order
            edited_audio = original_audio.copy()
            
            # Sort segments by start time
            sorted_segments = sorted(segments, key=lambda x: x[0])
            
            # Apply each edit (simplified version)
            for start_time, end_time, action in sorted_segments:
                start_sample = int(start_time * sample_rate)
                end_sample = int(end_time * sample_rate)
                
                # Validate bounds
                start_sample = max(0, start_sample)
                end_sample = min(len(edited_audio), end_sample)
                
                if start_sample >= end_sample:
                    continue
                
                if action == "remove":
                    edited_audio = np.concatenate([
                        edited_audio[:start_sample],
                        edited_audio[end_sample:]
                    ])
                elif action == "amplify":
                    boost_factor = 10 ** (3.0 / 20)  # 3dB boost
                    edited_audio[start_sample:end_sample] *= boost_factor
                    edited_audio = np.clip(edited_audio, -1.0, 1.0)
            
            return self.create_preview_audio(edited_audio, sample_rate, volume=volume)
            
        except Exception as e:
            st.error(f"Failed to create edited preview: {e}")
            return None

    def get_audio_statistics(self, audio_data: np.ndarray) -> Dict[str, float]:
        """
        Get basic statistics about audio data.
        
        Args:
            audio_data: Audio data
            
        Returns:
            Dictionary of statistics
        """
        return {
            'max_amplitude': float(np.max(np.abs(audio_data))),
            'rms_level': float(np.sqrt(np.mean(audio_data**2))),
            'peak_to_rms_ratio': float(np.max(np.abs(audio_data)) / np.sqrt(np.mean(audio_data**2))),
            'dynamic_range': float(np.max(audio_data) - np.min(audio_data)),
            'zero_crossings': int(np.sum(np.diff(np.signbit(audio_data))))
        }

    def render_audio_statistics(self, original_audio: np.ndarray, edited_audio: Optional[np.ndarray] = None):
        """
        Render comparison of audio statistics.
        
        Args:
            original_audio: Original audio data
            edited_audio: Edited audio data (optional)
        """
        st.subheader("Audio Analysis")
        
        original_stats = self.get_audio_statistics(original_audio)
        
        if edited_audio is not None:
            edited_stats = self.get_audio_statistics(edited_audio)
            
            # Comparison table
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("**Metric**")
                st.write("Max Amplitude")
                st.write("RMS Level")
                st.write("Peak-to-RMS Ratio")
                st.write("Dynamic Range")
                
            with col2:
                st.markdown("**Original**")
                st.write(f"{original_stats['max_amplitude']:.3f}")
                st.write(f"{original_stats['rms_level']:.3f}")
                st.write(f"{original_stats['peak_to_rms_ratio']:.2f}")
                st.write(f"{original_stats['dynamic_range']:.3f}")
                
            with col3:
                st.markdown("**Edited**")
                st.write(f"{edited_stats['max_amplitude']:.3f}")
                st.write(f"{edited_stats['rms_level']:.3f}")
                st.write(f"{edited_stats['peak_to_rms_ratio']:.2f}")
                st.write(f"{edited_stats['dynamic_range']:.3f}")
        else:
            # Single column for original only
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric("Max Amplitude", f"{original_stats['max_amplitude']:.3f}")
                st.metric("RMS Level", f"{original_stats['rms_level']:.3f}")
                
            with col2:
                st.metric("Peak-to-RMS Ratio", f"{original_stats['peak_to_rms_ratio']:.2f}")
                st.metric("Dynamic Range", f"{original_stats['dynamic_range']:.3f}")

    def cleanup_temp_files(self):
        """Clean up temporary audio files."""
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except Exception:
                pass  # Ignore cleanup errors
        self.temp_files.clear()

    def __del__(self):
        """Cleanup when object is destroyed."""
        self.cleanup_temp_files()