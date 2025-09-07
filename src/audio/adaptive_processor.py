# src/audio/adaptive_processor.py
import numpy as np
from typing import Dict, Any, List, Tuple, Optional
import logging

try:
    from scipy.signal import butter, filtfilt, savgol_filter
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logging.warning("scipy not available - adaptive processing will use basic methods")

logger = logging.getLogger(__name__)


class AdaptiveAudioProcessor:
    """Advanced audio processor that adapts to content type, especially Q&A segments."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the adaptive processor.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.sample_rate = config.get('sample_rate', 44100)
        self.question_segments = []
        
        # Processing parameters
        self.gentle_noise_reduction = config.get('gentle_noise_reduction', 0.3)
        self.standard_noise_reduction = config.get('standard_noise_reduction', 0.6)
        self.question_amplification = config.get('question_amplification_db', 2.0)
        
        logger.info(f"AdaptiveAudioProcessor initialized with sample_rate={self.sample_rate}")

    def process_with_question_preservation(self, audio_data: np.ndarray,
                                         question_segments: List[Tuple[float, float]]) -> np.ndarray:
        """
        Process audio while preserving question segments.
        
        Args:
            audio_data: Input audio data
            question_segments: List of (start_time, end_time) for question segments
            
        Returns:
            Processed audio data
        """
        self.question_segments = question_segments
        
        logger.info(f"Processing audio with {len(question_segments)} question segments")
        
        # Create working copy
        processed_audio = audio_data.copy()
        
        # Step 1: Apply adaptive noise reduction
        processed_audio = self._apply_adaptive_noise_reduction(processed_audio)
        
        # Step 2: Enhance question segments
        processed_audio = self._enhance_question_segments(processed_audio)
        
        # Step 3: Apply adaptive normalization
        processed_audio = self._apply_adaptive_normalization(processed_audio)
        
        # Step 4: Apply final smoothing
        processed_audio = self._apply_final_smoothing(processed_audio)
        
        return processed_audio

    def _apply_adaptive_noise_reduction(self, audio_data: np.ndarray) -> np.ndarray:
        """Apply noise reduction that's less aggressive near questions."""
        processed = audio_data.copy()
        
        # Create processing mask
        question_mask = self._create_question_mask(len(processed))
        question_buffer_mask = self._create_question_buffer_mask(len(processed))
        
        # Apply different levels of noise reduction
        # 1. Gentle reduction around questions (includes buffer zones)
        gentle_mask = question_buffer_mask
        processed[gentle_mask] = self._gentle_noise_reduction(processed[gentle_mask])
        
        # 2. Standard reduction for non-question areas
        standard_mask = ~question_buffer_mask
        if np.any(standard_mask):
            processed[standard_mask] = self._standard_noise_reduction(processed[standard_mask])
        
        logger.debug(f"Applied adaptive noise reduction: {np.sum(gentle_mask)} gentle samples, "
                    f"{np.sum(standard_mask)} standard samples")
        
        return processed

    def _gentle_noise_reduction(self, audio_segment: np.ndarray) -> np.ndarray:
        """Apply gentle noise reduction for question segments."""
        if len(audio_segment) == 0:
            return audio_segment
        
        # Use lighter noise reduction
        reduction_factor = self.gentle_noise_reduction
        
        # Simple spectral subtraction approach
        # Calculate noise floor
        noise_floor = np.percentile(np.abs(audio_segment), 10)  # Bottom 10% as noise estimate
        
        # Apply gentle noise gate
        threshold = noise_floor * 3  # Conservative threshold
        mask = np.abs(audio_segment) < threshold
        
        # Gentle attenuation of low-level signals
        audio_segment = audio_segment.copy()
        audio_segment[mask] *= (1 - reduction_factor)
        
        return audio_segment

    def _standard_noise_reduction(self, audio_segment: np.ndarray) -> np.ndarray:
        """Apply standard noise reduction for non-question segments."""
        if len(audio_segment) == 0:
            return audio_segment
        
        # More aggressive noise reduction
        reduction_factor = self.standard_noise_reduction
        
        # Calculate noise floor
        noise_floor = np.percentile(np.abs(audio_segment), 15)  # Bottom 15% as noise estimate
        
        # Apply noise gate
        threshold = noise_floor * 2  # More aggressive threshold
        mask = np.abs(audio_segment) < threshold
        
        # Standard attenuation
        audio_segment = audio_segment.copy()
        audio_segment[mask] *= (1 - reduction_factor)
        
        # Additional high-frequency noise reduction if scipy is available
        if SCIPY_AVAILABLE and len(audio_segment) > 100:
            audio_segment = self._apply_spectral_smoothing(audio_segment)
        
        return audio_segment

    def _apply_spectral_smoothing(self, audio_segment: np.ndarray) -> np.ndarray:
        """Apply spectral smoothing to reduce high-frequency noise."""
        try:
            # Design a gentle low-pass filter
            nyquist = self.sample_rate / 2
            cutoff = min(8000, nyquist * 0.8)  # Cutoff at 8kHz or 80% of Nyquist
            
            # Butterworth filter (gentle rolloff)
            b, a = butter(2, cutoff / nyquist, btype='low')
            
            # Apply filter
            return filtfilt(b, a, audio_segment)
        except Exception as e:
            logger.warning(f"Spectral smoothing failed: {e}")
            return audio_segment

    def _enhance_question_segments(self, audio_data: np.ndarray) -> np.ndarray:
        """Apply enhancement specifically to question segments."""
        enhanced = audio_data.copy()
        
        for start_time, end_time in self.question_segments:
            start_sample = int(start_time * self.sample_rate)
            end_sample = int(end_time * self.sample_rate)
            
            # Validate bounds
            start_sample = max(0, start_sample)
            end_sample = min(len(enhanced), end_sample)
            
            if start_sample >= end_sample:
                continue
            
            segment = enhanced[start_sample:end_sample]
            
            # Apply gentle amplification
            segment = self._amplify_segment(segment, self.question_amplification)
            
            # Apply clarity enhancement
            segment = self._apply_clarity_enhancement(segment)
            
            # Apply gentle compression to maintain dynamics
            segment = self._apply_gentle_compression(segment)
            
            enhanced[start_sample:end_sample] = segment
        
        return enhanced

    def _amplify_segment(self, segment: np.ndarray, boost_db: float) -> np.ndarray:
        """Amplify audio segment with clipping protection."""
        if len(segment) == 0:
            return segment
        
        boost_factor = 10 ** (boost_db / 20)
        amplified = segment * boost_factor
        
        # Soft clipping to prevent distortion
        return self._soft_clip(amplified)

    def _soft_clip(self, audio_data: np.ndarray, threshold: float = 0.95) -> np.ndarray:
        """Apply soft clipping to prevent distortion."""
        # Tanh-based soft clipping
        clipped = np.tanh(audio_data / threshold) * threshold
        return clipped

    def _apply_clarity_enhancement(self, segment: np.ndarray) -> np.ndarray:
        """Apply subtle clarity enhancement for speech."""
        if not SCIPY_AVAILABLE or len(segment) < 100:
            return segment
        
        try:
            # Gentle high-frequency emphasis (speech clarity)
            nyquist = self.sample_rate / 2
            
            # Design a gentle high-shelf filter around 2-4 kHz (speech clarity range)
            cutoff = min(3000, nyquist * 0.5)
            b, a = butter(1, cutoff / nyquist, btype='high')
            
            # Apply gentle emphasis
            emphasis = filtfilt(b, a, segment) * 0.1  # Very gentle
            enhanced = segment + emphasis
            
            return self._soft_clip(enhanced)
        except Exception as e:
            logger.warning(f"Clarity enhancement failed: {e}")
            return segment

    def _apply_gentle_compression(self, segment: np.ndarray) -> np.ndarray:
        """Apply gentle compression to maintain dynamics while controlling peaks."""
        if len(segment) == 0:
            return segment
        
        # Simple soft compression
        threshold = 0.7
        ratio = 3.0  # 3:1 compression ratio
        
        # Calculate instantaneous amplitude
        abs_segment = np.abs(segment)
        
        # Apply compression above threshold
        mask = abs_segment > threshold
        if np.any(mask):
            # Compressed amplitude
            compressed_amp = threshold + (abs_segment[mask] - threshold) / ratio
            
            # Maintain original sign
            sign = np.sign(segment[mask])
            segment[mask] = compressed_amp * sign
        
        return segment

    def _apply_adaptive_normalization(self, audio_data: np.ndarray) -> np.ndarray:
        """Apply normalization that accounts for question segments."""
        if len(audio_data) == 0:
            return audio_data
        
        # Calculate separate levels for questions and non-questions
        question_mask = self._create_question_mask(len(audio_data))
        
        question_rms = 0.0
        non_question_rms = 0.0
        
        if np.any(question_mask):
            question_audio = audio_data[question_mask]
            question_rms = np.sqrt(np.mean(question_audio**2))
        
        if np.any(~question_mask):
            non_question_audio = audio_data[~question_mask]
            non_question_rms = np.sqrt(np.mean(non_question_audio**2))
        
        # Calculate adaptive target level
        if question_rms > 0 and non_question_rms > 0:
            # Balance between question and non-question levels
            target_level = (question_rms * 0.7 + non_question_rms * 0.3)
        elif question_rms > 0:
            target_level = question_rms * 0.8  # Slightly lower to preserve dynamics
        else:
            target_level = np.sqrt(np.mean(audio_data**2)) * 0.7  # Standard normalization
        
        # Apply normalization
        current_rms = np.sqrt(np.mean(audio_data**2))
        if current_rms > 1e-8:  # Avoid division by zero
            normalization_factor = target_level / current_rms
            # Limit normalization to prevent excessive amplification
            normalization_factor = min(normalization_factor, 3.0)
            audio_data = audio_data * normalization_factor
        
        return audio_data

    def _apply_final_smoothing(self, audio_data: np.ndarray) -> np.ndarray:
        """Apply final smoothing to remove processing artifacts."""
        if not SCIPY_AVAILABLE or len(audio_data) < 100:
            return audio_data
        
        try:
            # Gentle smoothing filter to remove processing artifacts
            if len(audio_data) > 51:  # Minimum length for savgol filter
                # Use Savitzky-Golay filter for gentle smoothing
                window_length = min(51, len(audio_data) // 10)
                if window_length % 2 == 0:
                    window_length += 1  # Must be odd
                
                if window_length >= 5:
                    smoothed = savgol_filter(audio_data, window_length, 3)
                    # Blend with original to maintain character
                    audio_data = 0.9 * audio_data + 0.1 * smoothed
        except Exception as e:
            logger.warning(f"Final smoothing failed: {e}")
        
        return audio_data

    def _create_question_mask(self, length: int) -> np.ndarray:
        """Create boolean mask for question segments."""
        mask = np.zeros(length, dtype=bool)
        
        for start_time, end_time in self.question_segments:
            start_sample = int(start_time * self.sample_rate)
            end_sample = int(end_time * self.sample_rate)
            
            # Validate bounds
            start_sample = max(0, start_sample)
            end_sample = min(length, end_sample)
            
            if start_sample < end_sample:
                mask[start_sample:end_sample] = True
        
        return mask

    def _create_question_buffer_mask(self, length: int) -> np.ndarray:
        """Create mask including buffer zones around questions."""
        mask = np.zeros(length, dtype=bool)
        buffer_seconds = 2.0  # 2-second buffer around questions
        buffer_samples = int(buffer_seconds * self.sample_rate)
        
        for start_time, end_time in self.question_segments:
            start_sample = int(start_time * self.sample_rate)
            end_sample = int(end_time * self.sample_rate)
            
            # Add buffer
            start_sample = max(0, start_sample - buffer_samples)
            end_sample = min(length, end_sample + buffer_samples)
            
            if start_sample < end_sample:
                mask[start_sample:end_sample] = True
        
        return mask

    def get_processing_statistics(self, original_audio: np.ndarray, 
                                processed_audio: np.ndarray) -> Dict[str, Any]:
        """
        Get statistics about the processing applied.
        
        Args:
            original_audio: Original audio data
            processed_audio: Processed audio data
            
        Returns:
            Dictionary with processing statistics
        """
        stats = {}
        
        # Basic level statistics
        orig_rms = np.sqrt(np.mean(original_audio**2))
        proc_rms = np.sqrt(np.mean(processed_audio**2))
        
        stats['original_rms'] = float(orig_rms)
        stats['processed_rms'] = float(proc_rms)
        stats['rms_change_db'] = float(20 * np.log10(proc_rms / (orig_rms + 1e-8)))
        
        # Peak statistics
        stats['original_peak'] = float(np.max(np.abs(original_audio)))
        stats['processed_peak'] = float(np.max(np.abs(processed_audio)))
        
        # Question segment statistics
        stats['question_segments'] = len(self.question_segments)
        stats['total_question_time'] = sum(end - start for start, end in self.question_segments)
        
        if len(original_audio) > 0:
            total_time = len(original_audio) / self.sample_rate
            stats['question_percentage'] = (stats['total_question_time'] / total_time) * 100
        else:
            stats['question_percentage'] = 0.0
        
        # Processing effectiveness
        if self.question_segments:
            question_mask = self._create_question_mask(len(processed_audio))
            
            if np.any(question_mask):
                question_audio = processed_audio[question_mask]
                stats['question_rms'] = float(np.sqrt(np.mean(question_audio**2)))
            
            if np.any(~question_mask):
                non_question_audio = processed_audio[~question_mask]
                stats['non_question_rms'] = float(np.sqrt(np.mean(non_question_audio**2)))
        
        return stats

    def analyze_content_type(self, audio_data: np.ndarray, 
                           question_segments: List[Tuple[float, float]]) -> Dict[str, Any]:
        """
        Analyze the audio content type and provide processing recommendations.
        
        Args:
            audio_data: Audio data to analyze
            question_segments: Detected question segments
            
        Returns:
            Content analysis and recommendations
        """
        total_time = len(audio_data) / self.sample_rate
        question_time = sum(end - start for start, end in question_segments)
        question_ratio = question_time / total_time if total_time > 0 else 0
        
        # Analyze audio characteristics
        rms_level = np.sqrt(np.mean(audio_data**2))
        peak_level = np.max(np.abs(audio_data))
        dynamic_range = peak_level / (rms_level + 1e-8)
        
        # Content type classification
        if question_ratio > 0.3:
            content_type = "Q&A Heavy"
            recommended_mode = "gentle"
        elif question_ratio > 0.15:
            content_type = "Interactive Lecture"
            recommended_mode = "balanced"
        elif question_ratio > 0.05:
            content_type = "Lecture with Questions"
            recommended_mode = "standard_with_preservation"
        else:
            content_type = "Standard Lecture"
            recommended_mode = "standard"
        
        return {
            'content_type': content_type,
            'recommended_mode': recommended_mode,
            'question_ratio': question_ratio,
            'total_questions': len(question_segments),
            'audio_quality': {
                'rms_level': float(rms_level),
                'peak_level': float(peak_level),
                'dynamic_range': float(dynamic_range)
            },
            'processing_recommendations': {
                'noise_reduction_strength': self._recommend_noise_reduction(question_ratio),
                'question_amplification': self._recommend_amplification(question_ratio),
                'preservation_buffer': self._recommend_buffer(question_ratio)
            }
        }

    def _recommend_noise_reduction(self, question_ratio: float) -> float:
        """Recommend noise reduction strength based on question ratio."""
        if question_ratio > 0.3:
            return 0.2  # Very gentle
        elif question_ratio > 0.15:
            return 0.3  # Gentle
        elif question_ratio > 0.05:
            return 0.4  # Moderate
        else:
            return 0.6  # Standard

    def _recommend_amplification(self, question_ratio: float) -> float:
        """Recommend question amplification based on question ratio."""
        if question_ratio > 0.3:
            return 3.0  # More amplification for Q&A heavy content
        elif question_ratio > 0.15:
            return 2.0  # Moderate amplification
        else:
            return 1.0  # Light amplification

    def _recommend_buffer(self, question_ratio: float) -> float:
        """Recommend buffer size around questions."""
        if question_ratio > 0.3:
            return 3.0  # Larger buffer for Q&A heavy content
        elif question_ratio > 0.15:
            return 2.0  # Standard buffer
        else:
            return 1.0  # Smaller buffer