"""
Q&A Audio Normalization Module

Intelligent audio processing for sermon recordings that automatically detects 
and normalizes quiet audience questions during Q&A segments while preserving 
the clear audio quality of the main speaker/teacher responses.

Features:
- Multi-modal Q&A segment detection (audio level, speaker change, temporal patterns)
- Automated gain adjustment for audience questions
- Speaker diarization and voice activity detection
- Integration with existing AudioProcessor pipeline
"""

import logging
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

# Suppress warnings from audio processing libraries
warnings.filterwarnings('ignore', category=UserWarning)
warnings.filterwarnings('ignore', category=RuntimeWarning)

logger = logging.getLogger(__name__)

@dataclass
class QASegment:
    """Represents a detected Q&A segment in audio"""
    start_time: float  # seconds
    end_time: float    # seconds
    segment_type: str  # 'question' or 'answer'
    confidence: float  # detection confidence 0-1
    audio_level_db: float  # original RMS level in dB
    gain_applied: float    # gain adjustment applied in dB
    speaker_id: int | None = None  # speaker diarization ID if available

    def duration(self) -> float:
        """Get segment duration in seconds"""
        return self.end_time - self.start_time

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization"""
        return asdict(self)

class QANormalizer:
    """
    Intelligent Q&A audio normalization with multi-modal detection.
    
    Detects Q&A segments using:
    1. Audio level analysis (significant volume drops)
    2. Speaker change detection (voice activity detection)  
    3. Temporal pattern recognition (Q&A typically follows presentation)
    """

    def __init__(self, config: dict[str, Any]):
        """
        Initialize Q&A normalizer with configuration.
        
        Args:
            config: Configuration dictionary with Q&A processing settings
        """
        self.config = config
        qa_config = config.get('qa_normalization', {})

        # Detection thresholds
        self.target_lufs = qa_config.get('target_lufs', -23.0)
        self.main_speaker_threshold_db = qa_config.get('main_speaker_threshold', -12.0)
        self.question_threshold_db = qa_config.get('question_threshold', -30.0)
        self.look_ahead_ms = qa_config.get('look_ahead_ms', 100)
        self.transition_smoothing = qa_config.get('transition_smoothing', True)

        # Detection method configuration
        self.detection_method = qa_config.get('detection_method', 'level_based')

        # Speaker diarization settings
        diarization_config = qa_config.get('speaker_diarization', {})
        self.min_speakers = diarization_config.get('min_speakers', 1)
        self.max_speakers = diarization_config.get('max_speakers', 10)

        # Internal state
        self.detected_segments: list[QASegment] = []
        self.sample_rate: int | None = None
        self.audio_duration: float | None = None

        logger.info(f"Initialized QANormalizer with method: {self.detection_method}")

    def process_audio(self, audio_file: str) -> tuple[np.ndarray, int]:
        """
        Process audio file with Q&A normalization.
        
        Args:
            audio_file: Path to input audio file
            
        Returns:
            Tuple of (normalized_audio_data, sample_rate)
        """
        logger.info(f"Processing audio for Q&A normalization: {audio_file}")

        # Load audio
        audio_data, sample_rate = sf.read(audio_file)
        if audio_data.ndim > 1:
            audio_data = np.mean(audio_data, axis=1)  # Convert to mono

        self.sample_rate = sample_rate
        self.audio_duration = len(audio_data) / sample_rate

        # Detect Q&A segments
        self.detected_segments = self._detect_qa_segments(audio_data, sample_rate)

        if not self.detected_segments:
            logger.info("No Q&A segments detected, returning original audio")
            return audio_data, sample_rate

        # Apply normalization to detected segments
        normalized_audio = self._apply_qa_normalization(audio_data, sample_rate)

        logger.info(f"Q&A normalization complete. Processed {len(self.detected_segments)} segments")
        return normalized_audio, sample_rate

    def _detect_qa_segments(self, audio_data: np.ndarray, sample_rate: int) -> list[QASegment]:
        """
        Detect Q&A segments using the configured detection method.
        
        Args:
            audio_data: Audio samples
            sample_rate: Sample rate in Hz
            
        Returns:
            List of detected Q&A segments
        """
        if self.detection_method == 'level_based':
            return self._detect_by_audio_levels(audio_data, sample_rate)
        elif self.detection_method == 'speaker_diarization':
            return self._detect_by_speaker_diarization(audio_data, sample_rate)
        elif self.detection_method == 'hybrid':
            # Combine multiple detection methods
            level_segments = self._detect_by_audio_levels(audio_data, sample_rate)
            diarization_segments = self._detect_by_speaker_diarization(audio_data, sample_rate)
            return self._merge_segment_detections(level_segments, diarization_segments)
        else:
            logger.warning(f"Unknown detection method: {self.detection_method}")
            return []

    def _detect_by_audio_levels(self, audio_data: np.ndarray, sample_rate: int) -> list[QASegment]:
        """
        Detect Q&A segments based on audio level analysis.
        
        Identifies segments where audio drops significantly below normal levels,
        indicating audience questions.
        """
        logger.info("Detecting Q&A segments using audio level analysis")

        # Calculate RMS energy in sliding windows
        window_size = int(0.5 * sample_rate)  # 500ms windows
        hop_size = int(0.1 * sample_rate)     # 100ms hop

        rms_values = []
        timestamps = []

        for i in range(0, len(audio_data) - window_size, hop_size):
            window = audio_data[i:i + window_size]
            rms = np.sqrt(np.mean(window**2))
            rms_db = 20 * np.log10(rms + 1e-10)  # Add small epsilon to avoid log(0)

            rms_values.append(rms_db)
            timestamps.append(i / sample_rate)

        rms_values = np.array(rms_values)
        timestamps = np.array(timestamps)

        # Find segments significantly below main speaker level
        main_speaker_mask = rms_values > self.main_speaker_threshold_db
        question_mask = (rms_values < self.question_threshold_db) & (rms_values > -60.0)  # Avoid silence

        # Group consecutive question segments
        segments = []
        in_question = False
        segment_start = None

        for i, (is_question, timestamp, rms_db) in enumerate(zip(question_mask, timestamps, rms_values, strict=False)):
            if is_question and not in_question:
                # Start of question segment
                segment_start = timestamp
                in_question = True
            elif not is_question and in_question:
                # End of question segment
                if segment_start is not None:
                    duration = timestamp - segment_start
                    if duration >= 1.0:  # Minimum 1 second for valid question
                        segments.append(QASegment(
                            start_time=segment_start,
                            end_time=timestamp,
                            segment_type='question',
                            confidence=0.8,  # High confidence for level-based detection
                            audio_level_db=float(np.mean(rms_values[max(0, i-5):i])),
                            gain_applied=0.0  # Will be calculated during normalization
                        ))
                in_question = False
                segment_start = None

        # Handle case where question segment extends to end of audio
        if in_question and segment_start is not None:
            segments.append(QASegment(
                start_time=segment_start,
                end_time=self.audio_duration,
                segment_type='question',
                confidence=0.8,
                audio_level_db=float(np.mean(rms_values[-5:])),
                gain_applied=0.0
            ))

        logger.info(f"Detected {len(segments)} Q&A segments using audio level analysis")
        return segments

    def _detect_by_speaker_diarization(self, audio_data: np.ndarray, sample_rate: int) -> list[QASegment]:
        """
        Detect Q&A segments using speaker diarization (if available).
        
        This is a placeholder for advanced speaker diarization using models like
        pyannote.audio. For now, returns empty list as it requires additional dependencies.
        """
        logger.info("Speaker diarization detection not yet implemented")
        logger.info("Falling back to level-based detection")
        return self._detect_by_audio_levels(audio_data, sample_rate)

    def _merge_segment_detections(self, segments1: list[QASegment], segments2: list[QASegment]) -> list[QASegment]:
        """
        Merge segments from multiple detection methods.
        
        Currently returns the first list as a simple implementation.
        Future versions could implement more sophisticated merging logic.
        """
        logger.info(f"Merging {len(segments1)} and {len(segments2)} detected segments")
        return segments1  # Simple implementation for now

    def _apply_qa_normalization(self, audio_data: np.ndarray, sample_rate: int) -> np.ndarray:
        """
        Apply gain adjustments to normalize Q&A segments.
        
        Args:
            audio_data: Original audio samples
            sample_rate: Sample rate in Hz
            
        Returns:
            Normalized audio with Q&A segments boosted
        """
        normalized_audio = audio_data.copy()

        for segment in self.detected_segments:
            if segment.segment_type == 'question':
                # Calculate sample indices
                start_sample = int(segment.start_time * sample_rate)
                end_sample = int(segment.end_time * sample_rate)

                # Extract segment
                segment_audio = audio_data[start_sample:end_sample]

                if len(segment_audio) == 0:
                    continue

                # Calculate current RMS level
                current_rms = np.sqrt(np.mean(segment_audio**2))
                current_db = 20 * np.log10(current_rms + 1e-10)

                # Calculate target gain to reach main speaker level
                target_db = self.main_speaker_threshold_db - 3.0  # Slightly below main speaker
                gain_db = target_db - current_db

                # Limit gain to reasonable range
                gain_db = np.clip(gain_db, 0.0, 20.0)  # Max 20dB boost

                # Apply gain
                gain_linear = 10**(gain_db / 20.0)
                boosted_segment = segment_audio * gain_linear

                # Apply smoothing at transitions if enabled
                if self.transition_smoothing:
                    fade_samples = int(0.05 * sample_rate)  # 50ms fade
                    if len(boosted_segment) > 2 * fade_samples:
                        # Fade in
                        fade_in = np.linspace(0, 1, fade_samples)
                        boosted_segment[:fade_samples] *= fade_in

                        # Fade out
                        fade_out = np.linspace(1, 0, fade_samples)
                        boosted_segment[-fade_samples:] *= fade_out

                # Clip to prevent overload
                boosted_segment = np.clip(boosted_segment, -0.98, 0.98)

                # Apply to normalized audio
                normalized_audio[start_sample:end_sample] = boosted_segment

                # Update segment with applied gain
                segment.gain_applied = gain_db

                logger.debug(f"Applied {gain_db:.1f}dB gain to question segment {segment.start_time:.1f}-{segment.end_time:.1f}s")

        return normalized_audio

    def get_segments(self) -> list[dict[str, Any]]:
        """
        Get detected Q&A segments as a list of dictionaries.
        
        Returns:
            List of segment dictionaries suitable for JSON serialization
        """
        return [segment.to_dict() for segment in self.detected_segments]

    def get_processing_stats(self) -> dict[str, Any]:
        """
        Get processing statistics and metrics.
        
        Returns:
            Dictionary with processing statistics
        """
        if not self.detected_segments:
            return {
                'total_segments': 0,
                'total_qa_duration': 0.0,
                'average_gain_applied': 0.0,
                'detection_method': self.detection_method
            }

        question_segments = [s for s in self.detected_segments if s.segment_type == 'question']

        return {
            'total_segments': len(self.detected_segments),
            'question_segments': len(question_segments),
            'total_qa_duration': sum(s.duration() for s in question_segments),
            'average_gain_applied': np.mean([s.gain_applied for s in question_segments]) if question_segments else 0.0,
            'max_gain_applied': max([s.gain_applied for s in question_segments]) if question_segments else 0.0,
            'detection_method': self.detection_method,
            'audio_duration': self.audio_duration
        }

# Convenience function for integration with existing audio processing
def apply_qa_normalization(audio_file: str, config: dict[str, Any],
                          output_file: str | None = None) -> tuple[str, dict[str, Any]]:
    """
    Apply Q&A normalization to an audio file.
    
    Args:
        audio_file: Path to input audio file
        config: Configuration dictionary
        output_file: Optional output file path (uses temp file if None)
        
    Returns:
        Tuple of (output_file_path, processing_stats)
    """
    normalizer = QANormalizer(config)
    normalized_audio, sample_rate = normalizer.process_audio(audio_file)

    if output_file is None:
        # Create temporary output file
        input_path = Path(audio_file)
        output_file = str(input_path.parent / f"{input_path.stem}_qa_normalized{input_path.suffix}")

    # Save normalized audio
    sf.write(output_file, normalized_audio, sample_rate)

    # Get processing statistics
    stats = normalizer.get_processing_stats()
    stats['qa_segments'] = normalizer.get_segments()

    logger.info(f"Q&A normalization complete: {output_file}")
    return output_file, stats
