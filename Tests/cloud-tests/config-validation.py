#!/usr/bin/env python3
"""
Configuration Validation for SermonAudio Processor

This script validates the configuration structure and schema without requiring
external services or API connections.

Validates:
- YAML structure and syntax
- Required configuration fields
- Provider configurations
- Default values and placeholders
- Configuration completeness
"""

import os
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Any, Set
import json
import re

def load_yaml_safely(file_path: Path) -> Dict[str, Any]:
    """Load YAML file with error handling."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        return {'_error': str(e), '_file': str(file_path)}

def validate_config_structure(config: Dict[str, Any], config_name: str) -> Dict[str, Any]:
    """Validate configuration structure and return analysis."""
    analysis = {
        'config_name': config_name,
        'valid': True,
        'errors': [],
        'warnings': [],
        'sections': {},
        'placeholders': [],
        'required_fields': {},
        'field_coverage': 0.0
    }
    
    if '_error' in config:
        analysis['valid'] = False
        analysis['errors'].append(f"YAML parsing error: {config['_error']}")
        return analysis
    
    # Define expected configuration structure
    expected_structure = {
        'api_key': {'type': str, 'required': True, 'description': 'SermonAudio API key'},
        'broadcaster_id': {'type': str, 'required': True, 'description': 'SermonAudio broadcaster ID'},
        'llm': {
            'type': dict,
            'required': True,
            'description': 'LLM provider configuration',
            'subfields': {
                'primary': {'type': dict, 'required': True},
                'fallback': {'type': dict, 'required': False},
                'validator': {'type': dict, 'required': False}
            }
        },
        'metadata_processing': {
            'type': dict,
            'required': False,
            'description': 'Metadata processing options',
            'subfields': {
                'description': {'type': dict, 'required': False},
                'hashtags': {'type': dict, 'required': False}
            }
        },
        'audio_processing': {
            'type': dict,
            'required': False,
            'description': 'Audio processing configuration'
        },
        'debug': {'type': bool, 'required': False, 'description': 'Debug mode flag'}
    }
    
    # Validate structure
    total_fields = len(expected_structure)
    found_fields = 0
    
    for field_name, field_spec in expected_structure.items():
        analysis['sections'][field_name] = {
            'present': field_name in config,
            'required': field_spec.get('required', False),
            'type_valid': False,
            'description': field_spec.get('description', ''),
            'issues': []
        }
        
        if field_name in config:
            found_fields += 1
            value = config[field_name]
            expected_type = field_spec['type']
            
            # Type validation
            if isinstance(value, expected_type):
                analysis['sections'][field_name]['type_valid'] = True
            else:
                analysis['sections'][field_name]['issues'].append(
                    f"Type mismatch: expected {expected_type.__name__}, got {type(value).__name__}"
                )
            
            # Subfield validation for dicts
            if expected_type == dict and 'subfields' in field_spec and isinstance(value, dict):
                subfield_analysis = {}
                for sub_name, sub_spec in field_spec['subfields'].items():
                    subfield_analysis[sub_name] = {
                        'present': sub_name in value,
                        'required': sub_spec.get('required', False)
                    }
                    
                    if sub_spec.get('required', False) and sub_name not in value:
                        analysis['sections'][field_name]['issues'].append(
                            f"Missing required subfield: {sub_name}"
                        )
                
                analysis['sections'][field_name]['subfields'] = subfield_analysis
        
        elif field_spec.get('required', False):
            analysis['errors'].append(f"Missing required field: {field_name}")
            analysis['valid'] = False
    
    analysis['field_coverage'] = found_fields / total_fields
    
    # Look for placeholder values
    placeholder_patterns = [
        r'your-.*-key',
        r'your-.*-id',
        r'.*-here',
        r'localhost.*',
        r'example\..*',
        r'placeholder',
        r'replace.*'
    ]
    
    def find_placeholders(obj, path=''):
        """Recursively find placeholder values."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                find_placeholders(value, f"{path}.{key}" if path else key)
        elif isinstance(obj, str):
            for pattern in placeholder_patterns:
                if re.search(pattern, obj, re.IGNORECASE):
                    analysis['placeholders'].append({
                        'path': path,
                        'value': obj,
                        'pattern': pattern
                    })
    
    find_placeholders(config)
    
    # Provider-specific validation
    if 'llm' in config and isinstance(config['llm'], dict):
        llm_config = config['llm']
        
        # Validate primary provider
        if 'primary' in llm_config:
            primary = llm_config['primary']
            if 'provider' in primary:
                provider_type = primary['provider']
                if provider_type not in primary:
                    analysis['warnings'].append(
                        f"Primary provider '{provider_type}' configuration missing"
                    )
        
        # Validate fallback provider if enabled
        if 'fallback' in llm_config and llm_config['fallback'].get('enabled', False):
            fallback = llm_config['fallback']
            if 'provider' in fallback:
                provider_type = fallback['provider']
                if provider_type not in fallback:
                    analysis['warnings'].append(
                        f"Fallback provider '{provider_type}' configuration missing"
                    )
    
    return analysis

def analyze_all_configs(project_root: Path) -> Dict[str, Any]:
    """Analyze all configuration files in the project."""
    configs_analysis = {
        'timestamp': str(Path(__file__).stat().st_mtime),
        'project_root': str(project_root),
        'configs': {},
        'summary': {
            'total_configs': 0,
            'valid_configs': 0,
            'total_errors': 0,
            'total_warnings': 0,
            'total_placeholders': 0
        }
    }
    
    # Find configuration files
    config_files = {
        'config.yaml': project_root / 'config.yaml',
        'config.example.yaml': project_root / 'config.example.yaml',
        'examples_config.yaml': project_root / 'examples_config.yaml'
    }
    
    for config_name, config_path in config_files.items():
        if config_path.exists():
            config_data = load_yaml_safely(config_path)
            analysis = validate_config_structure(config_data, config_name)
            configs_analysis['configs'][config_name] = analysis
            
            configs_analysis['summary']['total_configs'] += 1
            if analysis['valid']:
                configs_analysis['summary']['valid_configs'] += 1
            configs_analysis['summary']['total_errors'] += len(analysis['errors'])
            configs_analysis['summary']['total_warnings'] += len(analysis['warnings'])
            configs_analysis['summary']['total_placeholders'] += len(analysis['placeholders'])
    
    return configs_analysis

def generate_config_report(analysis: Dict[str, Any]) -> str:
    """Generate a human-readable configuration analysis report."""
    report = []
    report.append("# SermonAudio Processor Configuration Validation Report")
    report.append(f"**Generated**: {analysis['timestamp']}")
    report.append("")
    
    # Summary
    summary = analysis['summary']
    report.append("## 📊 Summary")
    report.append(f"- **Total Configurations**: {summary['total_configs']}")
    report.append(f"- **Valid Configurations**: {summary['valid_configs']}")
    report.append(f"- **Total Errors**: {summary['total_errors']}")
    report.append(f"- **Total Warnings**: {summary['total_warnings']}")
    report.append(f"- **Placeholder Values**: {summary['total_placeholders']}")
    report.append("")
    
    # Individual config analysis
    for config_name, config_analysis in analysis['configs'].items():
        report.append(f"## 📄 {config_name}")
        
        status = "✅ Valid" if config_analysis['valid'] else "❌ Invalid"
        report.append(f"**Status**: {status}")
        report.append(f"**Field Coverage**: {config_analysis['field_coverage']:.1%}")
        report.append("")
        
        # Errors
        if config_analysis['errors']:
            report.append("### ❌ Errors")
            for error in config_analysis['errors']:
                report.append(f"- {error}")
            report.append("")
        
        # Warnings
        if config_analysis['warnings']:
            report.append("### ⚠️ Warnings")
            for warning in config_analysis['warnings']:
                report.append(f"- {warning}")
            report.append("")
        
        # Placeholders
        if config_analysis['placeholders']:
            report.append("### 🏷️ Placeholder Values")
            for placeholder in config_analysis['placeholders']:
                report.append(f"- `{placeholder['path']}`: `{placeholder['value']}`")
            report.append("")
        
        # Section details
        report.append("### 📋 Configuration Sections")
        for section_name, section_info in config_analysis['sections'].items():
            status_icon = "✅" if section_info['present'] else "❌"
            required_text = " (Required)" if section_info['required'] else ""
            report.append(f"- {status_icon} **{section_name}**{required_text}")
            
            if section_info['issues']:
                for issue in section_info['issues']:
                    report.append(f"  - ⚠️ {issue}")
            
            if 'subfields' in section_info:
                for sub_name, sub_info in section_info['subfields'].items():
                    sub_status = "✅" if sub_info['present'] else "❌"
                    sub_required = " (Required)" if sub_info['required'] else ""
                    report.append(f"  - {sub_status} {sub_name}{sub_required}")
        
        report.append("")
    
    # Recommendations
    report.append("## 💡 Recommendations")
    
    total_placeholders = sum(len(config['placeholders']) for config in analysis['configs'].values())
    if total_placeholders > 0:
        report.append("- Replace placeholder values with actual configuration")
    
    invalid_configs = [name for name, config in analysis['configs'].items() if not config['valid']]
    if invalid_configs:
        report.append(f"- Fix validation errors in: {', '.join(invalid_configs)}")
    
    if summary['total_warnings'] > 0:
        report.append("- Address configuration warnings for optimal functionality")
    
    if 'config.yaml' not in analysis['configs']:
        report.append("- Create config.yaml from config.example.yaml template")
    
    report.append("")
    
    return "\n".join(report)

def main():
    """Run configuration validation."""
    # Find project root
    current_dir = Path(__file__).parent
    project_root = current_dir.parent.parent
    
    print("🔍 Starting configuration validation...")
    
    # Analyze configurations
    analysis = analyze_all_configs(project_root)
    
    # Generate report
    report = generate_config_report(analysis)
    
    # Save results
    output_dir = project_root / 'Tests' / 'cloud-tests'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    report_file = output_dir / 'config-validation-report.md'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    json_file = output_dir / 'config-validation-data.json'
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, indent=2, default=str)
    
    print(f"✅ Configuration validation complete!")
    print(f"📄 Report saved to: {report_file}")
    print(f"📊 Raw data saved to: {json_file}")
    
    # Print summary
    summary = analysis['summary']
    print(f"\n📊 Summary:")
    print(f"- Configurations analyzed: {summary['total_configs']}")
    print(f"- Valid configurations: {summary['valid_configs']}")
    print(f"- Total errors: {summary['total_errors']}")
    print(f"- Total warnings: {summary['total_warnings']}")
    print(f"- Placeholder values: {summary['total_placeholders']}")
    
    return 0 if summary['total_errors'] == 0 else 1

if __name__ == '__main__':
    sys.exit(main())