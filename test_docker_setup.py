#!/usr/bin/env python3
"""
Test Docker containerization setup

Validates the Docker infrastructure created for the SermonAudio Processor.
Tests Docker configuration, Compose files, and basic functionality.
"""

import json
import os
import subprocess
import sys
from pathlib import Path


def run_command(cmd, check=True, capture_output=True):
    """Run a shell command and return the result."""
    try:
        result = subprocess.run(
            cmd, shell=True, check=check, capture_output=capture_output, text=True
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return False, e.stdout if e.stdout else "", e.stderr if e.stderr else str(e)


def test_docker_prerequisites():
    """Test that Docker and Docker Compose are available."""
    print("🔍 Testing Docker prerequisites...")
    
    # Test Docker
    success, stdout, stderr = run_command("docker --version")
    if not success:
        print("❌ Docker is not available")
        return False
    print(f"✅ Docker found: {stdout.strip()}")
    
    # Test Docker Compose
    success, stdout, stderr = run_command("docker compose version")
    if not success:
        print("❌ Docker Compose is not available")
        return False
    print(f"✅ Docker Compose found: {stdout.strip()}")
    
    return True


def test_dockerfile_syntax():
    """Test Dockerfile syntax validity."""
    print("🐳 Testing Dockerfile syntax...")
    
    dockerfiles = ["Dockerfile", "Dockerfile.dev", "Dockerfile.prod"]
    
    for dockerfile in dockerfiles:
        if not os.path.exists(dockerfile):
            print(f"❌ {dockerfile} not found")
            return False
        
        # Basic syntax check by reading the file
        try:
            with open(dockerfile, 'r') as f:
                content = f.read()
                if not content.strip():
                    print(f"❌ {dockerfile} is empty")
                    return False
                if not content.startswith('#') and not content.startswith('FROM'):
                    print(f"❌ {dockerfile} doesn't start with FROM or comment")
                    return False
            print(f"✅ {dockerfile} syntax OK")
        except Exception as e:
            print(f"❌ Error reading {dockerfile}: {e}")
            return False
    
    return True


def test_compose_files():
    """Test Docker Compose file validity."""
    print("📋 Testing Docker Compose files...")
    
    compose_files = [
        "docker-compose.yml",
        "docker-compose.dev.yml", 
        "docker-compose.prod.yml"
    ]
    
    for compose_file in compose_files:
        if not os.path.exists(compose_file):
            print(f"❌ {compose_file} not found")
            return False
        
        # Test compose file syntax
        success, stdout, stderr = run_command(f"docker compose -f {compose_file} config")
        if not success:
            print(f"❌ {compose_file} syntax error: {stderr}")
            return False
        print(f"✅ {compose_file} syntax OK")
    
    return True


def test_file_structure():
    """Test that all required files and directories exist."""
    print("📂 Testing file structure...")
    
    required_files = [
        "Dockerfile",
        "docker-compose.yml",
        ".dockerignore",
        "docker/start_production.sh",
        "docker/wait_for_services.py",
        "docker/README.md",
        "setup-docker.sh"
    ]
    
    required_dirs = [
        "docker",
        "docker/nginx",
        "docker/postgres", 
        "docker/prometheus",
        "docker/backup",
        "k8s",
        "helm/sermon-processor"
    ]
    
    for file_path in required_files:
        if not os.path.exists(file_path):
            print(f"❌ Required file missing: {file_path}")
            return False
        print(f"✅ Found: {file_path}")
    
    for dir_path in required_dirs:
        if not os.path.isdir(dir_path):
            print(f"❌ Required directory missing: {dir_path}")
            return False
        print(f"✅ Found: {dir_path}/")
    
    return True


def test_scripts_executable():
    """Test that scripts are executable."""
    print("🔧 Testing script permissions...")
    
    scripts = [
        "setup-docker.sh",
        "docker-start-dev.sh",
        "docker-start-prod.sh", 
        "docker-build.sh",
        "docker/start_production.sh",
        "docker/backup/backup_script.sh",
        "docker/backup/restore_script.sh"
    ]
    
    for script in scripts:
        if not os.path.exists(script):
            print(f"❌ Script not found: {script}")
            return False
        
        if not os.access(script, os.X_OK):
            print(f"❌ Script not executable: {script}")
            return False
        print(f"✅ Executable: {script}")
    
    return True


def test_kubernetes_manifests():
    """Test Kubernetes manifests syntax."""
    print("☸️ Testing Kubernetes manifests...")
    
    k8s_files = [
        "k8s/namespace.yaml",
        "k8s/configmap.yaml",
        "k8s/secret.yaml",
        "k8s/deployment.yaml",
        "k8s/service.yaml"
    ]
    
    for k8s_file in k8s_files:
        if not os.path.exists(k8s_file):
            print(f"❌ K8s manifest missing: {k8s_file}")
            return False
        
        # Basic YAML syntax check
        try:
            import yaml
            with open(k8s_file, 'r') as f:
                yaml.safe_load(f)
            print(f"✅ Valid YAML: {k8s_file}")
        except ImportError:
            print(f"⚠️ PyYAML not available, skipping YAML validation for {k8s_file}")
        except Exception as e:
            print(f"❌ YAML syntax error in {k8s_file}: {e}")
            return False
    
    return True


def main():
    """Run all tests."""
    print("🧪 Docker Containerization Test Suite")
    print("=====================================")
    print()
    
    tests = [
        ("Docker Prerequisites", test_docker_prerequisites),
        ("File Structure", test_file_structure),
        ("Dockerfile Syntax", test_dockerfile_syntax),
        ("Docker Compose Files", test_compose_files),
        ("Script Permissions", test_scripts_executable),
        ("Kubernetes Manifests", test_kubernetes_manifests),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n--- {test_name} ---")
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} PASSED")
            else:
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            print(f"❌ {test_name} ERROR: {e}")
    
    print()
    print("=" * 40)
    print(f"Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Docker containerization setup is complete.")
        return 0
    else:
        print("⚠️ Some tests failed. Please review the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())