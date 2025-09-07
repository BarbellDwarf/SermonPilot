#!/usr/bin/env python3
"""
Local Test Runner for SermonAudio Processor

This script orchestrates local testing for components that require external dependencies.
It checks the environment first, then runs appropriate test suites based on availability.

Test categories:
- Environment verification
- API integration tests
- UI functionality tests  
- Audio processing tests
- RAG system tests
"""

import sys
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Any

def load_environment_status(project_root: Path) -> Dict[str, Any]:
    """Load environment check results if available."""
    env_check_file = project_root / 'Tests' / 'local-tests' / 'environment-check-data.json'
    
    if env_check_file.exists():
        try:
            with open(env_check_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️  Failed to load environment check data: {e}")
            return {}
    
    print("⚠️  No environment check data found. Running environment check first...")
    return {}

def run_environment_check(project_root: Path) -> Dict[str, Any]:
    """Run environment check and return results."""
    env_check_script = project_root / 'Tests' / 'local-tests' / 'environment-check.py'
    
    try:
        result = subprocess.run([sys.executable, str(env_check_script)], 
                               capture_output=True, text=True, timeout=300)
        
        # Load the results
        return load_environment_status(project_root)
    
    except subprocess.TimeoutExpired:
        print("❌ Environment check timed out")
        return {'overall_status': 'failed'}
    except Exception as e:
        print(f"❌ Environment check failed: {e}")
        return {'overall_status': 'failed'}

def run_test_script(script_path: Path, timeout: int = 300) -> Dict[str, Any]:
    """Run a test script and capture results."""
    result_info = {
        'script': script_path.name,
        'success': False,
        'output': '',
        'error': '',
        'return_code': None
    }
    
    try:
        result = subprocess.run([sys.executable, str(script_path)], 
                               capture_output=True, text=True, timeout=timeout)
        
        result_info['return_code'] = result.returncode
        result_info['output'] = result.stdout
        result_info['error'] = result.stderr
        result_info['success'] = result.returncode == 0
        
    except subprocess.TimeoutExpired:
        result_info['error'] = f"Test timed out after {timeout} seconds"
    except Exception as e:
        result_info['error'] = str(e)
    
    return result_info

def determine_runnable_tests(env_status: Dict[str, Any], tests_dir: Path) -> List[Dict[str, Any]]:
    """Determine which tests can be run based on environment status."""
    available_tests = []
    
    # Define test requirements
    test_requirements = {
        'api-integration-tests.py': {
            'requires': ['config_valid', 'has_api_credentials'],
            'optional': ['ollama_accessible'],
            'description': 'SermonAudio API and LLM provider integration'
        },
        'ui-functionality-tests.py': {
            'requires': ['streamlit_available', 'config_valid'],
            'optional': [],
            'description': 'Streamlit UI component functionality'
        },
        'audio-processing-tests.py': {
            'requires': ['audio_libraries_available'],
            'optional': ['gpu_available', 'deepfilternet_available'],
            'description': 'Audio processing pipeline and AI enhancement'
        },
        'rag-system-tests.py': {
            'requires': ['chromadb_available', 'sentence_transformers_available'],
            'optional': [],
            'description': 'Vector database and semantic search'
        }
    }
    
    overall_status = env_status.get('overall_status', 'unknown')
    
    for test_file, requirements in test_requirements.items():
        test_path = tests_dir / test_file
        
        can_run = True
        missing_requirements = []
        limited_functionality = []
        
        # Check if test file exists
        if not test_path.exists():
            can_run = False
            missing_requirements.append(f"Test file {test_file} not found")
        
        # Check requirements based on environment status
        if overall_status == 'failed':
            can_run = False
            missing_requirements.append("Environment check failed")
        
        # More detailed requirement checking would go here
        # For now, we'll use simplified logic based on overall status
        
        available_tests.append({
            'file': test_file,
            'path': test_path,
            'can_run': can_run,
            'description': requirements['description'],
            'missing_requirements': missing_requirements,
            'limited_functionality': limited_functionality,
            'priority': 'high' if can_run else 'low'
        })
    
    return available_tests

def generate_test_plan(available_tests: List[Dict[str, Any]]) -> str:
    """Generate a test execution plan."""
    plan = []
    plan.append("# Local Test Execution Plan")
    plan.append("")
    
    runnable_tests = [t for t in available_tests if t['can_run']]
    blocked_tests = [t for t in available_tests if not t['can_run']]
    
    plan.append(f"## ✅ Runnable Tests ({len(runnable_tests)})")
    for test in runnable_tests:
        plan.append(f"- **{test['file']}**: {test['description']}")
        if test['limited_functionality']:
            plan.append(f"  - ⚠️  Limited: {', '.join(test['limited_functionality'])}")
    plan.append("")
    
    if blocked_tests:
        plan.append(f"## ❌ Blocked Tests ({len(blocked_tests)})")
        for test in blocked_tests:
            plan.append(f"- **{test['file']}**: {test['description']}")
            for req in test['missing_requirements']:
                plan.append(f"  - Missing: {req}")
        plan.append("")
    
    return "\n".join(plan)

def run_test_suite(available_tests: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run all available tests and collect results."""
    results = {
        'timestamp': str(Path(__file__).stat().st_mtime),
        'total_tests': len(available_tests),
        'runnable_tests': 0,
        'passed_tests': 0,
        'failed_tests': 0,
        'skipped_tests': 0,
        'test_results': []
    }
    
    for test_info in available_tests:
        if test_info['can_run']:
            results['runnable_tests'] += 1
            print(f"🧪 Running {test_info['file']}...")
            
            test_result = run_test_script(test_info['path'])
            test_result.update({
                'description': test_info['description'],
                'skipped': False
            })
            
            if test_result['success']:
                results['passed_tests'] += 1
                print(f"   ✅ {test_info['file']} passed")
            else:
                results['failed_tests'] += 1
                print(f"   ❌ {test_info['file']} failed")
                if test_result['error']:
                    print(f"      Error: {test_result['error'][:200]}...")
        
        else:
            results['skipped_tests'] += 1
            test_result = {
                'script': test_info['file'],
                'success': False,
                'skipped': True,
                'description': test_info['description'],
                'skip_reason': ', '.join(test_info['missing_requirements'])
            }
            print(f"⏭️  Skipping {test_info['file']}: {test_result['skip_reason']}")
        
        results['test_results'].append(test_result)
    
    return results

def generate_test_report(results: Dict[str, Any]) -> str:
    """Generate a test execution report."""
    report = []
    report.append("# Local Test Execution Report")
    report.append(f"**Generated**: {results['timestamp']}")
    report.append("")
    
    # Summary
    report.append("## 📊 Test Summary")
    report.append(f"- **Total Tests**: {results['total_tests']}")
    report.append(f"- **Runnable Tests**: {results['runnable_tests']}")
    report.append(f"- **Passed**: {results['passed_tests']}")
    report.append(f"- **Failed**: {results['failed_tests']}")
    report.append(f"- **Skipped**: {results['skipped_tests']}")
    
    success_rate = (results['passed_tests'] / max(results['runnable_tests'], 1)) * 100
    report.append(f"- **Success Rate**: {success_rate:.1f}%")
    report.append("")
    
    # Detailed results
    report.append("## 📋 Detailed Results")
    
    for test_result in results['test_results']:
        status_icon = "✅" if test_result['success'] else "⏭️" if test_result.get('skipped') else "❌"
        report.append(f"### {status_icon} {test_result['script']}")
        report.append(f"**Description**: {test_result.get('description', 'No description')}")
        
        if test_result.get('skipped'):
            report.append(f"**Skipped**: {test_result.get('skip_reason', 'Unknown reason')}")
        elif test_result['success']:
            report.append("**Status**: Passed")
        else:
            report.append("**Status**: Failed")
            if test_result.get('error'):
                report.append(f"**Error**: {test_result['error'][:300]}...")
        
        report.append("")
    
    # Recommendations
    report.append("## 💡 Recommendations")
    
    if results['failed_tests'] > 0:
        report.append("- Review failed test outputs for specific issues")
        report.append("- Check environment configuration and dependencies")
    
    if results['skipped_tests'] > 0:
        report.append("- Address missing requirements to enable skipped tests")
        report.append("- Run environment check and fix identified issues")
    
    if results['passed_tests'] == results['runnable_tests'] and results['runnable_tests'] > 0:
        report.append("- All runnable tests passed! Environment is ready for development")
        report.append("- Consider running manual UI testing with Streamlit")
    
    report.append("")
    
    return "\n".join(report)

def main():
    """Main test runner execution."""
    # Find project root
    current_dir = Path(__file__).parent
    project_root = current_dir.parent.parent
    tests_dir = current_dir
    
    print("🚀 SermonAudio Processor Local Test Runner")
    print("=" * 50)
    
    # Load or run environment check
    env_status = load_environment_status(project_root)
    
    if not env_status or env_status.get('overall_status') == 'unknown':
        print("🔍 Running environment check...")
        env_status = run_environment_check(project_root)
    
    if not env_status:
        print("❌ Failed to get environment status")
        return 1
    
    overall_status = env_status.get('overall_status', 'unknown')
    print(f"📊 Environment Status: {overall_status.upper()}")
    
    # Determine available tests
    available_tests = determine_runnable_tests(env_status, tests_dir)
    
    # Generate and display test plan
    test_plan = generate_test_plan(available_tests)
    print(f"\n{test_plan}")
    
    # Ask user if they want to proceed
    runnable_count = len([t for t in available_tests if t['can_run']])
    
    if runnable_count == 0:
        print("❌ No tests can be run with current environment")
        print("💡 Run environment check and fix issues before testing")
        return 1
    
    proceed = input(f"\n🧪 Run {runnable_count} available tests? (y/N): ").lower().strip()
    
    if proceed != 'y':
        print("⏸️  Test execution cancelled")
        return 0
    
    # Run test suite
    print(f"\n🧪 Running {runnable_count} tests...")
    print("=" * 50)
    
    results = run_test_suite(available_tests)
    
    # Generate and save report
    report = generate_test_report(results)
    
    output_dir = project_root / 'Tests' / 'local-tests'
    report_file = output_dir / 'test-execution-report.md'
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    json_file = output_dir / 'test-execution-data.json'
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, default=str)
    
    print("\n" + "=" * 50)
    print(f"✅ Test execution complete!")
    print(f"📄 Report saved to: {report_file}")
    print(f"📊 Data saved to: {json_file}")
    
    # Print final summary
    success_rate = (results['passed_tests'] / max(results['runnable_tests'], 1)) * 100
    print(f"\n📊 Final Summary:")
    print(f"- Tests run: {results['runnable_tests']}")
    print(f"- Passed: {results['passed_tests']}")
    print(f"- Failed: {results['failed_tests']}")
    print(f"- Success rate: {success_rate:.1f}%")
    
    return 0 if results['failed_tests'] == 0 else 1

if __name__ == '__main__':
    sys.exit(main())