#!/usr/bin/env python3
"""
Static Analysis for SermonAudio Processor UI Components

This script performs cloud-safe static analysis of the Streamlit UI components
without requiring external dependencies or server execution.

Analyzes:
- UI page structure and components
- Import dependencies and resolution
- Component organization and patterns
- Navigation structure
"""

import ast
import os
import sys
from pathlib import Path
from typing import Dict, List, Set, Any
import json

def analyze_python_file(file_path: Path) -> Dict[str, Any]:
    """Analyze a Python file using AST parsing."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content)
        
        analysis = {
            'file_path': str(file_path),
            'imports': [],
            'functions': [],
            'classes': [],
            'constants': [],
            'streamlit_components': [],
            'docstring': ast.get_docstring(tree),
            'lines_of_code': len(content.splitlines()),
            'complexity_score': 0
        }
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    analysis['imports'].append({
                        'type': 'import',
                        'module': alias.name,
                        'alias': alias.asname
                    })
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                for alias in node.names:
                    analysis['imports'].append({
                        'type': 'from_import',
                        'module': module,
                        'name': alias.name,
                        'alias': alias.asname
                    })
            elif isinstance(node, ast.FunctionDef):
                analysis['functions'].append({
                    'name': node.name,
                    'line': node.lineno,
                    'args': len(node.args.args),
                    'decorators': [d.id for d in node.decorator_list if hasattr(d, 'id')],
                    'docstring': ast.get_docstring(node)
                })
                # Increase complexity for each function
                analysis['complexity_score'] += 1
            elif isinstance(node, ast.ClassDef):
                analysis['classes'].append({
                    'name': node.name,
                    'line': node.lineno,
                    'bases': [base.id for base in node.bases if hasattr(base, 'id')],
                    'decorators': [d.id for d in node.decorator_list if hasattr(d, 'id')],
                    'docstring': ast.get_docstring(node)
                })
                analysis['complexity_score'] += 2
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        analysis['constants'].append({
                            'name': target.id,
                            'line': node.lineno
                        })
            elif isinstance(node, ast.Call):
                # Look for Streamlit components
                if hasattr(node.func, 'attr'):
                    if hasattr(node.func.value, 'id') and node.func.value.id == 'st':
                        analysis['streamlit_components'].append({
                            'component': node.func.attr,
                            'line': node.lineno
                        })
        
        return analysis
        
    except Exception as e:
        return {
            'file_path': str(file_path),
            'error': str(e),
            'analysis_failed': True
        }

def analyze_ui_structure(ui_dir: Path) -> Dict[str, Any]:
    """Analyze the overall UI structure."""
    ui_analysis = {
        'ui_directory': str(ui_dir),
        'pages': {},
        'main_app': None,
        'navigation': None,
        'shared_components': [],
        'total_files': 0,
        'total_lines': 0,
        'dependencies': set(),
        'streamlit_usage': {}
    }
    
    # Analyze main Streamlit app
    main_app_path = ui_dir / 'streamlit_app.py'
    if main_app_path.exists():
        ui_analysis['main_app'] = analyze_python_file(main_app_path)
        ui_analysis['total_files'] += 1
        ui_analysis['total_lines'] += ui_analysis['main_app'].get('lines_of_code', 0)
    
    # Analyze navigation
    nav_path = ui_dir / 'shared_navigation.py'
    if nav_path.exists():
        ui_analysis['navigation'] = analyze_python_file(nav_path)
        ui_analysis['total_files'] += 1
        ui_analysis['total_lines'] += ui_analysis['navigation'].get('lines_of_code', 0)
    
    # Analyze UI pages
    pages_dir = ui_dir / 'ui_pages'
    if pages_dir.exists():
        for py_file in pages_dir.glob('*.py'):
            if py_file.name != '__init__.py':
                page_name = py_file.stem
                ui_analysis['pages'][page_name] = analyze_python_file(py_file)
                ui_analysis['total_files'] += 1
                ui_analysis['total_lines'] += ui_analysis['pages'][page_name].get('lines_of_code', 0)
    
    # Analyze other UI components
    for py_file in ui_dir.glob('*.py'):
        if py_file.name not in ['streamlit_app.py', 'shared_navigation.py', '__init__.py']:
            component_name = py_file.stem
            ui_analysis['shared_components'].append({
                'name': component_name,
                'analysis': analyze_python_file(py_file)
            })
            ui_analysis['total_files'] += 1
            ui_analysis['total_lines'] += ui_analysis['shared_components'][-1]['analysis'].get('lines_of_code', 0)
    
    # Collect dependencies and Streamlit usage
    streamlit_components = {}
    all_files = [ui_analysis['main_app']] + list(ui_analysis['pages'].values()) + [comp['analysis'] for comp in ui_analysis['shared_components']]
    if ui_analysis['navigation']:
        all_files.append(ui_analysis['navigation'])
    
    for file_analysis in all_files:
        if file_analysis and not file_analysis.get('analysis_failed'):
            # Collect imports
            for imp in file_analysis.get('imports', []):
                ui_analysis['dependencies'].add(imp['module'])
            
            # Collect Streamlit components
            for comp in file_analysis.get('streamlit_components', []):
                comp_name = comp['component']
                if comp_name not in streamlit_components:
                    streamlit_components[comp_name] = 0
                streamlit_components[comp_name] += 1
    
    ui_analysis['dependencies'] = sorted(list(ui_analysis['dependencies']))
    ui_analysis['streamlit_usage'] = streamlit_components
    
    return ui_analysis

def generate_analysis_report(analysis: Dict[str, Any]) -> str:
    """Generate a human-readable analysis report."""
    report = []
    report.append("# SermonAudio Processor UI Static Analysis Report")
    report.append(f"**Generated**: {analysis.get('timestamp', 'Unknown')}")
    report.append("")
    
    # Overview
    report.append("## 📊 Overview")
    report.append(f"- **Total UI Files**: {analysis['ui_structure']['total_files']}")
    report.append(f"- **Total Lines of Code**: {analysis['ui_structure']['total_lines']}")
    report.append(f"- **UI Pages**: {len(analysis['ui_structure']['pages'])}")
    report.append(f"- **Shared Components**: {len(analysis['ui_structure']['shared_components'])}")
    report.append("")
    
    # Main App Analysis
    if analysis['ui_structure']['main_app']:
        main_app = analysis['ui_structure']['main_app']
        report.append("## 🏠 Main Application (streamlit_app.py)")
        report.append(f"- **Lines of Code**: {main_app['lines_of_code']}")
        report.append(f"- **Functions**: {len(main_app['functions'])}")
        report.append(f"- **Imports**: {len(main_app['imports'])}")
        if main_app['docstring']:
            report.append(f"- **Description**: {main_app['docstring'][:100]}...")
        report.append("")
    
    # Pages Analysis
    report.append("## 📄 UI Pages Analysis")
    for page_name, page_analysis in analysis['ui_structure']['pages'].items():
        if not page_analysis.get('analysis_failed'):
            report.append(f"### {page_name}")
            report.append(f"- **Lines**: {page_analysis['lines_of_code']}")
            report.append(f"- **Functions**: {len(page_analysis['functions'])}")
            report.append(f"- **Classes**: {len(page_analysis['classes'])}")
            report.append(f"- **Streamlit Components**: {len(page_analysis['streamlit_components'])}")
            if page_analysis['docstring']:
                report.append(f"- **Purpose**: {page_analysis['docstring'][:100]}...")
            report.append("")
    
    # Streamlit Usage
    report.append("## 🎨 Streamlit Component Usage")
    streamlit_usage = analysis['ui_structure']['streamlit_usage']
    for component, count in sorted(streamlit_usage.items(), key=lambda x: x[1], reverse=True):
        report.append(f"- `st.{component}`: {count} usages")
    report.append("")
    
    # Dependencies
    report.append("## 📦 Dependencies")
    dependencies = analysis['ui_structure']['dependencies']
    for dep in dependencies:
        report.append(f"- {dep}")
    report.append("")
    
    # Issues and Recommendations
    report.append("## ⚠️ Potential Issues")
    issues = analysis.get('issues', [])
    if issues:
        for issue in issues:
            report.append(f"- {issue}")
    else:
        report.append("- No obvious issues detected in static analysis")
    report.append("")
    
    # Quality Metrics
    report.append("## 📈 Quality Metrics")
    total_complexity = sum(
        page.get('complexity_score', 0) 
        for page in analysis['ui_structure']['pages'].values()
        if not page.get('analysis_failed')
    )
    if analysis['ui_structure']['main_app']:
        total_complexity += analysis['ui_structure']['main_app'].get('complexity_score', 0)
    
    report.append(f"- **Overall Complexity Score**: {total_complexity}")
    report.append(f"- **Average Lines per File**: {analysis['ui_structure']['total_lines'] // max(analysis['ui_structure']['total_files'], 1)}")
    report.append(f"- **Streamlit Component Diversity**: {len(streamlit_usage)} different components")
    report.append("")
    
    return "\n".join(report)

def main():
    """Run static analysis on the UI components."""
    # Find project root and UI directory
    current_dir = Path(__file__).parent
    project_root = current_dir.parent.parent
    ui_dir = project_root / 'ui'
    
    if not ui_dir.exists():
        print(f"Error: UI directory not found at {ui_dir}")
        return 1
    
    print("🔍 Starting static analysis of UI components...")
    
    # Perform analysis
    ui_structure = analyze_ui_structure(ui_dir)
    
    # Look for potential issues
    issues = []
    
    # Check for missing documentation
    pages_without_docs = [
        name for name, analysis in ui_structure['pages'].items()
        if not analysis.get('analysis_failed') and not analysis.get('docstring')
    ]
    if pages_without_docs:
        issues.append(f"Pages missing docstrings: {', '.join(pages_without_docs)}")
    
    # Check for overly complex files
    complex_files = [
        name for name, analysis in ui_structure['pages'].items()
        if not analysis.get('analysis_failed') and analysis.get('complexity_score', 0) > 20
    ]
    if complex_files:
        issues.append(f"High complexity files (>20): {', '.join(complex_files)}")
    
    # Check for large files
    large_files = [
        name for name, analysis in ui_structure['pages'].items()
        if not analysis.get('analysis_failed') and analysis.get('lines_of_code', 0) > 500
    ]
    if large_files:
        issues.append(f"Large files (>500 lines): {', '.join(large_files)}")
    
    # Compile full analysis
    full_analysis = {
        'timestamp': str(Path(__file__).stat().st_mtime),
        'ui_structure': ui_structure,
        'issues': issues
    }
    
    # Generate and save report
    report = generate_analysis_report(full_analysis)
    
    # Save to file
    output_dir = project_root / 'Tests' / 'cloud-tests'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    report_file = output_dir / 'ui-static-analysis-report.md'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    # Also save raw JSON data
    json_file = output_dir / 'ui-static-analysis-data.json'
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(full_analysis, f, indent=2, default=str)
    
    print(f"✅ Analysis complete!")
    print(f"📄 Report saved to: {report_file}")
    print(f"📊 Raw data saved to: {json_file}")
    
    # Print summary
    print(f"\n📊 Summary:")
    print(f"- Total UI files analyzed: {ui_structure['total_files']}")
    print(f"- Total lines of code: {ui_structure['total_lines']}")
    print(f"- UI pages found: {len(ui_structure['pages'])}")
    print(f"- Issues identified: {len(issues)}")
    
    if issues:
        print(f"\n⚠️ Issues found:")
        for issue in issues:
            print(f"  - {issue}")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())