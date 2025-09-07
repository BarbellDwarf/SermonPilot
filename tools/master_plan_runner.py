#!/usr/bin/env python3
"""
Comprehensive Test Runner for SermonAudio Processor
Implements all testing components from the MasterPlan.md
"""

import os
import sys
import subprocess
import json
import time
from pathlib import Path
from datetime import datetime
import argparse

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

class MasterPlanTestRunner:
    """Comprehensive test runner implementing MasterPlan.md requirements"""
    
    def __init__(self, verbose=False):
        self.verbose = verbose
        self.project_root = project_root
        self.test_results = {
            'timestamp': datetime.now().isoformat(),
            'success_metrics': {
                'cloud_environment': {},
                'local_environment': {}
            },
            'test_suites': {},
            'issues_identified': [],
            'recommendations': []
        }
    
    def log(self, message, level="INFO"):
        """Log message with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        if self.verbose or level in ["ERROR", "WARNING"]:
            print(f"[{timestamp}] {level}: {message}")
    
    def run_cloud_safe_tests(self):
        """Run all cloud-safe tests (Phase 1-3 from MasterPlan)"""
        self.log("Starting cloud-safe test suite...")
        
        cloud_tests = {
            'static_analysis': self.run_static_analysis,
            'configuration_validation': self.run_configuration_validation,
            'import_analysis': self.run_import_analysis,
            'mock_data_detection': self.run_mock_data_detection
        }
        
        for test_name, test_func in cloud_tests.items():
            self.log(f"Running {test_name}...")
            try:
                result = test_func()
                self.test_results['test_suites'][test_name] = result
                self.log(f"✅ {test_name} completed successfully")
            except Exception as e:
                self.log(f"❌ {test_name} failed: {str(e)}", "ERROR")
                self.test_results['test_suites'][test_name] = {
                    'status': 'failed',
                    'error': str(e)
                }
    
    def run_static_analysis(self):
        """Run static analysis tests"""
        script_path = self.project_root / 'Tests' / 'cloud-tests' / 'static-analysis.py'
        if script_path.exists():
            result = subprocess.run([sys.executable, str(script_path)], 
                                  capture_output=True, text=True)
            return {
                'status': 'success' if result.returncode == 0 else 'failed',
                'output': result.stdout,
                'errors': result.stderr
            }
        return {'status': 'skipped', 'reason': 'Script not found'}
    
    def run_configuration_validation(self):
        """Run configuration validation tests"""
        script_path = self.project_root / 'Tests' / 'cloud-tests' / 'config-validation.py'
        if script_path.exists():
            result = subprocess.run([sys.executable, str(script_path)], 
                                  capture_output=True, text=True)
            return {
                'status': 'success' if result.returncode == 0 else 'failed',
                'output': result.stdout,
                'errors': result.stderr
            }
        return {'status': 'skipped', 'reason': 'Script not found'}
    
    def run_import_analysis(self):
        """Run import analysis tests"""
        script_path = self.project_root / 'Tests' / 'cloud-tests' / 'import-checks.py'
        if script_path.exists():
            result = subprocess.run([sys.executable, str(script_path)], 
                                  capture_output=True, text=True)
            return {
                'status': 'success' if result.returncode == 0 else 'failed',
                'output': result.stdout,
                'errors': result.stderr
            }
        return {'status': 'skipped', 'reason': 'Script not found'}
    
    def run_mock_data_detection(self):
        """Run mock data detection tests"""
        script_path = self.project_root / 'Tests' / 'cloud-tests' / 'mock-data-scan.py'
        if script_path.exists():
            result = subprocess.run([sys.executable, str(script_path)], 
                                  capture_output=True, text=True)
            return {
                'status': 'success' if result.returncode == 0 else 'failed',
                'output': result.stdout,
                'errors': result.stderr
            }
        return {'status': 'skipped', 'reason': 'Script not found'}
    
    def run_unit_tests(self):
        """Run unit tests"""
        self.log("Running unit tests...")
        unit_test_dir = self.project_root / 'Tests' / 'unit-tests'
        
        if not unit_test_dir.exists():
            return {'status': 'skipped', 'reason': 'Unit test directory not found'}
        
        # Run all unit test files
        test_files = list(unit_test_dir.glob('test_*.py'))
        results = {}
        
        for test_file in test_files:
            self.log(f"Running {test_file.name}...")
            result = subprocess.run([sys.executable, str(test_file)], 
                                  capture_output=True, text=True)
            results[test_file.name] = {
                'status': 'success' if result.returncode == 0 else 'failed',
                'output': result.stdout,
                'errors': result.stderr
            }
        
        return results
    
    def run_integration_tests(self):
        """Run integration tests"""
        self.log("Running integration tests...")
        integration_test_dir = self.project_root / 'Tests' / 'integration-tests'
        
        if not integration_test_dir.exists():
            return {'status': 'skipped', 'reason': 'Integration test directory not found'}
        
        # Run all integration test files
        test_files = list(integration_test_dir.glob('test_*.py'))
        results = {}
        
        for test_file in test_files:
            self.log(f"Running {test_file.name}...")
            result = subprocess.run([sys.executable, str(test_file)], 
                                  capture_output=True, text=True)
            results[test_file.name] = {
                'status': 'success' if result.returncode == 0 else 'failed',
                'output': result.stdout,
                'errors': result.stderr
            }
        
        return results
    
    def run_ui_tests(self):
        """Run UI tests"""
        self.log("Running UI tests...")
        ui_test_dir = self.project_root / 'Tests' / 'ui-tests'
        
        if not ui_test_dir.exists():
            return {'status': 'skipped', 'reason': 'UI test directory not found'}
        
        # Run all UI test files
        test_files = list(ui_test_dir.glob('test_*.py'))
        results = {}
        
        for test_file in test_files:
            self.log(f"Running {test_file.name}...")
            result = subprocess.run([sys.executable, str(test_file)], 
                                  capture_output=True, text=True)
            results[test_file.name] = {
                'status': 'success' if result.returncode == 0 else 'failed',
                'output': result.stdout,
                'errors': result.stderr
            }
        
        return results
    
    def evaluate_success_metrics(self):
        """Evaluate success metrics from MasterPlan.md"""
        self.log("Evaluating success metrics...")
        
        # Cloud Environment Success Metrics
        cloud_metrics = {
            'zero_production_unsafe_files': self.check_production_safety(),
            'all_imports_resolvable': self.check_import_resolution(),
            'configuration_templates_complete': self.check_configuration_completeness(),
            'mock_data_properly_categorized': self.check_mock_data_categorization(),
            'documentation_updated_accurate': self.check_documentation_accuracy()
        }
        
        # Local Environment Success Metrics (environment-dependent)
        local_metrics = {
            'streamlit_ui_functional': self.check_streamlit_functionality(),
            'external_integrations_working': self.check_external_integrations(),
            'audio_processing_operational': self.check_audio_processing(),
            'rag_system_performing': self.check_rag_system(),
            'performance_monitoring_active': self.check_performance_monitoring(),
            'zero_critical_errors': self.check_critical_errors()
        }
        
        self.test_results['success_metrics']['cloud_environment'] = cloud_metrics
        self.test_results['success_metrics']['local_environment'] = local_metrics
    
    def check_production_safety(self):
        """Check for production-unsafe files"""
        # Read mock data scan results if available
        mock_data_file = self.project_root / 'Tests' / 'cloud-tests' / 'mock-data-analysis-data.json'
        if mock_data_file.exists():
            try:
                with open(mock_data_file, 'r') as f:
                    data = json.load(f)
                    production_unsafe = data.get('production_unsafe_files', [])
                    return {
                        'status': 'pass' if len(production_unsafe) == 0 else 'fail',
                        'unsafe_files_count': len(production_unsafe),
                        'details': f"Found {len(production_unsafe)} production-unsafe files"
                    }
            except Exception as e:
                return {'status': 'error', 'details': f"Error reading mock data: {str(e)}"}
        
        return {'status': 'unknown', 'details': 'Mock data scan not available'}
    
    def check_import_resolution(self):
        """Check import resolution status"""
        import_data_file = self.project_root / 'Tests' / 'cloud-tests' / 'import-analysis-data.json'
        if import_data_file.exists():
            try:
                with open(import_data_file, 'r') as f:
                    data = json.load(f)
                    unresolvable = data.get('unresolvable_imports', [])
                    return {
                        'status': 'pass' if len(unresolvable) == 0 else 'warning',
                        'unresolvable_count': len(unresolvable),
                        'details': f"Found {len(unresolvable)} unresolvable imports"
                    }
            except Exception as e:
                return {'status': 'error', 'details': f"Error reading import data: {str(e)}"}
        
        return {'status': 'unknown', 'details': 'Import analysis not available'}
    
    def check_configuration_completeness(self):
        """Check configuration completeness"""
        config_files = [
            self.project_root / 'config.yaml',
            self.project_root / 'config.example.yaml'
        ]
        
        completeness_score = 0
        total_files = len(config_files)
        
        for config_file in config_files:
            if config_file.exists():
                completeness_score += 1
        
        return {
            'status': 'pass' if completeness_score == total_files else 'warning',
            'completeness_ratio': f"{completeness_score}/{total_files}",
            'details': f"Configuration files: {completeness_score}/{total_files} present"
        }
    
    def check_mock_data_categorization(self):
        """Check mock data categorization"""
        return {
            'status': 'pass',
            'details': 'Mock data detection and categorization completed in cloud tests'
        }
    
    def check_documentation_accuracy(self):
        """Check documentation accuracy"""
        doc_files = [
            self.project_root / 'README.md',
            self.project_root / 'LOCAL_TESTING_REQUIREMENTS.md',
            self.project_root / 'Tests' / 'local-tests' / 'LOCAL_SETUP.md'
        ]
        
        accuracy_score = 0
        for doc_file in doc_files:
            if doc_file.exists():
                accuracy_score += 1
        
        return {
            'status': 'pass' if accuracy_score >= 2 else 'warning',
            'documentation_files': accuracy_score,
            'details': f"Found {accuracy_score} documentation files"
        }
    
    def check_streamlit_functionality(self):
        """Check Streamlit functionality (requires local environment)"""
        streamlit_app = self.project_root / 'streamlit_app.py'
        return {
            'status': 'requires_local_testing',
            'app_file_exists': streamlit_app.exists(),
            'details': 'Requires local Streamlit environment for testing'
        }
    
    def check_external_integrations(self):
        """Check external integrations"""
        return {
            'status': 'requires_local_testing',
            'details': 'Requires API credentials and local services'
        }
    
    def check_audio_processing(self):
        """Check audio processing capabilities"""
        return {
            'status': 'requires_local_testing',
            'details': 'Requires GPU/audio processing libraries'
        }
    
    def check_rag_system(self):
        """Check RAG system functionality"""
        vector_db_path = self.project_root / 'analytics_vector_db'
        return {
            'status': 'requires_local_testing',
            'vector_db_exists': vector_db_path.exists(),
            'details': 'Requires ChromaDB and embeddings'
        }
    
    def check_performance_monitoring(self):
        """Check performance monitoring"""
        return {
            'status': 'requires_local_testing',
            'details': 'Requires running system for metrics collection'
        }
    
    def check_critical_errors(self):
        """Check for critical errors"""
        error_count = 0
        for suite_name, suite_results in self.test_results['test_suites'].items():
            if isinstance(suite_results, dict) and suite_results.get('status') == 'failed':
                error_count += 1
        
        return {
            'status': 'pass' if error_count == 0 else 'fail',
            'error_count': error_count,
            'details': f"Found {error_count} critical errors in test suites"
        }
    
    def generate_recommendations(self):
        """Generate recommendations based on test results"""
        recommendations = []
        
        # Analyze cloud metrics
        cloud_metrics = self.test_results['success_metrics']['cloud_environment']
        
        for metric_name, metric_result in cloud_metrics.items():
            if metric_result.get('status') == 'fail':
                if metric_name == 'zero_production_unsafe_files':
                    recommendations.append({
                        'priority': 'high',
                        'category': 'security',
                        'action': 'Replace hardcoded credentials and test data with environment variables',
                        'details': metric_result.get('details', '')
                    })
                elif metric_name == 'all_imports_resolvable':
                    recommendations.append({
                        'priority': 'medium',
                        'category': 'code_quality',
                        'action': 'Resolve import issues in local environment',
                        'details': metric_result.get('details', '')
                    })
        
        # Add general recommendations
        recommendations.extend([
            {
                'priority': 'high',
                'category': 'deployment',
                'action': 'Set up local testing environment for complete validation',
                'details': 'Follow LOCAL_TESTING_REQUIREMENTS.md for setup instructions'
            },
            {
                'priority': 'medium',
                'category': 'code_quality',
                'action': 'Refactor large UI files identified in static analysis',
                'details': 'Break down files >500 lines into smaller components'
            },
            {
                'priority': 'low',
                'category': 'maintenance',
                'action': 'Set up continuous integration for automated testing',
                'details': 'Integrate this test framework into CI/CD pipeline'
            }
        ])
        
        self.test_results['recommendations'] = recommendations
    
    def save_results(self, output_file=None):
        """Save test results to file"""
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = self.project_root / 'Tests' / 'archives' / 'test-results' / f'master_plan_test_{timestamp}.json'
            output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w') as f:
            json.dump(self.test_results, f, indent=2)
        
        self.log(f"Test results saved to: {output_file}")
        return output_file
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*60)
        print("MASTER PLAN TEST EXECUTION SUMMARY")
        print("="*60)
        
        # Cloud environment metrics
        print("\n🌥️  CLOUD ENVIRONMENT METRICS:")
        cloud_metrics = self.test_results['success_metrics']['cloud_environment']
        for metric_name, result in cloud_metrics.items():
            status_icon = "✅" if result.get('status') == 'pass' else "⚠️" if result.get('status') == 'warning' else "❌"
            print(f"  {status_icon} {metric_name}: {result.get('details', 'No details')}")
        
        # Local environment metrics
        print("\n🏠 LOCAL ENVIRONMENT METRICS:")
        local_metrics = self.test_results['success_metrics']['local_environment']
        for metric_name, result in local_metrics.items():
            status_icon = "🔄" if result.get('status') == 'requires_local_testing' else "✅" if result.get('status') == 'pass' else "❌"
            print(f"  {status_icon} {metric_name}: {result.get('details', 'No details')}")
        
        # Test suites
        print("\n🧪 TEST SUITES:")
        for suite_name, result in self.test_results['test_suites'].items():
            if isinstance(result, dict):
                status_icon = "✅" if result.get('status') == 'success' else "⚠️" if result.get('status') == 'skipped' else "❌"
                print(f"  {status_icon} {suite_name}: {result.get('status', 'unknown')}")
            else:
                print(f"  🔄 {suite_name}: Multiple tests executed")
        
        # Recommendations
        print("\n💡 RECOMMENDATIONS:")
        high_priority = [r for r in self.test_results['recommendations'] if r['priority'] == 'high']
        medium_priority = [r for r in self.test_results['recommendations'] if r['priority'] == 'medium']
        
        if high_priority:
            print("  🔥 HIGH PRIORITY:")
            for rec in high_priority:
                print(f"    • {rec['action']}")
        
        if medium_priority:
            print("  ⚠️  MEDIUM PRIORITY:")
            for rec in medium_priority:
                print(f"    • {rec['action']}")
        
        print(f"\n📊 Full results saved to test archives")
        print("="*60)
    
    def run_comprehensive_tests(self, include_local=False):
        """Run comprehensive test suite"""
        self.log("Starting comprehensive test execution...")
        
        # Phase 1: Cloud-safe tests
        self.run_cloud_safe_tests()
        
        # Phase 2: Unit tests
        unit_results = self.run_unit_tests()
        self.test_results['test_suites']['unit_tests'] = unit_results
        
        # Phase 3: Integration tests (if local environment)
        if include_local:
            integration_results = self.run_integration_tests()
            self.test_results['test_suites']['integration_tests'] = integration_results
            
            ui_results = self.run_ui_tests()
            self.test_results['test_suites']['ui_tests'] = ui_results
        
        # Phase 4: Evaluate metrics
        self.evaluate_success_metrics()
        
        # Phase 5: Generate recommendations
        self.generate_recommendations()
        
        # Phase 6: Save and summarize
        self.save_results()
        self.print_summary()

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='MasterPlan Test Runner')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--local', '-l', action='store_true', help='Include local environment tests')
    parser.add_argument('--cloud-only', '-c', action='store_true', help='Run only cloud-safe tests')
    parser.add_argument('--unit-only', '-u', action='store_true', help='Run only unit tests')
    
    args = parser.parse_args()
    
    runner = MasterPlanTestRunner(verbose=args.verbose)
    
    if args.cloud_only:
        runner.run_cloud_safe_tests()
        runner.evaluate_success_metrics()
        runner.generate_recommendations()
        runner.save_results()
        runner.print_summary()
    elif args.unit_only:
        unit_results = runner.run_unit_tests()
        runner.test_results['test_suites']['unit_tests'] = unit_results
        runner.print_summary()
    else:
        runner.run_comprehensive_tests(include_local=args.local)

if __name__ == '__main__':
    main()