#!/usr/bin/env python3
"""
Simplified Mock Data Scanner for SermonAudio Processor

A more efficient version that focuses on the most critical mock data patterns
without deep AST analysis that might cause performance issues.
"""

import os
import sys
import re
import json
from pathlib import Path
from typing import Dict, List, Any

def scan_file_for_critical_patterns(file_path: Path) -> Dict[str, Any]:
    """Scan a file for critical mock data patterns using simple text analysis."""
    patterns = {
        'placeholder_patterns': [
            r'your-.*-key',
            r'your-.*-id', 
            r'.*-here',
            r'placeholder',
            r'replace.*',
            r'example\..*',
            r'test-.*-key',
            r'demo-.*',
            r'fake-.*',
            r'mock-.*'
        ],
        'credential_patterns': [
            r'sk-[a-zA-Z0-9]{32,}',  # OpenAI API key pattern
            r'xai-[a-zA-Z0-9]{32,}',  # xAI API key pattern
        ],
        'demo_content': [
            r'demo.*sermon',
            r'sample.*sermon',
            r'test.*sermon',
            r'lorem.*ipsum'
        ]
    }
    
    result = {
        'file_path': str(file_path),
        'file_type': file_path.suffix,
        'placeholder_count': 0,
        'credential_count': 0,
        'demo_content_count': 0,
        'risk_level': 'low',
        'issues': []
    }
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Quick size check - skip very large files
        if len(content) > 1000000:  # 1MB limit
            result['issues'].append('File too large, skipped detailed analysis')
            return result
        
        lines = content.splitlines()
        
        for line_num, line in enumerate(lines, 1):
            line_lower = line.lower()
            
            # Check for placeholder patterns
            for pattern in patterns['placeholder_patterns']:
                if re.search(pattern, line, re.IGNORECASE):
                    result['placeholder_count'] += 1
                    result['issues'].append(f"Line {line_num}: Placeholder pattern '{pattern}'")
                    break  # Only count once per line
            
            # Check for credential patterns (more serious)
            for pattern in patterns['credential_patterns']:
                if re.search(pattern, line):
                    result['credential_count'] += 1
                    result['issues'].append(f"Line {line_num}: Potential credential pattern")
                    result['risk_level'] = 'critical'
                    break
            
            # Check for demo content
            for pattern in patterns['demo_content']:
                if re.search(pattern, line, re.IGNORECASE):
                    result['demo_content_count'] += 1
                    break
        
        # Determine risk level
        total_issues = result['placeholder_count'] + result['credential_count'] + result['demo_content_count']
        
        if result['credential_count'] > 0:
            result['risk_level'] = 'critical'
        elif total_issues > 10:
            result['risk_level'] = 'high'
        elif total_issues > 5:
            result['risk_level'] = 'medium'
        elif total_issues > 0:
            result['risk_level'] = 'low'
        else:
            result['risk_level'] = 'clean'
    
    except Exception as e:
        result['issues'].append(f"Scan error: {str(e)}")
        result['risk_level'] = 'error'
    
    return result

def quick_project_scan(project_root: Path) -> Dict[str, Any]:
    """Perform a quick scan of the project for mock data."""
    analysis = {
        'timestamp': str(Path(__file__).stat().st_mtime),
        'project_root': str(project_root),
        'files_scanned': 0,
        'critical_files': 0,
        'high_risk_files': 0,
        'medium_risk_files': 0,
        'total_placeholders': 0,
        'total_credentials': 0,
        'files_by_risk': {
            'critical': [],
            'high': [],
            'medium': [],
            'low': [],
            'clean': [],
            'error': []
        }
    }
    
    # Scan key directories with limits
    scan_paths = [
        project_root / 'ui',
        project_root / 'src', 
        project_root / 'tests',
        project_root / '*.py',
        project_root / '*.yaml',
        project_root / '*.yml',
        project_root / '*.md'
    ]
    
    # Collect files to scan
    files_to_scan = []
    for scan_path in scan_paths:
        if '*' in str(scan_path):
            files_to_scan.extend(project_root.glob(scan_path.name))
        elif scan_path.is_dir():
            files_to_scan.extend(scan_path.rglob('*.py'))
            files_to_scan.extend(scan_path.rglob('*.yaml'))
            files_to_scan.extend(scan_path.rglob('*.yml'))
            files_to_scan.extend(scan_path.rglob('*.md'))
    
    # Filter and limit files
    files_to_scan = [f for f in files_to_scan if f.is_file() and '__pycache__' not in str(f)]
    files_to_scan = files_to_scan[:500]  # Limit to first 500 files for performance
    
    print(f"🔍 Scanning {len(files_to_scan)} files for mock data patterns...")
    
    for file_path in files_to_scan:
        analysis['files_scanned'] += 1
        result = scan_file_for_critical_patterns(file_path)
        
        risk_level = result['risk_level']
        analysis['files_by_risk'][risk_level].append({
            'file': str(file_path.relative_to(project_root)),
            'placeholders': result['placeholder_count'],
            'credentials': result['credential_count'],
            'demo_content': result['demo_content_count'],
            'issues': len(result['issues'])
        })
        
        analysis['total_placeholders'] += result['placeholder_count']
        analysis['total_credentials'] += result['credential_count']
        
        if risk_level == 'critical':
            analysis['critical_files'] += 1
        elif risk_level == 'high':
            analysis['high_risk_files'] += 1
        elif risk_level == 'medium':
            analysis['medium_risk_files'] += 1
        
        # Progress indicator
        if analysis['files_scanned'] % 50 == 0:
            print(f"   Processed {analysis['files_scanned']} files...")
    
    return analysis

def generate_quick_report(analysis: Dict[str, Any]) -> str:
    """Generate a quick summary report."""
    report = []
    report.append("# Quick Mock Data Analysis Report")
    report.append(f"**Generated**: {analysis['timestamp']}")
    report.append("")
    
    # Summary
    total_risk_files = analysis['critical_files'] + analysis['high_risk_files'] + analysis['medium_risk_files']
    report.append("## 📊 Quick Summary")
    report.append(f"- **Files Scanned**: {analysis['files_scanned']}")
    report.append(f"- **Files with Issues**: {total_risk_files}")
    report.append(f"- **Critical Files**: {analysis['critical_files']}")
    report.append(f"- **High Risk Files**: {analysis['high_risk_files']}")
    report.append(f"- **Medium Risk Files**: {analysis['medium_risk_files']}")
    report.append(f"- **Total Placeholders**: {analysis['total_placeholders']}")
    report.append(f"- **Potential Credentials**: {analysis['total_credentials']}")
    report.append("")
    
    # Critical files
    if analysis['files_by_risk']['critical']:
        report.append("## 🔥 Critical Risk Files")
        for file_info in analysis['files_by_risk']['critical'][:10]:  # Top 10
            report.append(f"- `{file_info['file']}` - {file_info['credentials']} potential credentials")
        report.append("")
    
    # High risk files
    if analysis['files_by_risk']['high']:
        report.append("## ⚠️ High Risk Files")
        for file_info in analysis['files_by_risk']['high'][:10]:  # Top 10
            report.append(f"- `{file_info['file']}` - {file_info['placeholders']} placeholders")
        report.append("")
    
    # Recommendations
    report.append("## 💡 Quick Recommendations")
    if analysis['critical_files'] > 0:
        report.append("- **URGENT**: Review critical files for potential credential exposure")
    if analysis['total_placeholders'] > 20:
        report.append("- Replace placeholder values with environment variables")
    if total_risk_files > 10:
        report.append("- Implement mock data cleanup process")
    
    report.append("")
    return "\n".join(report)

def main():
    """Run quick mock data analysis."""
    current_dir = Path(__file__).parent
    project_root = current_dir.parent.parent
    
    print("🔍 Starting quick mock data analysis...")
    
    # Perform quick scan
    analysis = quick_project_scan(project_root)
    
    # Generate report
    report = generate_quick_report(analysis)
    
    # Save results
    output_dir = project_root / 'Tests' / 'cloud-tests'
    
    report_file = output_dir / 'quick-mock-data-report.md'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    json_file = output_dir / 'quick-mock-data-data.json'
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, indent=2, default=str)
    
    print(f"✅ Quick analysis complete!")
    print(f"📄 Report saved to: {report_file}")
    print(f"📊 Data saved to: {json_file}")
    
    # Print summary
    total_risk_files = analysis['critical_files'] + analysis['high_risk_files'] + analysis['medium_risk_files']
    print(f"\n📊 Summary:")
    print(f"- Files scanned: {analysis['files_scanned']}")
    print(f"- Files with issues: {total_risk_files}")
    print(f"- Critical files: {analysis['critical_files']}")
    print(f"- Total placeholders: {analysis['total_placeholders']}")
    
    return 0 if analysis['critical_files'] == 0 else 1

if __name__ == '__main__':
    sys.exit(main())