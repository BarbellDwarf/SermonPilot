#!/usr/bin/env python3
"""
Real Sermon Test with DeepFilterNet GPU Processing
Test sermon ID: 721242325445763
"""

import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
import yaml

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

import sermonaudio
from sermonaudio.node.requests import Node

# Add src directory to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from audio_processing import AudioProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_config():
    """Load configuration from config.yaml"""
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)

def download_sermon(sermon_id: str, output_dir: Path) -> Path:
    """Download sermon audio file"""

    logger.info(f"🎵 Downloading sermon ID: {sermon_id}")

    # Get sermon info
    sermon_node = Node(f"/sermons/{sermon_id}")
    sermon_data = sermon_node.get()

    if not sermon_data:
        raise Exception(f"Could not find sermon with ID: {sermon_id}")

    sermon_info = sermon_data[0]
    title = sermon_info.get('full_title', f'Sermon_{sermon_id}')

    # Clean title for filename
    safe_title = re.sub(r'[^\w\-_\. ]', '', title)
    safe_title = safe_title.replace(' ', '_')[:100]  # Limit length

    logger.info(f"📝 Sermon: {title}")
    logger.info(f"👤 Speaker: {sermon_info.get('speaker_name', 'Unknown')}")
    logger.info(f"📅 Date: {sermon_info.get('date_preached', 'Unknown')}")

    # Get download URL
    download_url = sermon_info.get('download_url')
    if not download_url:
        raise Exception("No download URL available for this sermon")

    # Download the file
    output_file = output_dir / f"{safe_title}_{sermon_id}.mp3"

    logger.info(f"⬇️  Downloading from: {download_url}")
    logger.info(f"💾 Saving to: {output_file}")

    response = requests.get(download_url, stream=True)
    response.raise_for_status()

    total_size = int(response.headers.get('content-length', 0))
    downloaded = 0

    with open(output_file, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    progress = (downloaded / total_size) * 100
                    print(f"\r📥 Download progress: {progress:.1f}%", end='', flush=True)

    print()  # New line after progress
    logger.info(f"✅ Download completed: {output_file.name}")
    logger.info(f"📊 File size: {output_file.stat().st_size / (1024*1024):.2f} MB")

    return output_file

def test_deepfilternet_gpu(audio_file: Path, output_dir: Path) -> dict:
    """Test DeepFilterNet with GPU processing"""

    logger.info("🚀 TESTING DEEPFILTERNET WITH GPU")
    logger.info("="*60)

    start_time = time.time()

    # Initialize processor with DeepFilterNet
    processor = AudioProcessor(enhancement_method="deepfilternet")

    # Create output filename
    output_file = output_dir / f"{audio_file.stem}_enhanced_deepfilternet.wav"

    logger.info(f"📁 Input: {audio_file.name}")
    logger.info(f"📁 Output: {output_file.name}")
    logger.info("🔧 Method: DeepFilterNet")
    logger.info("💻 Device: GPU (CUDA)")

    # Get audio info first
    import soundfile as sf
    try:
        audio_info = sf.info(str(audio_file))
        duration_minutes = audio_info.frames / audio_info.samplerate / 60

        logger.info("📊 Audio info:")
        logger.info(f"   🎵 Duration: {duration_minutes:.2f} minutes")
        logger.info(f"   📻 Sample rate: {audio_info.samplerate} Hz")
        logger.info(f"   📈 Channels: {audio_info.channels}")
        logger.info(f"   📐 Format: {audio_info.format}")

    except Exception as e:
        logger.warning(f"Could not get audio info: {e}")
        duration_minutes = 0

    # Process the audio
    try:
        success = processor.process_sermon_audio(
            input_path=str(audio_file),
            output_path=str(output_file),
            noise_reduction=True,
            amplify=True,
            normalize=True
        )

        processing_time = time.time() - start_time

        if success and output_file.exists():
            # Get output info
            output_info = sf.info(str(output_file))
            output_size_mb = output_file.stat().st_size / (1024 * 1024)

            # Calculate performance metrics
            if duration_minutes > 0:
                speed_ratio = duration_minutes / (processing_time / 60)
            else:
                speed_ratio = 0

            results = {
                "status": "success",
                "processing_time_seconds": processing_time,
                "processing_time_minutes": processing_time / 60,
                "audio_duration_minutes": duration_minutes,
                "speed_ratio": speed_ratio,
                "output_size_mb": output_size_mb,
                "output_file": str(output_file),
                "input_sample_rate": audio_info.samplerate if 'audio_info' in locals() else None,
                "output_sample_rate": output_info.samplerate,
                "input_channels": audio_info.channels if 'audio_info' in locals() else None,
                "output_channels": output_info.channels
            }

            logger.info("✅ PROCESSING COMPLETED SUCCESSFULLY!")
            logger.info(f"⏱️  Processing time: {processing_time:.2f} seconds ({processing_time/60:.2f} minutes)")
            if duration_minutes > 0:
                logger.info(f"🚀 Speed ratio: {speed_ratio:.2f}x real-time")
            logger.info(f"📊 Output size: {output_size_mb:.2f} MB")
            logger.info(f"📁 Enhanced file: {output_file.name}")

            return results

        else:
            logger.error("❌ Processing failed - no output file created")
            return {
                "status": "failed",
                "error": "No output file created",
                "processing_time_seconds": processing_time
            }

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"❌ Processing failed with exception: {e}")
        return {
            "status": "error",
            "error": str(e),
            "processing_time_seconds": processing_time
        }

def main():
    """Main test function"""

    sermon_id = "721242325445763"

    # Create test directory
    test_dir = Path("real_sermon_test")
    test_dir.mkdir(exist_ok=True)

    logger.info("🎯 REAL SERMON DEEPFILTERNET GPU TEST")
    logger.info("="*70)
    logger.info(f"📋 Sermon ID: {sermon_id}")
    logger.info(f"📁 Test directory: {test_dir}")
    logger.info(f"📅 Test time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        # Load config and set up API
        config = load_config()
        sermonaudio.set_api_key(config['api_key'])

        # Download sermon
        audio_file = download_sermon(sermon_id, test_dir)

        # Test DeepFilterNet processing
        results = test_deepfilternet_gpu(audio_file, test_dir)

        # Print final summary
        logger.info("\n" + "="*70)
        logger.info("🏆 FINAL RESULTS SUMMARY")
        logger.info("="*70)

        if results["status"] == "success":
            logger.info("✅ Status: SUCCESS")
            logger.info(f"⏱️  Total processing time: {results['processing_time_minutes']:.2f} minutes")
            logger.info(f"🎵 Audio duration: {results['audio_duration_minutes']:.2f} minutes")
            logger.info(f"🚀 Performance: {results['speed_ratio']:.2f}x real-time")
            logger.info(f"📊 Output size: {results['output_size_mb']:.2f} MB")
            logger.info(f"📁 Enhanced file: {Path(results['output_file']).name}")

            # Performance analysis
            if results['speed_ratio'] >= 10:
                logger.info("🌟 EXCELLENT: Very fast processing!")
            elif results['speed_ratio'] >= 5:
                logger.info("⭐ GOOD: Fast processing!")
            elif results['speed_ratio'] >= 1:
                logger.info("👍 ACCEPTABLE: Real-time processing!")
            else:
                logger.info("⚠️  SLOW: Slower than real-time")

        else:
            logger.error(f"❌ Status: {results['status'].upper()}")
            logger.error(f"💥 Error: {results.get('error', 'Unknown error')}")
            logger.error(f"⏱️  Time before failure: {results['processing_time_seconds']:.2f} seconds")

        logger.info(f"\n📁 All files saved in: {test_dir.absolute()}")

    except Exception as e:
        logger.error(f"💥 Test failed with exception: {e}")
        return False

    return results.get("status") == "success"

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
