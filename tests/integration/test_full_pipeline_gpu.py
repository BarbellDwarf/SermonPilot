#!/usr/bin/env python3
"""
Full Pipeline Test with GPU Acceleration
Uses the complete sermon_updater.py pipeline for processing sermon ID 721242325445763
"""

import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def backup_and_modify_config_for_gpu():
    """Backup current config and modify for GPU testing"""

    config_path = Path(__file__).parent.parent / "config.yaml"
    backup_path = Path(__file__).parent.parent / "config_backup.yaml"

    # Backup current config
    import shutil
    shutil.copy2(config_path, backup_path)
    logger.info(f"✅ Backed up config to: {backup_path}")

    # Read current config
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Modify for GPU testing
    original_method = config.get('audio_enhancement_method', 'resemble_enhance')
    config['audio_enhancement_method'] = 'deepfilternet'  # Use GPU-optimized DeepFilterNet
    config['dry_run'] = False  # Ensure we actually process

    # Write modified config
    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)

    logger.info("🔧 Modified config:")
    logger.info(f"   Original method: {original_method}")
    logger.info("   GPU method: deepfilternet")
    logger.info("   Dry run: False")

    return backup_path, original_method

def restore_config(backup_path):
    """Restore original config from backup"""

    config_path = Path(__file__).parent.parent / "config.yaml"

    import shutil
    shutil.copy2(backup_path, config_path)
    backup_path.unlink()  # Delete backup

    logger.info("🔄 Restored original config")

def run_full_pipeline_test(sermon_id: str):
    """Run the full sermon_updater.py pipeline on a specific sermon"""

    logger.info("🚀 RUNNING FULL PIPELINE WITH GPU ACCELERATION")
    logger.info("="*70)
    logger.info(f"📋 Sermon ID: {sermon_id}")
    logger.info("🔧 Enhancement: DeepFilterNet (GPU)")
    logger.info(f"📅 Test time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    start_time = time.time()

    try:
        # Import the sermon updater after config is set
        sys.path.append(str(Path(__file__).parent.parent))
        from sermon_updater import process_single_sermon

        logger.info(f"🎵 Processing sermon {sermon_id} with full pipeline...")

        # Process the sermon using the full pipeline
        result = process_single_sermon(sermon_id)

        processing_time = time.time() - start_time

        logger.info("✅ FULL PIPELINE PROCESSING COMPLETED!")
        logger.info(f"⏱️  Total processing time: {processing_time:.2f} seconds ({processing_time/60:.2f} minutes)")

        # Check for output files
        processed_dir = Path(__file__).parent.parent / "processed_sermons" / sermon_id
        if processed_dir.exists():
            files = list(processed_dir.glob("*"))
            logger.info(f"📁 Output directory: {processed_dir}")
            logger.info(f"📄 Generated files ({len(files)}):")
            for file in files:
                size_mb = file.stat().st_size / (1024 * 1024)
                logger.info(f"   📄 {file.name} ({size_mb:.2f} MB)")

        return True, processing_time

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"❌ Full pipeline failed: {e}")
        logger.error(f"⏱️  Time before failure: {processing_time:.2f} seconds")
        return False, processing_time

def main():
    """Main test function"""

    sermon_id = "721242325445763"
    backup_path = None

    try:
        logger.info("🎯 FULL SERMON PIPELINE GPU TEST")
        logger.info("="*70)

        # Backup and modify config for GPU testing
        backup_path, original_method = backup_and_modify_config_for_gpu()

        # Run the full pipeline test
        success, processing_time = run_full_pipeline_test(sermon_id)

        # Results summary
        logger.info("\n" + "="*70)
        logger.info("🏆 FULL PIPELINE TEST RESULTS")
        logger.info("="*70)

        if success:
            logger.info("✅ Status: SUCCESS")
            logger.info(f"⏱️  Total time: {processing_time:.2f} seconds ({processing_time/60:.2f} minutes)")
            logger.info("🔧 Method: DeepFilterNet (GPU)")
            logger.info(f"📋 Sermon ID: {sermon_id}")
            logger.info("🌟 Full pipeline completed successfully!")
        else:
            logger.error("❌ Status: FAILED")
            logger.error(f"⏱️  Time before failure: {processing_time:.2f} seconds")

        return success

    except Exception as e:
        logger.error(f"💥 Test setup failed: {e}")
        return False

    finally:
        # Always restore original config
        if backup_path and backup_path.exists():
            try:
                restore_config(backup_path)
            except Exception as e:
                logger.error(f"⚠️  Failed to restore config: {e}")

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
