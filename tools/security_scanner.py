#!/usr/bin/env python3
"""
Security Scanner for SermonAudio Processor
Detects hardcoded credentials, test data, and security violations across the codebase
"""

import os
import re
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass, asdict


@dataclass
class SecurityViolation:
    """Represents a security violation found in the codebase."""
    file_path: str
    line_number: int
    line_content: str
    violation_type: str
    severity: str
    description: str


class SecurityScanner:
    """Comprehensive security scanner for detecting hardcoded credentials and test data."""
    
    def __init__(self):
        # Patterns for detecting hardcoded credentials
        self.credential_patterns = {
            'api_key': r'api_key\s*[:=]\s*["\']?([a-zA-Z0-9-]{20,})["\']?',
            'openai_key': r'["\']?(sk-[a-zA-Z0-9]{32,})["\']?',
            'xai_key': r'["\']?(xai-[a-zA-Z0-9]{20,})["\']?',
            'anthropic_key': r'["\']?(sk-ant-[a-zA-Z0-9]{20,})["\']?',
            'groq_key': r'["\']?(gsk-[a-zA-Z0-9]{20,})["\']?',
            'password': r'password\s*[:=]\s*["\']?([^$][^{][^}]+)["\']?',
            'secret': r'secret\s*[:=]\s*["\']?([a-zA-Z0-9]{16,})["\']?',
            'token': r'token\s*[:=]\s*["\']?([a-zA-Z0-9-_]{20,})["\']?',
        }
        
        # Patterns for test data and mock values
        self.test_patterns = {
            'test_id': r'["\']?(12345|test123|example123)["\']?',
            'placeholder_api': r'["\']?(your-[a-z-]+-(?:key|id|here))["\']?',
            'test_broadcaster': r'["\']?(test_broadcaster|demo_broadcaster)["\']?',
            'example_values': r'["\']?(example|demo|sample|placeholder)["\']?',
            'localhost_urls': r'["\']?(http://localhost:\d+)["\']?',
        }
        
        # Hardcoded values that indicate test/development data
        self.hardcoded_values = [
            'your-api-key-here', 'your-broadcaster-id', 'test_key', 'test_broadcaster',
            'example.com', 'demo.com', 'placeholder', 'changeme', 'password123',
            '12345', 'test123', 'admin', 'root', 'default'
        ]
        
        # File extensions to scan
        self.scan_extensions = {'.py', '.yaml', '.yml', '.json', '.txt', '.md', '.cfg', '.ini'}
        
        # Directories to exclude from scanning
        self.exclude_dirs = {
            '.git', '__pycache__', '.venv', 'venv', 'node_modules', 
            '.pytest_cache', 'build', 'dist', '.mypy_cache'
        }
        
        # Files to exclude from scanning
        self.exclude_files = {
            '.env.example', 'requirements.txt', 'pyproject.toml', 'uv.lock',
            'security_scanner.py'  # Exclude this file itself
        }
    
    def scan_file(self, file_path: Path) -> List[SecurityViolation]:
        """Scan a single file for security violations."""
        violations = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.splitlines()
                
            for line_num, line in enumerate(lines, 1):
                # Skip empty lines and comments
                if not line.strip() or line.strip().startswith('#'):
                    continue
                
                # Check for credential patterns
                violations.extend(
                    self._check_credential_patterns(file_path, line_num, line)
                )
                
                # Check for test data patterns
                violations.extend(
                    self._check_test_patterns(file_path, line_num, line)
                )
                
                # Check for hardcoded values
                violations.extend(
                    self._check_hardcoded_values(file_path, line_num, line)
                )
                
        except Exception as e:
            # Log error but continue scanning
            print(f"Warning: Could not scan {file_path}: {e}")
        
        return violations
    
    def _check_credential_patterns(self, file_path: Path, line_num: int, line: str) -> List[SecurityViolation]:
        """Check for credential patterns in a line."""
        violations = []
        
        for pattern_name, pattern in self.credential_patterns.items():
            matches = re.finditer(pattern, line, re.IGNORECASE)
            for match in matches:
                # Skip if it's an environment variable reference
                if '${' in line or line.strip().startswith('EXPORT') or '=' in line.split('#')[0]:
                    if any(env_indicator in line.upper() for env_indicator in ['$', 'ENV', 'ENVIRONMENT']):
                        continue
                
                violations.append(SecurityViolation(
                    file_path=str(file_path),
                    line_number=line_num,
                    line_content=line.strip(),
                    violation_type=f"hardcoded_credential_{pattern_name}",
                    severity="critical",
                    description=f"Potential hardcoded {pattern_name.replace('_', ' ')} detected"
                ))
        
        return violations
    
    def _check_test_patterns(self, file_path: Path, line_num: int, line: str) -> List[SecurityViolation]:
        """Check for test data patterns in a line."""
        violations = []
        
        # Skip files that are explicitly test files
        if 'test' in str(file_path).lower() or 'tests' in str(file_path).lower():
            return violations
        
        for pattern_name, pattern in self.test_patterns.items():
            matches = re.finditer(pattern, line, re.IGNORECASE)
            for match in matches:
                violations.append(SecurityViolation(
                    file_path=str(file_path),
                    line_number=line_num,
                    line_content=line.strip(),
                    violation_type=f"test_data_{pattern_name}",
                    severity="medium",
                    description=f"Test/placeholder data detected: {pattern_name.replace('_', ' ')}"
                ))
        
        return violations
    
    def _check_hardcoded_values(self, file_path: Path, line_num: int, line: str) -> List[SecurityViolation]:
        """Check for known hardcoded values in a line."""
        violations = []
        
        # Skip files that are explicitly test files or examples
        if any(indicator in str(file_path).lower() for indicator in ['test', 'example', 'fixture', 'mock']):
            return violations
        
        line_lower = line.lower()
        for hardcoded_value in self.hardcoded_values:
            if hardcoded_value.lower() in line_lower:
                # Skip if it's in a comment or documentation
                if '#' in line and line.index('#') < line.index(hardcoded_value):
                    continue
                    
                violations.append(SecurityViolation(
                    file_path=str(file_path),
                    line_number=line_num,
                    line_content=line.strip(),
                    violation_type="hardcoded_value",
                    severity="low",
                    description=f"Hardcoded value '{hardcoded_value}' detected"
                ))
        
        return violations
    
    def scan_directory(self, directory: Path) -> List[SecurityViolation]:
        """Scan a directory recursively for security violations."""
        violations = []
        
        for root, dirs, files in os.walk(directory):
            # Exclude certain directories
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            
            for file in files:
                file_path = Path(root) / file
                
                # Skip excluded files
                if file in self.exclude_files:
                    continue
                
                # Only scan files with relevant extensions
                if file_path.suffix.lower() in self.scan_extensions:
                    violations.extend(self.scan_file(file_path))
        
        return violations
    
    def generate_report(self, violations: List[SecurityViolation], output_format: str = 'text') -> str:
        """Generate a security report from violations."""
        if output_format == 'json':
            return json.dumps([asdict(v) for v in violations], indent=2)
        
        # Generate text report
        report = []
        report.append("🔍 SermonAudio Processor - Security Scan Report")
        report.append("=" * 60)
        
        if not violations:
            report.append("\n✅ No security violations detected!")
            return "\n".join(report)
        
        # Group violations by severity
        critical = [v for v in violations if v.severity == 'critical']
        medium = [v for v in violations if v.severity == 'medium']
        low = [v for v in violations if v.severity == 'low']
        
        report.append(f"\n📊 Summary:")
        report.append(f"   🔴 Critical: {len(critical)} violations")
        report.append(f"   🟡 Medium:   {len(medium)} violations")
        report.append(f"   🔵 Low:      {len(low)} violations")
        report.append(f"   📄 Total:    {len(violations)} violations")
        
        # Critical violations
        if critical:
            report.append("\n🔴 CRITICAL VIOLATIONS (Immediate Action Required):")
            report.append("-" * 50)
            for violation in critical:
                report.append(f"📁 {violation.file_path}:{violation.line_number}")
                report.append(f"   💡 {violation.description}")
                report.append(f"   📝 {violation.line_content}")
                report.append("")
        
        # Medium violations
        if medium:
            report.append("\n🟡 MEDIUM VIOLATIONS (Should Be Fixed):")
            report.append("-" * 50)
            for violation in medium[:10]:  # Limit to first 10
                report.append(f"📁 {violation.file_path}:{violation.line_number}")
                report.append(f"   💡 {violation.description}")
                report.append(f"   📝 {violation.line_content}")
                report.append("")
            
            if len(medium) > 10:
                report.append(f"... and {len(medium) - 10} more medium violations")
                report.append("")
        
        # Low violations summary
        if low:
            report.append(f"\n🔵 LOW VIOLATIONS: {len(low)} items (run with --verbose for details)")
        
        report.append("\n🔧 Recommended Actions:")
        report.append("1. Replace hardcoded credentials with environment variables")
        report.append("2. Move test data to proper test fixtures directories")
        report.append("3. Use .env files for configuration")
        report.append("4. Review and update placeholder values")
        
        return "\n".join(report)
    
    def get_statistics(self, violations: List[SecurityViolation]) -> Dict[str, Any]:
        """Get statistics about security violations."""
        stats = {
            'total_violations': len(violations),
            'by_severity': {},
            'by_type': {},
            'by_file': {},
            'unique_files': len(set(v.file_path for v in violations))
        }
        
        for violation in violations:
            # Count by severity
            stats['by_severity'][violation.severity] = stats['by_severity'].get(violation.severity, 0) + 1
            
            # Count by type
            stats['by_type'][violation.violation_type] = stats['by_type'].get(violation.violation_type, 0) + 1
            
            # Count by file
            stats['by_file'][violation.file_path] = stats['by_file'].get(violation.file_path, 0) + 1
        
        return stats


def main():
    """Main function for command-line interface."""
    parser = argparse.ArgumentParser(description='Security scanner for SermonAudio Processor')
    parser.add_argument('path', nargs='?', default='.', help='Path to scan (default: current directory)')
    parser.add_argument('--format', choices=['text', 'json'], default='text', help='Output format')
    parser.add_argument('--output', '-o', help='Output file (default: stdout)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    parser.add_argument('--stats', action='store_true', help='Show statistics only')
    parser.add_argument('--fix-mode', action='store_true', help='Exit with error code if violations found')
    
    args = parser.parse_args()
    
    scanner = SecurityScanner()
    violations = scanner.scan_directory(Path(args.path))
    
    if args.stats:
        stats = scanner.get_statistics(violations)
        print(json.dumps(stats, indent=2))
        return
    
    report = scanner.generate_report(violations, args.format)
    
    if args.output:
        with open(args.output, 'w') as f:
            f.write(report)
        print(f"Report written to {args.output}")
    else:
        print(report)
    
    # Exit with error code if violations found and in fix mode
    if args.fix_mode and violations:
        critical_count = len([v for v in violations if v.severity == 'critical'])
        sys.exit(critical_count)


if __name__ == "__main__":
    main()