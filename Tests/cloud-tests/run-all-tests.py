#!/usr/bin/env python3
"""
Cloud-Safe Test Suite Runner

This script runs all tests that can be executed in a cloud environment
without external dependencies or API calls.

Test Categories:
- Static UI analysis
- Configuration validation  
- Import/dependency analysis
- Mock data detection
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Dict, List, Any
import json

def run_cloud_test(script_path: Path, timeout: int = 300) -> Dict[str, Any]:
    """Run a cloud-safe test script and capture results."""
    result_info = {
        'script': script_path.name,
        'success': False,
        'output': '',
        'error': '',
        'return_code': None,
        'execution_time': 0
    }
    
    try:
        import time
        start_time = time.time()
        
        result = subprocess.run([sys.executable, str(script_path)], 
                               capture_output=True, text=True, timeout=timeout)
        
        result_info['execution_time'] = time.time() - start_time
        result_info['return_code'] = result.returncode
        result_info['output'] = result.stdout
        result_info['error'] = result.stderr
        result_info['success'] = result.returncode == 0
        
    except subprocess.TimeoutExpired:
        result_info['error'] = f"Test timed out after {timeout} seconds"
    except Exception as e:
        result_info['error'] = str(e)
    
    return result_info

def run_cloud_test_suite(project_root: Path) -> Dict[str, Any]:
    """Run all cloud-safe tests."""
    cloud_tests_dir = project_root / 'Tests' / 'cloud-tests'
    
    # Define test scripts and their descriptions
    test_scripts = [
        {
            'script': 'static-analysis.py',
            'name': 'UI Static Analysis',
            'description': 'Analyze UI component structure and complexity'
        },
        {
            'script': 'config-validation.py', 
            'name': 'Configuration Validation',
            'description': 'Validate YAML configuration structure and completeness'
        },
        {
            'script': 'import-checks.py',
            'name': 'Import Analysis',
            'description': 'Check import statements and dependency resolution'
        },
        {
            'script': 'quick-mock-scan.py',
            'name': 'Quick Mock Data Detection',
            'description': 'Quick scan for placeholder values and test data'
        }
    ]
    
    results = {
        'timestamp': str(Path(__file__).stat().st_mtime),
        'project_root': str(project_root),
        'total_tests': len(test_scripts),
        'passed_tests': 0,
        'failed_tests': 0,
        'total_execution_time': 0,
        'test_results': []
    }
    
    print("🔍 Running Cloud-Safe Test Suite")
    print("=" * 50)
    
    for test_info in test_scripts:
        script_path = cloud_tests_dir / test_info['script']
        
        if not script_path.exists():
            print(f"⚠️  Skipping {test_info['name']}: Script not found")
            continue
        
        print(f"🧪 Running {test_info['name']}...")
        print(f"   Description: {test_info['description']}")
        
        # Run the test
        test_result = run_cloud_test(script_path)
        test_result.update({
            'name': test_info['name'],
            'description': test_info['description']
        })
        
        results['total_execution_time'] += test_result['execution_time']
        
        if test_result['success']:
            results['passed_tests'] += 1
            print(f"   ✅ Completed in {test_result['execution_time']:.1f}s")
        else:
            results['failed_tests'] += 1
            print(f"   ❌ Failed after {test_result['execution_time']:.1f}s")
            if test_result['error']:
                print(f"   Error: {test_result['error'][:200]}...")
        
        results['test_results'].append(test_result)
        print()
    
    return results

def analyze_test_results(results: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze test results and extract key insights."""
    analysis = {
        'overall_status': 'unknown',
        'critical_issues': [],
        'warnings': [],
        'recommendations': [],
        'summary_stats': {}
    }
    
    # Determine overall status
    if results['failed_tests'] == 0:
        analysis['overall_status'] = 'passed'
    elif results['passed_tests'] > results['failed_tests']:
        analysis['overall_status'] = 'mostly_passed'
    else:
        analysis['overall_status'] = 'failed'
    
    # Extract insights from individual test outputs
    for test_result in results['test_results']:
        test_name = test_result.get('name', test_result['script'])
        
        if not test_result['success']:
            analysis['critical_issues'].append(f"{test_name} failed: {test_result['error'][:100]}...")
        
        # Extract specific insights from outputs
        output = test_result.get('output', '')
        
        if 'static-analysis' in test_result['script']:
            # Extract UI analysis insights
            if 'High complexity files' in output:
                analysis['warnings'].append("High complexity UI files detected")
            if 'Large files' in output:
                analysis['warnings'].append("Large UI files detected")
        
        elif 'config-validation' in test_result['script']:
            # Extract config insights
            if 'Placeholder values: 0' not in output:
                analysis['warnings'].append("Configuration contains placeholder values")
            if 'Valid configurations: 0' in output:
                analysis['critical_issues'].append("No valid configuration files found")
        
        elif 'import-checks' in test_result['script']:
            # Extract import insights
            if 'Unresolvable imports: 0' not in output:
                analysis['warnings'].append("Unresolvable imports detected")
        
        elif 'quick-mock-scan' in test_result['script']:
            # Extract mock data insights
            if 'Critical files: 0' not in output:
                analysis['critical_issues'].append("Critical mock data files detected")
            if 'Files with issues: 0' not in output:
                analysis['warnings'].append("Mock data patterns found")
    
    # Generate recommendations
    if analysis['critical_issues']:
        analysis['recommendations'].append("Address critical issues before production deployment")
    
    if analysis['warnings']:
        analysis['recommendations'].append("Review warnings for code quality improvements")
    
    if analysis['overall_status'] == 'passed':
        analysis['recommendations'].append("Cloud-safe analysis complete - ready for local testing")
    
    return analysis

def generate_summary_report(results: Dict[str, Any], analysis: Dict[str, Any]) -> str:
    """Generate a comprehensive summary report."""
    report = []
    report.append("# Cloud-Safe Test Suite Summary Report")
    report.append(f"**Generated**: {results['timestamp']}")
    report.append("")
    
    # Overall status
    status_icon = {
        'passed': '✅',
        'mostly_passed': '⚠️',
        'failed': '❌'
    }.get(analysis['overall_status'], '❓')
    
    report.append(f"## {status_icon} Overall Status: {analysis['overall_status'].upper()}")
    report.append("")
    
    # Summary statistics
    report.append("## 📊 Test Summary")
    report.append(f"- **Total Tests**: {results['total_tests']}")
    report.append(f"- **Passed**: {results['passed_tests']}")
    report.append(f"- **Failed**: {results['failed_tests']}")
    report.append(f"- **Total Execution Time**: {results['total_execution_time']:.1f} seconds")
    
    success_rate = (results['passed_tests'] / max(results['total_tests'], 1)) * 100
    report.append(f"- **Success Rate**: {success_rate:.1f}%")
    report.append("")
    
    # Critical issues
    if analysis['critical_issues']:
        report.append("## 🔥 Critical Issues")
        for issue in analysis['critical_issues']:
            report.append(f"- {issue}")
        report.append("")
    
    # Warnings
    if analysis['warnings']:
        report.append("## ⚠️ Warnings")
        for warning in analysis['warnings']:
            report.append(f"- {warning}")
        report.append("")
    
    # Individual test results
    report.append("## 📋 Test Results Details")
    for test_result in results['test_results']:
        status_icon = "✅" if test_result['success'] else "❌"
        report.append(f"### {status_icon} {test_result.get('name', test_result['script'])}")
        report.append(f"**Description**: {test_result.get('description', 'No description')}")
        report.append(f"**Execution Time**: {test_result['execution_time']:.1f} seconds")
        
        if test_result['success']:
            report.append("**Status**: Passed")
        else:
            report.append("**Status**: Failed")
            if test_result.get('error'):
                report.append(f"**Error**: {test_result['error'][:300]}...")
        
        report.append("")
    
    # Recommendations
    if analysis['recommendations']:
        report.append("## 💡 Recommendations")
        for rec in analysis['recommendations']:
            report.append(f"- {rec}")
        report.append("")
    
    # Next steps
    report.append("## 🚀 Next Steps")
    
    if analysis['overall_status'] == 'passed':
        report.append("1. **Review individual test reports** for detailed findings")
        report.append("2. **Address any warnings** for improved code quality")
        report.append("3. **Set up local environment** for integration testing")
        report.append("4. **Run local test suite** for complete validation")
    elif analysis['overall_status'] == 'mostly_passed':
        report.append("1. **Fix failed tests** before proceeding")
        report.append("2. **Address critical issues** identified")
        report.append("3. **Re-run test suite** to verify fixes")
        report.append("4. **Proceed with local testing** once all tests pass")
    else:
        report.append("1. **Address all test failures** immediately")
        report.append("2. **Review error messages** for specific fixes needed")
        report.append("3. **Re-run tests** until all pass")
        report.append("4. **Do not proceed to local testing** until cloud tests pass")
    
    report.append("")
    report.append("## 📄 Detailed Reports")
    report.append("Individual test reports are available in `Tests/cloud-tests/`:")
    report.append("- `ui-static-analysis-report.md` - UI component analysis")
    report.append("- `config-validation-report.md` - Configuration validation")
    report.append("- `import-analysis-report.md` - Import and dependency analysis")
    report.append("- `mock-data-analysis-report.md` - Mock data detection")
    report.append("")
    
    return "\n".join(report)

def main():
    """Main execution function."""
    # Find project root
    current_dir = Path(__file__).parent
    project_root = current_dir.parent.parent
    
    # Run cloud test suite
    results = run_cloud_test_suite(project_root)
    
    # Analyze results
    analysis = analyze_test_results(results)
    
    # Generate summary report
    report = generate_summary_report(results, analysis)
    
    # Save results
    output_dir = project_root / 'Tests' / 'cloud-tests'
    
    summary_file = output_dir / 'cloud-test-suite-summary.md'
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    data_file = output_dir / 'cloud-test-suite-data.json'
    with open(data_file, 'w', encoding='utf-8') as f:
        combined_data = {
            'results': results,
            'analysis': analysis
        }
        json.dump(combined_data, f, indent=2, default=str)
    
    # Print summary
    print("=" * 50)
    print(f"✅ Cloud-safe test suite complete!")
    print(f"📄 Summary report: {summary_file}")
    print(f"📊 Raw data: {data_file}")
    
    # Print final status
    status = analysis['overall_status']
    print(f"\n📊 Final Status: {status.upper()}")
    print(f"- Tests passed: {results['passed_tests']}/{results['total_tests']}")
    print(f"- Execution time: {results['total_execution_time']:.1f}s")
    
    if analysis['critical_issues']:
        print(f"- Critical issues: {len(analysis['critical_issues'])}")
    
    if analysis['warnings']:
        print(f"- Warnings: {len(analysis['warnings'])}")
    
    # Return appropriate exit code
    return 0 if results['failed_tests'] == 0 else 1

if __name__ == '__main__':
    sys.exit(main())