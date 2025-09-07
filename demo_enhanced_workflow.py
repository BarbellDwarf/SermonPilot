#!/usr/bin/env python3
"""
Demo script for the Enhanced Audio Editing workflow

This script demonstrates the complete workflow from audio analysis 
to processing configuration using the new components.
"""

import numpy as np
import sys
from pathlib import Path

# Add project paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "ui"))

from ui.components.audio_waveform import AudioWaveformViewer
from ui.components.audio_editor import AudioEditor
from ui.components.audio_preview import AudioPreview
from ui.components.processing_modes import ProcessingModeSelector
from src.audio.question_processor import QuestionProcessor
from src.audio.adaptive_processor import AdaptiveAudioProcessor


def create_demo_audio():
    """Create demo audio with speech-like characteristics."""
    print("🎵 Creating demo audio...")
    
    sample_rate = 44100
    duration = 30.0  # 30 seconds
    samples = int(sample_rate * duration)
    
    # Create time array
    t = np.linspace(0, duration, samples)
    
    # Create speech-like audio with multiple speakers and Q&A
    # Main speaker (0-15 seconds)
    main_speech = 0.3 * np.sin(2 * np.pi * 200 * t[:samples//2])
    
    # Add some harmonics for realism
    main_speech += 0.15 * np.sin(2 * np.pi * 400 * t[:samples//2])
    main_speech += 0.08 * np.sin(2 * np.pi * 600 * t[:samples//2])
    
    # Question from audience (16-20 seconds) - higher pitch, shorter duration
    question_start = int(16 * sample_rate)
    question_end = int(20 * sample_rate)
    question_speech = 0.2 * np.sin(2 * np.pi * 300 * t[question_start:question_end])
    
    # Answer from speaker (21-30 seconds)
    answer_start = int(21 * sample_rate)
    answer_speech = 0.25 * np.sin(2 * np.pi * 180 * t[answer_start:])
    
    # Combine all parts
    audio_data = np.zeros(samples)
    audio_data[:samples//2] = main_speech
    audio_data[question_start:question_end] = question_speech
    audio_data[answer_start:] = answer_speech
    
    # Add realistic pauses and noise
    # Pause after main speech (15-16 seconds)
    audio_data[int(15 * sample_rate):int(16 * sample_rate)] *= 0.1
    
    # Pause after question (20-21 seconds)
    audio_data[int(20 * sample_rate):int(21 * sample_rate)] *= 0.1
    
    # Add background noise
    noise = np.random.randn(samples) * 0.03
    audio_data += noise
    
    # Normalize
    max_val = np.max(np.abs(audio_data))
    if max_val > 0:
        audio_data = audio_data / max_val * 0.8
    
    return audio_data, sample_rate


def demo_audio_analysis(audio_data, sample_rate):
    """Demonstrate audio analysis capabilities."""
    print("\n📊 Analyzing audio...")
    
    # Create waveform viewer
    waveform_viewer = AudioWaveformViewer(audio_data, sample_rate)
    audio_info = waveform_viewer.get_audio_info()
    
    print(f"   Duration: {audio_info['duration']:.1f} seconds")
    print(f"   Sample Rate: {audio_info['sample_rate']} Hz")
    print(f"   Max Amplitude: {audio_info['max_amplitude']:.3f}")
    print(f"   RMS Level: {audio_info['rms_level']:.3f}")
    
    # Detect question segments
    question_processor = QuestionProcessor({'sample_rate': sample_rate})
    question_segments = question_processor.detect_question_segments(audio_data)
    
    print(f"   Detected Q&A segments: {len(question_segments)}")
    for i, (start, end) in enumerate(question_segments):
        print(f"     Segment {i+1}: {start:.1f}s - {end:.1f}s ({end-start:.1f}s)")
    
    return waveform_viewer, question_segments


def demo_audio_editing(waveform_viewer, audio_data, sample_rate):
    """Demonstrate audio editing capabilities."""
    print("\n✂️ Applying audio edits...")
    
    # Add manual edits
    edits = [
        (1.0, 3.0, "amplify", "Boost introduction"),
        (14.5, 15.5, "remove", "Remove long pause"),
        (25.0, 27.0, "amplify", "Boost conclusion"),
    ]
    
    audio_editor = AudioEditor()
    
    for start, end, action, description in edits:
        waveform_viewer.add_segment(start, end, action)
        print(f"   Added {action} edit: {start:.1f}s-{end:.1f}s ({description})")
    
    # Apply edits
    segments = waveform_viewer.get_segments()
    processed_audio = audio_data.copy()
    
    # Apply in reverse order to maintain indices
    for start_time, end_time, action in reversed(segments):
        processed_audio = audio_editor.apply_edit(
            processed_audio, sample_rate, start_time, end_time, action
        )
    
    # Get edit summary
    summary = audio_editor.get_editing_summary(segments)
    print(f"   Total segments edited: {summary['total_segments']}")
    print(f"   Total edited duration: {summary['total_edited_duration']:.1f}s")
    
    return processed_audio, segments


def demo_processing_modes():
    """Demonstrate processing mode selection."""
    print("\n🎛️ Available processing modes...")
    
    mode_selector = ProcessingModeSelector()
    
    for mode_key, mode_info in mode_selector.modes.items():
        print(f"   {mode_info['icon']} {mode_info['name']}")
        print(f"     {mode_info['description']}")
        
        # Show processing intensity
        settings = mode_info['settings']
        if settings:  # Skip empty custom settings
            intensity = mode_selector._calculate_processing_intensity(settings)
            time_est = mode_selector._estimate_processing_time(settings)
            quality = mode_selector._estimate_quality_impact(settings)
            
            print(f"     Intensity: {intensity:.0%}, Time: {time_est:.1f}x, Quality: {quality:.0f}%")
        print()


def demo_adaptive_processing(audio_data, sample_rate, question_segments):
    """Demonstrate adaptive processing with question preservation."""
    print("\n🧠 Applying adaptive processing...")
    
    # Configure adaptive processor for Q&A content
    config = {
        'sample_rate': sample_rate,
        'gentle_noise_reduction': 0.2,  # Very gentle for questions
        'standard_noise_reduction': 0.5,  # Standard for other content
        'question_amplification_db': 2.0
    }
    
    adaptive_processor = AdaptiveAudioProcessor(config)
    
    # Process with question preservation
    processed_audio = adaptive_processor.process_with_question_preservation(
        audio_data, question_segments
    )
    
    # Get processing statistics
    stats = adaptive_processor.get_processing_statistics(audio_data, processed_audio)
    
    print(f"   Original RMS: {stats['original_rms']:.4f}")
    print(f"   Processed RMS: {stats['processed_rms']:.4f}")
    print(f"   RMS Change: {stats['rms_change_db']:.1f} dB")
    print(f"   Question segments preserved: {stats['question_segments']}")
    print(f"   Question percentage: {stats['question_percentage']:.1f}%")
    
    # Content analysis
    analysis = adaptive_processor.analyze_content_type(audio_data, question_segments)
    print(f"   Content type: {analysis['content_type']}")
    print(f"   Recommended mode: {analysis['recommended_mode']}")
    
    return processed_audio, stats


def demo_preview_generation(original_audio, processed_audio, sample_rate):
    """Demonstrate audio preview generation."""
    print("\n🔊 Generating audio previews...")
    
    audio_preview = AudioPreview()
    
    # Generate statistics comparison
    original_stats = audio_preview.get_audio_statistics(original_audio)
    processed_stats = audio_preview.get_audio_statistics(processed_audio)
    
    print("   Audio quality comparison:")
    print(f"     Original - Max: {original_stats['max_amplitude']:.3f}, RMS: {original_stats['rms_level']:.3f}")
    print(f"     Processed - Max: {processed_stats['max_amplitude']:.3f}, RMS: {processed_stats['rms_level']:.3f}")
    
    # Create preview files (would be used in UI)
    try:
        original_preview = audio_preview.create_preview_audio(original_audio, sample_rate)
        processed_preview = audio_preview.create_preview_audio(processed_audio, sample_rate)
        
        if original_preview and processed_preview:
            print(f"   Created preview files:")
            print(f"     Original: {original_preview}")
            print(f"     Processed: {processed_preview}")
        
        # Cleanup
        audio_preview.cleanup_temp_files()
        
    except Exception as e:
        print(f"   Preview generation skipped: {e}")


def main():
    """Run the complete demo workflow."""
    print("🎵 Enhanced Audio Editing Workflow Demo")
    print("=" * 50)
    
    try:
        # Step 1: Create demo audio
        audio_data, sample_rate = create_demo_audio()
        
        # Step 2: Analyze audio
        waveform_viewer, question_segments = demo_audio_analysis(audio_data, sample_rate)
        
        # Step 3: Apply edits
        edited_audio, segments = demo_audio_editing(waveform_viewer, audio_data, sample_rate)
        
        # Step 4: Show processing modes
        demo_processing_modes()
        
        # Step 5: Apply adaptive processing
        final_audio, stats = demo_adaptive_processing(edited_audio, sample_rate, question_segments)
        
        # Step 6: Generate previews
        demo_preview_generation(audio_data, final_audio, sample_rate)
        
        print("\n✅ Demo completed successfully!")
        print(f"   Original length: {len(audio_data)/sample_rate:.1f}s")
        print(f"   Final length: {len(final_audio)/sample_rate:.1f}s")
        print(f"   Processing preserved {len(question_segments)} Q&A segments")
        
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()