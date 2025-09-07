# src/audio/question_processor.py
import numpy as np
from typing import List, Tuple, Dict, Any, Optional
import logging

try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False
    logging.warning("librosa not available - Q&A detection will use simplified methods")

try:
    from scipy.signal import find_peaks
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logging.warning("scipy not available - Q&A detection will use basic methods")

logger = logging.getLogger(__name__)


class QuestionProcessor:
    """Processor for detecting and preserving question segments in audio."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the question processor.
        
        Args:
            config: Configuration dictionary with processing parameters
        """
        self.config = config
        self.sample_rate = config.get('sample_rate', 44100)
        self.question_threshold = config.get('question_threshold', 0.6)
        
        # Detection parameters
        self.min_question_duration = config.get('min_question_duration', 2.0)  # seconds
        self.max_question_duration = config.get('max_question_duration', 30.0)  # seconds
        self.pause_threshold = config.get('pause_threshold', 0.5)  # seconds
        
        logger.info(f"QuestionProcessor initialized with sample_rate={self.sample_rate}")

    def detect_question_segments(self, audio_data: np.ndarray) -> List[Tuple[float, float]]:
        """
        Detect potential question segments in audio.
        
        Args:
            audio_data: Audio signal as numpy array
            
        Returns:
            List of (start_time, end_time) tuples for detected question segments
        """
        # Convert to mono if stereo
        if audio_data.ndim > 1:
            audio_data = np.mean(audio_data, axis=0)
        
        try:
            if LIBROSA_AVAILABLE and SCIPY_AVAILABLE:
                return self._detect_with_librosa(audio_data)
            else:
                return self._detect_basic(audio_data)
        except Exception as e:
            logger.error(f"Error in question detection: {e}")
            return self._detect_basic(audio_data)

    def _detect_with_librosa(self, audio_data: np.ndarray) -> List[Tuple[float, float]]:
        """Detect questions using librosa for advanced audio analysis."""
        # Calculate frame parameters
        frame_length = int(0.025 * self.sample_rate)  # 25ms frames
        hop_length = int(0.010 * self.sample_rate)    # 10ms hop
        
        # Calculate RMS energy
        rms = librosa.feature.rms(y=audio_data, frame_length=frame_length, hop_length=hop_length)[0]
        
        # Find speech segments (peaks in RMS)
        speech_threshold = np.mean(rms) + 0.5 * np.std(rms)
        peaks, properties = find_peaks(rms, height=speech_threshold, 
                                     distance=int(0.5 * self.sample_rate / hop_length))
        
        question_segments = []
        
        for peak in peaks:
            # Convert frame index to time
            peak_time = peak * hop_length / self.sample_rate
            
            # Extract segment for analysis
            segment_start = max(0, peak_time - 1.0)  # 1 second before peak
            segment_end = min(len(audio_data) / self.sample_rate, peak_time + 5.0)  # 5 seconds after
            
            segment = self._extract_segment(audio_data, segment_start, segment_end - segment_start)
            
            if len(segment) > 0 and self._is_question_segment(segment, segment_start):
                # Find precise boundaries
                extended_segment = self._extend_segment(audio_data, peak_time, segment)
                if self._validate_segment_duration(extended_segment):
                    question_segments.append(extended_segment)
        
        # Merge overlapping segments
        return self._merge_overlapping_segments(question_segments)

    def _detect_basic(self, audio_data: np.ndarray) -> List[Tuple[float, float]]:
        """Basic question detection without librosa."""
        # Simple energy-based detection
        window_size = int(0.5 * self.sample_rate)  # 0.5 second windows
        hop_size = int(0.25 * self.sample_rate)    # 0.25 second hops
        
        question_segments = []
        
        for i in range(0, len(audio_data) - window_size, hop_size):
            window = audio_data[i:i + window_size]
            
            # Calculate energy and basic features
            energy = np.mean(window**2)
            zero_crossings = np.sum(np.diff(np.signbit(window)))
            
            # Simple heuristics for question detection
            if self._is_question_basic(window, energy, zero_crossings):
                start_time = i / self.sample_rate
                end_time = (i + window_size) / self.sample_rate
                
                # Extend to find full question
                extended = self._extend_segment_basic(audio_data, start_time, end_time)
                if self._validate_segment_duration(extended):
                    question_segments.append(extended)
        
        return self._merge_overlapping_segments(question_segments)

    def _is_question_segment(self, segment: np.ndarray, start_time: float) -> bool:
        """Determine if a segment contains a question using advanced analysis."""
        if len(segment) == 0:
            return False
        
        # Initialize score
        question_score = 0.0
        
        # Analyze pitch patterns (questions often have rising intonation)
        pitch_score = self._analyze_pitch_trend(segment)
        question_score += pitch_score * 0.4
        
        # Analyze pause patterns (questions often followed by pauses)
        pause_score = self._detect_pauses(segment)
        question_score += pause_score * 0.3
        
        # Analyze energy patterns
        energy_score = self._analyze_energy_pattern(segment)
        question_score += energy_score * 0.2
        
        # Position-based weighting (questions more likely in certain parts)
        position_score = self._analyze_position(start_time)
        question_score += position_score * 0.1
        
        return question_score > self.question_threshold

    def _is_question_basic(self, segment: np.ndarray, energy: float, zero_crossings: int) -> bool:
        """Basic question detection using simple features."""
        # Normalize features
        avg_energy = np.mean(segment**2)
        energy_ratio = energy / (avg_energy + 1e-8)
        
        # Basic heuristics
        has_sufficient_energy = energy > 0.01
        has_speech_characteristics = zero_crossings > 50  # Indicates voice activity
        energy_consistent = energy_ratio > 0.5
        
        return has_sufficient_energy and has_speech_characteristics and energy_consistent

    def _analyze_pitch_trend(self, segment: np.ndarray) -> float:
        """Analyze pitch trend for rising intonation."""
        if not LIBROSA_AVAILABLE:
            return 0.5  # Default neutral score
        
        try:
            # Extract pitch using librosa
            pitches, magnitudes = librosa.piptrack(y=segment, sr=self.sample_rate, 
                                                  threshold=0.1, fmin=75, fmax=400)
            
            # Get dominant pitch over time
            dominant_pitches = []
            for i in range(pitches.shape[1]):
                pitch_frame = pitches[:, i]
                mag_frame = magnitudes[:, i]
                
                if np.max(mag_frame) > 0.1:
                    dominant_pitch = pitch_frame[np.argmax(mag_frame)]
                    if dominant_pitch > 75:  # Filter out noise
                        dominant_pitches.append(dominant_pitch)
            
            if len(dominant_pitches) < 5:
                return 0.3  # Insufficient data
            
            # Calculate trend (rising = positive slope)
            x = np.arange(len(dominant_pitches))
            slope = np.polyfit(x, dominant_pitches, 1)[0]
            
            # Normalize to 0-1 scale
            return max(0, min(1, (slope + 50) / 100))
            
        except Exception:
            return 0.5  # Default if analysis fails

    def _detect_pauses(self, segment: np.ndarray) -> float:
        """Detect pauses that often follow questions."""
        # Calculate short-term energy
        frame_length = int(0.020 * self.sample_rate)  # 20ms frames
        hop_length = int(0.010 * self.sample_rate)    # 10ms hop
        
        if LIBROSA_AVAILABLE:
            try:
                rms = librosa.feature.rms(y=segment, frame_length=frame_length, hop_length=hop_length)[0]
            except Exception:
                # Fallback to manual calculation
                rms = self._calculate_rms_manual(segment, frame_length, hop_length)
        else:
            rms = self._calculate_rms_manual(segment, frame_length, hop_length)
        
        # Find low-energy regions (pauses)
        threshold = np.mean(rms) * 0.3
        pause_frames = np.sum(rms < threshold)
        
        return min(1.0, pause_frames / len(rms))

    def _calculate_rms_manual(self, audio_data: np.ndarray, frame_length: int, hop_length: int) -> np.ndarray:
        """Manually calculate RMS energy when librosa is not available."""
        rms_values = []
        for i in range(0, len(audio_data) - frame_length, hop_length):
            frame = audio_data[i:i + frame_length]
            rms = np.sqrt(np.mean(frame**2))
            rms_values.append(rms)
        return np.array(rms_values)

    def _analyze_energy_pattern(self, segment: np.ndarray) -> float:
        """Analyze energy patterns typical of questions."""
        # Questions often have variable energy (rises and falls)
        rms = self._calculate_rms_manual(segment, int(0.05 * self.sample_rate), int(0.025 * self.sample_rate))
        
        if len(rms) < 5:
            return 0.3
        
        # Calculate energy variability
        energy_std = np.std(rms)
        energy_mean = np.mean(rms)
        
        if energy_mean > 0:
            variability = energy_std / energy_mean
            return min(1.0, variability * 2)  # Normalize
        
        return 0.3

    def _analyze_position(self, start_time: float) -> float:
        """Analyze position-based likelihood of questions."""
        # Questions more likely in Q&A sessions (typically later in recordings)
        # This is a simple heuristic
        if start_time > 1800:  # After 30 minutes
            return 0.8
        elif start_time > 900:  # After 15 minutes
            return 0.6
        else:
            return 0.4

    def _extract_segment(self, audio_data: np.ndarray, start_time: float, duration: float) -> np.ndarray:
        """Extract audio segment."""
        start_sample = int(start_time * self.sample_rate)
        end_sample = int((start_time + duration) * self.sample_rate)
        
        start_sample = max(0, start_sample)
        end_sample = min(len(audio_data), end_sample)
        
        if start_sample >= end_sample:
            return np.array([])
        
        return audio_data[start_sample:end_sample]

    def _extend_segment(self, audio_data: np.ndarray, center_time: float, segment: np.ndarray) -> Tuple[float, float]:
        """Extend segment to include full question context."""
        center_sample = int(center_time * self.sample_rate)
        
        # Extend backward to find start of question
        extended_start = self._find_segment_start(audio_data, center_sample)
        
        # Extend forward to find end of question
        extended_end = self._find_segment_end(audio_data, center_sample)
        
        return (extended_start / self.sample_rate, extended_end / self.sample_rate)

    def _extend_segment_basic(self, audio_data: np.ndarray, start_time: float, end_time: float) -> Tuple[float, float]:
        """Basic segment extension without advanced analysis."""
        # Simple extension based on energy
        start_sample = int(start_time * self.sample_rate)
        end_sample = int(end_time * self.sample_rate)
        
        # Extend by fixed amounts
        extended_start = max(0, start_sample - int(1.0 * self.sample_rate))
        extended_end = min(len(audio_data), end_sample + int(2.0 * self.sample_rate))
        
        return (extended_start / self.sample_rate, extended_end / self.sample_rate)

    def _find_segment_start(self, audio_data: np.ndarray, current_pos: int) -> int:
        """Find the start of a speech segment."""
        window_size = int(0.1 * self.sample_rate)  # 100ms window
        threshold = np.mean(np.abs(audio_data)) * 0.3
        
        for i in range(current_pos, max(0, current_pos - int(3 * self.sample_rate)), -window_size):
            if i - window_size < 0:
                return 0
                
            window = audio_data[i - window_size:i]
            if np.mean(np.abs(window)) < threshold:
                return i
        
        return max(0, current_pos - int(2 * self.sample_rate))

    def _find_segment_end(self, audio_data: np.ndarray, current_pos: int) -> int:
        """Find the end of a speech segment."""
        window_size = int(0.1 * self.sample_rate)  # 100ms window
        threshold = np.mean(np.abs(audio_data)) * 0.3
        
        for i in range(current_pos, min(len(audio_data), current_pos + int(5 * self.sample_rate)), window_size):
            if i + window_size > len(audio_data):
                return len(audio_data)
                
            window = audio_data[i:i + window_size]
            if np.mean(np.abs(window)) < threshold:
                return i
        
        return min(len(audio_data), current_pos + int(3 * self.sample_rate))

    def _validate_segment_duration(self, segment: Tuple[float, float]) -> bool:
        """Validate that segment duration is within acceptable range."""
        duration = segment[1] - segment[0]
        return self.min_question_duration <= duration <= self.max_question_duration

    def _merge_overlapping_segments(self, segments: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        """Merge overlapping segments."""
        if not segments:
            return []
        
        # Sort by start time
        segments = sorted(segments, key=lambda x: x[0])
        
        merged = [segments[0]]
        
        for current in segments[1:]:
            last = merged[-1]
            
            # Check for overlap (with small buffer)
            if current[0] <= last[1] + 0.5:  # 0.5 second buffer
                # Merge segments
                merged[-1] = (last[0], max(last[1], current[1]))
            else:
                merged.append(current)
        
        return merged

    def get_processing_recommendations(self, segments: List[Tuple[float, float]]) -> Dict[str, Any]:
        """
        Get processing recommendations based on detected question segments.
        
        Args:
            segments: List of question segments
            
        Returns:
            Dictionary with processing recommendations
        """
        if not segments:
            return {
                'has_questions': False,
                'recommended_mode': 'standard',
                'noise_reduction_strength': 0.6,
                'question_preservation': False
            }
        
        total_question_time = sum(end - start for start, end in segments)
        question_ratio = total_question_time / (len(segments) * 60)  # Rough estimate
        
        if question_ratio > 0.2:  # More than 20% questions
            return {
                'has_questions': True,
                'recommended_mode': 'question_heavy',
                'noise_reduction_strength': 0.3,
                'question_preservation': True,
                'amplify_questions': True
            }
        elif question_ratio > 0.1:  # 10-20% questions
            return {
                'has_questions': True,
                'recommended_mode': 'question_moderate',
                'noise_reduction_strength': 0.4,
                'question_preservation': True,
                'amplify_questions': False
            }
        else:
            return {
                'has_questions': True,
                'recommended_mode': 'question_light',
                'noise_reduction_strength': 0.5,
                'question_preservation': True,
                'amplify_questions': False
            }