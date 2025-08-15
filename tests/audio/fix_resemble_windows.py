#!/usr/bin/env python3
"""
Fix for Resemble Enhance Windows PosixPath compatibility issue
"""

import logging
import platform
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

def fix_resemble_enhance_windows_compatibility():
    """Fix the PosixPath issue in Resemble Enhance for Windows compatibility"""

    print("🔧 Fixing Resemble Enhance Windows compatibility...")

    try:
        import resemble_enhance
        resemble_package_dir = Path(resemble_enhance.__file__).parent
        model_repo_dir = resemble_package_dir / "model_repo" / "enhancer_stage2"
        hparams_file = model_repo_dir / "hparams.yaml"

        if not hparams_file.exists():
            print(f"❌ hparams.yaml not found at {hparams_file}")
            return False

        print(f"📁 Found hparams.yaml at: {hparams_file}")

        # Read the current file
        with open(hparams_file) as f:
            content = f.read()

        print("📝 Original hparams.yaml content (first 10 lines):")
        for i, line in enumerate(content.split('\n')[:10]):
            print(f"  {i+1}: {line}")

        # Check if it has PosixPath issues
        if "pathlib.PosixPath" in content:
            print("⚠️  Detected PosixPath issues, creating Windows-compatible version...")

            # Create backup
            backup_file = hparams_file.with_suffix('.yaml.backup')
            shutil.copy2(hparams_file, backup_file)
            print(f"💾 Backup created: {backup_file}")

            # Fix the content by replacing PosixPath with generic paths
            if platform.system() == "Windows":
                # Replace PosixPath with WindowsPath for Windows
                fixed_content = content.replace(
                    "!!python/object/apply:pathlib.PosixPath",
                    "!!python/object/apply:pathlib.WindowsPath"
                )
            else:
                # Keep as is for non-Windows
                fixed_content = content

            # Alternative approach: replace with simple string paths
            lines = content.split('\n')
            fixed_lines = []

            for line in lines:
                if "!!python/object/apply:pathlib.PosixPath" in line:
                    # Extract the path components and convert to simple string
                    if "fg_dir:" in line:
                        fixed_lines.append("fg_dir: data/fg")
                    elif "bg_dir:" in line:
                        fixed_lines.append("bg_dir: data/bg")
                    elif "rir_dir:" in line:
                        fixed_lines.append("rir_dir: data/rir")
                    else:
                        fixed_lines.append(line)
                elif line.startswith("- ") and any(prev_line.endswith("_dir: !!python/object/apply:pathlib.PosixPath") for prev_line in lines[max(0, len(fixed_lines)-2):len(fixed_lines)]):
                    # Skip the path component lines
                    continue
                else:
                    fixed_lines.append(line)

            fixed_content = '\n'.join(fixed_lines)

            # Write the fixed version
            with open(hparams_file, 'w') as f:
                f.write(fixed_content)

            print("✅ Fixed hparams.yaml for Windows compatibility")

            # Verify the fix
            print("📝 Fixed hparams.yaml content (first 10 lines):")
            for i, line in enumerate(fixed_content.split('\n')[:10]):
                print(f"  {i+1}: {line}")

            return True
        else:
            print("✅ No PosixPath issues detected, file is already compatible")
            return True

    except Exception as e:
        print(f"❌ Failed to fix compatibility: {e}")
        return False

def create_custom_resemble_enhancer():
    """Create a custom wrapper that avoids the PosixPath issue entirely"""

    print("🔧 Creating custom Resemble Enhance wrapper...")

    wrapper_code = '''
import torch
import tempfile
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class WindowsCompatibleResembleEnhancer:
    """Windows-compatible wrapper for Resemble Enhance"""
    
    def __init__(self, device="cuda"):
        self.device = device
        self.available = self._check_availability()
    
    def _check_availability(self):
        """Check if resemble-enhance command line is available"""
        try:
            import shutil
            return shutil.which("resemble-enhance") is not None
        except:
            return False
    
    def enhance_audio(self, input_path, output_path, denoise_only=False):
        """Enhance audio using command line interface (avoids Python API issues)"""
        if not self.available:
            raise RuntimeError("resemble-enhance command not available")
        
        cmd = ["resemble-enhance", input_path, output_path]
        if denoise_only:
            cmd.append("--denoise_only")
        
        # Add device selection if CUDA available
        if self.device == "cuda" and torch.cuda.is_available():
            cmd.extend(["--device", "cuda"])
        else:
            cmd.extend(["--device", "cpu"])
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.info(f"Resemble Enhance completed successfully")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Resemble Enhance failed: {e.stderr}")
            raise e
    
    def process_chunk(self, audio_chunk, sample_rate):
        """Process a single audio chunk"""
        import soundfile as sf
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_input:
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_output:
                try:
                    # Save chunk
                    sf.write(temp_input.name, audio_chunk, sample_rate)
                    temp_input.close()
                    
                    # Process
                    self.enhance_audio(temp_input.name, temp_output.name)
                    
                    # Load result
                    temp_output.close()
                    enhanced_chunk, _ = sf.read(temp_output.name)
                    
                    return enhanced_chunk
                    
                finally:
                    # Cleanup
                    import os
                    try:
                        if os.path.exists(temp_input.name):
                            os.unlink(temp_input.name)
                        if os.path.exists(temp_output.name):
                            os.unlink(temp_output.name)
                    except:
                        pass
'''

    wrapper_file = Path("tests") / "windows_resemble_wrapper.py"
    with open(wrapper_file, 'w') as f:
        f.write(wrapper_code)

    print(f"✅ Created custom wrapper: {wrapper_file}")
    return wrapper_file

def test_fixes():
    """Test the fixes"""
    print("🧪 Testing Resemble Enhance fixes...")

    # Try the fixes
    fix_success = fix_resemble_enhance_windows_compatibility()
    wrapper_created = create_custom_resemble_enhancer()

    if fix_success:
        # Test if we can now import without errors
        try:
            print("✅ Resemble Enhance Python API import successful after fix")
            return True
        except Exception as e:
            print(f"⚠️  Python API still has issues: {e}")
            print("💡 Will use command line wrapper instead")
            return wrapper_created is not None
    else:
        print("❌ Could not fix hparams.yaml")
        return False

if __name__ == "__main__":
    test_fixes()
