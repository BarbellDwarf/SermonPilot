"""
Enhanced Audio Processor - API matching the specification requirements

Provides the enhanced interface as specified in the detailed requirements,
wrapping the existing AudioProcessor with additional functionality.
"""

import logging
from pathlib import Path
from typing import Any

from audio_processing import AudioProcessor
from qa_normalizer import QANormalizer

logger = logging.getLogger(__name__)


class EnhancedAudioProcessor:
    """
    Enhanced audio processing with Q&A normalization as specified in requirements.
    
    Provides the exact API interface shown in the specification comments.
    """

    def __init__(self, config: dict[str, Any]):
        """
        Initialize enhanced audio processor with configuration.
        
        Args:
            config: Complete configuration dictionary
        """
        self.config = config

        # Q&A normalization configuration
        qa_config = config.get('qa_normalization', {})
        self.qa_normalizer = QANormalizer(config) if qa_config.get('enabled', False) else None

        # Audio processing configuration
        self.target_lufs = qa_config.get('target_lufs', -23.0)
        self.main_speaker_threshold = qa_config.get('main_speaker_threshold', -12.0)
        self.question_threshold = qa_config.get('question_threshold', -30.0)

        # Initialize underlying audio processor
        audio_config = config.get('audio_processing', {})
        enhancement_method = audio_config.get('enhancement_method', 'clear')
        self.audio_processor = AudioProcessor(enhancement_method=enhancement_method, config=config)

        logger.info(f"Enhanced AudioProcessor initialized with Q&A normalization: {self.qa_normalizer is not None}")

    def process_sermon_audio(self, audio_file: str, metadata: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """
        Process sermon audio with comprehensive Q&A normalization and enhancement.
        
        Args:
            audio_file: Path to input audio file
            metadata: Sermon metadata for processing context
            
        Returns:
            Tuple of (output_file_path, processing_log)
        """
        logger.info(f"Processing sermon audio: {audio_file}")

        # Generate output file path
        input_path = Path(audio_file)
        output_file = str(input_path.parent / f"{input_path.stem}_enhanced{input_path.suffix}")

        try:
            # Step 1: Q&A segment detection and normalization
            qa_info = None
            if self.qa_normalizer:
                logger.info("Applying Q&A normalization")
                normalized_audio, sample_rate = self.qa_normalizer.process_audio(audio_file)

                # Save temporary normalized audio for further processing
                temp_file = str(input_path.parent / f"{input_path.stem}_qa_normalized{input_path.suffix}")
                import soundfile as sf
                sf.write(temp_file, normalized_audio, sample_rate)

                # Get Q&A processing information
                qa_info = {
                    'qa_segments_detected': self.qa_normalizer.get_segments(),
                    'normalization_applied': True,
                    'processing_stats': self.qa_normalizer.get_processing_stats()
                }

                # Use normalized audio for further processing
                audio_file = temp_file

            # Step 2: General audio enhancement using existing pipeline
            success, additional_qa_info = self.audio_processor.process_sermon_audio(
                input_path=audio_file,
                output_path=output_file,
                apply_qa_normalization=False  # Already applied above if enabled
            )

            if not success:
                raise RuntimeError("Audio processing failed")

            # Step 3: Store processing metadata
            processing_log = {
                'qa_segments_detected': qa_info['qa_segments_detected'] if qa_info else [],
                'normalization_applied': qa_info is not None,
                'audio_quality_metrics': self.get_quality_metrics(output_file),
                'enhancement_method': self.audio_processor.enhancement_method,
                'processing_success': True
            }

            # Merge Q&A information
            if qa_info:
                processing_log.update(qa_info)

            # Clean up temporary file if created
            if qa_info and Path(audio_file).exists() and 'qa_normalized' in audio_file:
                Path(audio_file).unlink()

            logger.info(f"Enhanced audio processing completed: {output_file}")
            return output_file, processing_log

        except Exception as e:
            logger.error(f"Enhanced audio processing failed: {e}")
            processing_log = {
                'qa_segments_detected': [],
                'normalization_applied': False,
                'audio_quality_metrics': {},
                'enhancement_method': self.audio_processor.enhancement_method,
                'processing_success': False,
                'error': str(e)
            }
            return audio_file, processing_log

    def get_quality_metrics(self, audio_file: str) -> dict[str, Any]:
        """
        Calculate audio quality metrics for the processed file.
        
        Args:
            audio_file: Path to audio file
            
        Returns:
            Dictionary of quality metrics
        """
        try:
            import numpy as np
            import soundfile as sf

            audio_data, sample_rate = sf.read(audio_file)
            if audio_data.ndim > 1:
                audio_data = np.mean(audio_data, axis=1)

            # Calculate basic quality metrics
            rms_level = np.sqrt(np.mean(audio_data**2))
            peak_level = np.max(np.abs(audio_data))

            # Convert to dB
            rms_db = 20 * np.log10(rms_level + 1e-10)
            peak_db = 20 * np.log10(peak_level + 1e-10)

            # Calculate signal-to-noise ratio estimate
            # Use bottom 10% of RMS values as noise floor estimate
            window_size = int(0.1 * sample_rate)  # 100ms windows
            rms_windows = []
            for i in range(0, len(audio_data) - window_size, window_size):
                window = audio_data[i:i + window_size]
                window_rms = np.sqrt(np.mean(window**2))
                rms_windows.append(window_rms)

            rms_windows = np.array(rms_windows)
            noise_floor = np.percentile(rms_windows, 10)
            signal_level = np.percentile(rms_windows, 90)

            snr_estimate = 20 * np.log10((signal_level + 1e-10) / (noise_floor + 1e-10))

            return {
                'rms_level_db': float(rms_db),
                'peak_level_db': float(peak_db),
                'snr_estimate_db': float(snr_estimate),
                'dynamic_range_db': float(peak_db - rms_db),
                'duration_seconds': len(audio_data) / sample_rate,
                'sample_rate': sample_rate,
                'quality_score': min(10.0, max(0.0, (snr_estimate + 20) / 5))  # Rough quality score 0-10
            }

        except Exception as e:
            logger.warning(f"Could not calculate quality metrics: {e}")
            return {
                'error': str(e),
                'quality_score': 0.0
            }


# Convenience function matching the specification
def create_enhanced_processor(config: dict[str, Any]) -> EnhancedAudioProcessor:
    """
    Create an enhanced audio processor with the given configuration.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Configured EnhancedAudioProcessor instance
    """
    return EnhancedAudioProcessor(config)
