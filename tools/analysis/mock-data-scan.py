#!/usr/bin/env python3
"""
Mock Data Scanner for SermonAudio Processor

This script identifies mock data, placeholder values, and hardcoded test data
throughout the project without executing any code.

Scans for:
- Hardcoded test data and placeholder values
- Mock API responses and demo data
- Development-only data that shouldn't be in production
- Test fixtures that should be moved to test directories
"""

import os
import sys
import re
import json
from pathlib import Path
from typing import Dict, List, Any, Set
import ast

def scan_file_for_mock_data(file_path: Path) -> Dict[str, Any]:
    """Scan a single file for mock data patterns."""
    mock_data_info = {
        'file_path': str(file_path),
        'file_type': file_path.suffix,
        'mock_patterns': [],
        'placeholder_values': [],
        'hardcoded_data': [],
        'demo_data': [],
        'test_fixtures': [],
        'suspicious_strings': []
    }
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            lines = content.splitlines()
        
        # Define patterns for different types of mock data
        patterns = {
            'placeholder_values': [
                r'your-.*-key',
                r'your-.*-id', 
                r'.*-here',
                r'placeholder',
                r'replace.*',
                r'example\..*',
                r'test-.*-key',
                r'demo-.*',
                r'fake-.*',
                r'mock-.*',
                r'localhost.*11434',  # Ollama default
                r'api\.openai\.com',  # Might be placeholder
                r'127\.0\.0\.1',
                r'0\.0\.0\.0'
            ],
            'mock_api_responses': [
                r'mock.*response',
                r'fake.*response',
                r'dummy.*data',
                r'sample.*response',
                r'test.*response',
                r'placeholder.*response'
            ],
            'demo_data': [
                r'demo.*sermon',
                r'sample.*sermon',
                r'test.*sermon',
                r'example.*sermon',
                r'dummy.*content',
                r'lorem.*ipsum',
                r'sample.*title',
                r'test.*title',
                r'demo.*title'
            ],
            'hardcoded_test_data': [
                r'12345',
                r'test.*test',
                r'example.*example',
                r'temp.*temp',
                r'abc.*123',
                r'foo.*bar',
                r'hello.*world'
            ],
            'suspicious_credentials': [
                r'sk-[a-zA-Z0-9]{32,}',  # OpenAI API key pattern
                r'xai-[a-zA-Z0-9]{32,}',  # xAI API key pattern
                r'[A-Za-z0-9]{32,50}',   # Generic long strings (might be keys)
                r'[a-f0-9]{32,64}',      # Hex strings (might be tokens)
            ]
        }
        
        # Scan line by line
        for line_num, line in enumerate(lines, 1):
            line_lower = line.lower()
            
            # Check for various mock data patterns
            for pattern_type, pattern_list in patterns.items():
                for pattern in pattern_list:
                    matches = re.finditer(pattern, line, re.IGNORECASE)
                    for match in matches:
                        mock_data_info['mock_patterns'].append({
                            'type': pattern_type,
                            'pattern': pattern,
                            'match': match.group(),
                            'line': line_num,
                            'context': line.strip()
                        })
            
            # Special checks for specific content types
            
            # Look for obvious placeholder values
            if any(word in line_lower for word in ['placeholder', 'replace', 'your-', 'example', 'demo', 'test-']):
                mock_data_info['placeholder_values'].append({
                    'line': line_num,
                    'content': line.strip(),
                    'reason': 'Contains placeholder keywords'
                })
            
            # Look for hardcoded IDs or data that looks like test data
            if re.search(r'(id|key|token).*[\'"][0-9a-f]{8,}[\'"]', line, re.IGNORECASE):
                mock_data_info['hardcoded_data'].append({
                    'line': line_num,
                    'content': line.strip(),
                    'reason': 'Contains hardcoded ID/key/token'
                })
            
            # Look for demo/sample content
            if any(word in line_lower for word in ['demo', 'sample', 'example', 'dummy', 'lorem ipsum']):
                mock_data_info['demo_data'].append({
                    'line': line_num,
                    'content': line.strip(),
                    'reason': 'Contains demo/sample keywords'
                })
        
        # Additional Python-specific analysis for .py files
        if file_path.suffix == '.py':
            try:
                tree = ast.parse(content)
                
                # Look for variables with suspicious names or values
                for node in ast.walk(tree):
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name):
                                var_name = target.id.lower()
                                if any(word in var_name for word in ['mock', 'fake', 'demo', 'test', 'sample', 'placeholder']):
                                    mock_data_info['test_fixtures'].append({
                                        'type': 'variable',
                                        'name': target.id,
                                        'line': node.lineno,
                                        'reason': 'Variable name suggests test/mock data'
                                    })
                    
                    elif isinstance(node, ast.FunctionDef):
                        func_name = node.name.lower()
                        if any(word in func_name for word in ['mock', 'fake', 'demo', 'test', 'sample']):
                            mock_data_info['test_fixtures'].append({
                                'type': 'function',
                                'name': node.name,
                                'line': node.lineno,
                                'reason': 'Function name suggests test/mock functionality'
                            })
                    
                    elif isinstance(node, ast.Constant) and isinstance(node.value, str):  # String constants (Python 3.8+)
                        str_value = node.value.lower()
                        if len(str_value) > 10 and any(word in str_value for word in ['test', 'demo', 'sample', 'placeholder', 'example']):
                            mock_data_info['suspicious_strings'].append({
                                'value': node.value[:100] + ('...' if len(node.value) > 100 else ''),
                                'line': node.lineno,
                                'reason': 'String contains test/demo keywords'
                            })
            
            except SyntaxError:
                pass  # Skip files with syntax errors
    
    except Exception as e:
        mock_data_info['error'] = str(e)
    
    return mock_data_info

def categorize_mock_data(mock_data_info: Dict[str, Any]) -> Dict[str, str]:
    """Categorize mock data by severity and action needed."""
    categorization = {
        'severity': 'low',
        'action': 'review',
        'production_safe': True,
        'reasons': []
    }
    
    # Count different types of mock data
    mock_count = len(mock_data_info.get('mock_patterns', []))
    placeholder_count = len(mock_data_info.get('placeholder_values', []))
    hardcoded_count = len(mock_data_info.get('hardcoded_data', []))
    demo_count = len(mock_data_info.get('demo_data', []))
    test_fixture_count = len(mock_data_info.get('test_fixtures', []))
    
    total_issues = mock_count + placeholder_count + hardcoded_count + demo_count + test_fixture_count
    
    # Determine severity
    if total_issues == 0:
        categorization['severity'] = 'none'
        categorization['action'] = 'none'
    elif total_issues <= 2:
        categorization['severity'] = 'low'
        categorization['action'] = 'review'
    elif total_issues <= 5:
        categorization['severity'] = 'medium'
        categorization['action'] = 'fix'
    else:
        categorization['severity'] = 'high'
        categorization['action'] = 'immediate_fix'
        categorization['production_safe'] = False
    
    # Check for specific high-risk patterns
    for pattern in mock_data_info.get('mock_patterns', []):
        if pattern['type'] == 'suspicious_credentials':
            categorization['severity'] = 'critical'
            categorization['action'] = 'immediate_fix'
            categorization['production_safe'] = False
            categorization['reasons'].append('Contains potential credentials')
    
    if hardcoded_count > 0:
        categorization['reasons'].append(f'Contains {hardcoded_count} hardcoded values')
    
    if placeholder_count > 0:
        categorization['reasons'].append(f'Contains {placeholder_count} placeholder values')
    
    if demo_count > 0:
        categorization['reasons'].append(f'Contains {demo_count} demo/sample references')
    
    return categorization

def scan_project_for_mock_data(project_root: Path) -> Dict[str, Any]:
    """Scan the entire project for mock data."""
    analysis = {
        'timestamp': str(Path(__file__).stat().st_mtime),
        'project_root': str(project_root),
        'files': {},
        'summary': {
            'total_files_scanned': 0,
            'files_with_mock_data': 0,
            'high_risk_files': 0,
            'total_mock_patterns': 0,
            'total_placeholders': 0,
            'production_unsafe_files': 0,
            'categories': {
                'critical': 0,
                'high': 0,
                'medium': 0,
                'low': 0,
                'none': 0
            }
        }
    }
    
    # Define file types and directories to scan
    scan_extensions = {'.py', '.yaml', '.yml', '.json', '.md', '.txt', '.cfg', '.ini', '.toml'}
    exclude_dirs = {'__pycache__', '.git', '.pytest_cache', 'node_modules', '.venv', 'venv', 'analytics_vector_db'}
    exclude_files = {'uv.lock'}  # Skip large lock files
    
    # Find files to scan
    files_to_scan = []
    for root, dirs, files in os.walk(project_root):
        # Remove excluded directories
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        for file in files:
            file_path = Path(root) / file
            if file_path.suffix in scan_extensions and file_path.name not in exclude_files:
                files_to_scan.append(file_path)
    
    # Scan each file
    for file_path in files_to_scan:
        mock_data_info = scan_file_for_mock_data(file_path)
        categorization = categorize_mock_data(mock_data_info)
        
        analysis['files'][str(file_path)] = {
            'mock_data': mock_data_info,
            'categorization': categorization
        }
        
        analysis['summary']['total_files_scanned'] += 1
        
        # Update summary statistics
        if categorization['severity'] != 'none':
            analysis['summary']['files_with_mock_data'] += 1
        
        if categorization['severity'] in ['high', 'critical']:
            analysis['summary']['high_risk_files'] += 1
        
        if not categorization['production_safe']:
            analysis['summary']['production_unsafe_files'] += 1
        
        analysis['summary']['categories'][categorization['severity']] += 1
        analysis['summary']['total_mock_patterns'] += len(mock_data_info.get('mock_patterns', []))
        analysis['summary']['total_placeholders'] += len(mock_data_info.get('placeholder_values', []))
    
    return analysis

def generate_mock_data_report(analysis: Dict[str, Any]) -> str:
    """Generate a human-readable mock data analysis report."""
    report = []
    report.append("# SermonAudio Processor Mock Data Analysis Report")
    report.append(f"**Generated**: {analysis['timestamp']}")
    report.append("")
    
    # Summary
    summary = analysis['summary']
    report.append("## 📊 Summary")
    report.append(f"- **Total Files Scanned**: {summary['total_files_scanned']}")
    report.append(f"- **Files with Mock Data**: {summary['files_with_mock_data']}")
    report.append(f"- **High Risk Files**: {summary['high_risk_files']}")
    report.append(f"- **Production Unsafe Files**: {summary['production_unsafe_files']}")
    report.append(f"- **Total Mock Patterns**: {summary['total_mock_patterns']}")
    report.append(f"- **Total Placeholders**: {summary['total_placeholders']}")
    report.append("")
    
    # Risk categories
    report.append("## 🚨 Risk Categories")
    categories = summary['categories']
    report.append(f"- **Critical**: {categories['critical']} files")
    report.append(f"- **High**: {categories['high']} files")
    report.append(f"- **Medium**: {categories['medium']} files")
    report.append(f"- **Low**: {categories['low']} files")
    report.append(f"- **Clean**: {categories['none']} files")
    report.append("")
    
    # High priority files
    high_priority_files = []
    medium_priority_files = []
    
    for file_path, file_info in analysis['files'].items():
        severity = file_info['categorization']['severity']
        if severity in ['critical', 'high']:
            high_priority_files.append((file_path, file_info))
        elif severity == 'medium':
            medium_priority_files.append((file_path, file_info))
    
    if high_priority_files:
        report.append("## 🔥 High Priority Files (Immediate Action Required)")
        for file_path, file_info in high_priority_files:
            file_name = Path(file_path).name
            categorization = file_info['categorization']
            report.append(f"### {file_name}")
            report.append(f"- **Severity**: {categorization['severity'].upper()}")
            report.append(f"- **Action**: {categorization['action']}")
            report.append(f"- **Production Safe**: {'Yes' if categorization['production_safe'] else 'No'}")
            
            if categorization['reasons']:
                report.append("- **Issues**:")
                for reason in categorization['reasons']:
                    report.append(f"  - {reason}")
            
            # Show some examples
            mock_data = file_info['mock_data']
            examples = []
            
            for pattern in mock_data.get('mock_patterns', [])[:3]:  # First 3 examples
                examples.append(f"Line {pattern['line']}: {pattern['match']}")
            
            for placeholder in mock_data.get('placeholder_values', [])[:2]:  # First 2 examples
                examples.append(f"Line {placeholder['line']}: Placeholder detected")
            
            if examples:
                report.append("- **Examples**:")
                for example in examples:
                    report.append(f"  - {example}")
            
            report.append("")
    
    if medium_priority_files:
        report.append("## ⚠️ Medium Priority Files (Review Recommended)")
        for file_path, file_info in medium_priority_files[:10]:  # Limit to first 10
            file_name = Path(file_path).name
            categorization = file_info['categorization']
            reason_summary = ', '.join(categorization['reasons'][:2])  # First 2 reasons
            report.append(f"- `{file_name}`: {reason_summary}")
        report.append("")
    
    # Replacement strategy
    report.append("## 🔧 Mock Data Replacement Strategy")
    report.append("")
    report.append("### Immediate Actions (Critical/High)")
    report.append("1. **Review credential placeholders** - Replace with environment variables")
    report.append("2. **Remove hardcoded test data** - Move to test fixtures or configuration")
    report.append("3. **Replace demo content** - Use real or configurable content")
    report.append("")
    
    report.append("### Medium Term Actions (Medium/Low)")
    report.append("1. **Standardize placeholder patterns** - Use consistent naming")
    report.append("2. **Create configuration templates** - Separate example configs from working configs")
    report.append("3. **Move test fixtures** - Relocate to appropriate test directories")
    report.append("")
    
    # Recommendations
    report.append("## 💡 Recommendations")
    
    if summary['production_unsafe_files'] > 0:
        report.append("- **URGENT**: Fix production-unsafe files before deployment")
    
    if summary['high_risk_files'] > 0:
        report.append("- Review and address all high-risk files")
    
    if summary['total_placeholders'] > 10:
        report.append("- Create environment variable configuration system")
    
    report.append("- Implement mock data scanning in CI/CD pipeline")
    report.append("- Document placeholder replacement procedures")
    report.append("- Create development vs production configuration guides")
    report.append("")
    
    return "\n".join(report)

def main():
    """Run mock data analysis."""
    # Find project root
    current_dir = Path(__file__).parent
    project_root = current_dir.parent.parent
    
    print("🔍 Starting mock data analysis...")
    
    # Analyze mock data
    analysis = scan_project_for_mock_data(project_root)
    
    # Generate report
    report = generate_mock_data_report(analysis)
    
    # Save results
    output_dir = project_root / 'Tests' / 'cloud-tests'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    report_file = output_dir / 'mock-data-analysis-report.md'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    json_file = output_dir / 'mock-data-analysis-data.json'
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, indent=2, default=str)
    
    print(f"✅ Mock data analysis complete!")
    print(f"📄 Report saved to: {report_file}")
    print(f"📊 Raw data saved to: {json_file}")
    
    # Print summary
    summary = analysis['summary']
    print(f"\n📊 Summary:")
    print(f"- Files scanned: {summary['total_files_scanned']}")
    print(f"- Files with mock data: {summary['files_with_mock_data']}")
    print(f"- High risk files: {summary['high_risk_files']}")
    print(f"- Production unsafe files: {summary['production_unsafe_files']}")
    
    return 0 if summary['production_unsafe_files'] == 0 else 1

if __name__ == '__main__':
    sys.exit(main())