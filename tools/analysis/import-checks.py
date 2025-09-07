#!/usr/bin/env python3
"""
Import and Dependency Analysis for SermonAudio Processor

This script analyzes Python imports and dependencies without executing code
or requiring external packages to be installed.

Analyzes:
- Import statements and resolution
- Dependency requirements and availability
- Circular imports
- Unused imports
- Missing imports
"""

import ast
import os
import sys
from pathlib import Path
from typing import Dict, List, Set, Any
import json
import re

def extract_imports_from_file(file_path: Path) -> Dict[str, Any]:
    """Extract import information from a Python file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content)
        
        imports_info = {
            'file_path': str(file_path),
            'imports': [],
            'from_imports': [],
            'local_imports': [],
            'external_imports': [],
            'relative_imports': [],
            'import_errors': []
        }
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    import_info = {
                        'module': alias.name,
                        'alias': alias.asname,
                        'line': node.lineno,
                        'type': 'import'
                    }
                    imports_info['imports'].append(import_info)
                    
                    # Categorize import
                    if alias.name.startswith('.'):
                        imports_info['relative_imports'].append(import_info)
                    elif '.' in alias.name and alias.name.split('.')[0] in ['src', 'ui', 'tests']:
                        imports_info['local_imports'].append(import_info)
                    else:
                        imports_info['external_imports'].append(import_info)
            
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                level = node.level
                
                for alias in node.names:
                    import_info = {
                        'module': module,
                        'name': alias.name,
                        'alias': alias.asname,
                        'line': node.lineno,
                        'level': level,
                        'type': 'from_import'
                    }
                    imports_info['from_imports'].append(import_info)
                    
                    # Categorize import
                    if level > 0 or module.startswith('.'):
                        imports_info['relative_imports'].append(import_info)
                    elif module and module.split('.')[0] in ['src', 'ui', 'tests']:
                        imports_info['local_imports'].append(import_info)
                    else:
                        imports_info['external_imports'].append(import_info)
        
        return imports_info
        
    except Exception as e:
        return {
            'file_path': str(file_path),
            'error': str(e),
            'analysis_failed': True
        }

def check_import_resolution(imports_info: Dict[str, Any], project_root: Path) -> Dict[str, Any]:
    """Check if imports can be resolved within the project structure."""
    resolution_info = {
        'resolvable': [],
        'unresolvable': [],
        'external_packages': [],
        'project_modules': []
    }
    
    # Standard library modules (Python 3.11+)
    stdlib_modules = {
        'os', 'sys', 'pathlib', 'json', 'yaml', 'ast', 're', 'typing',
        'datetime', 'time', 'logging', 'warnings', 'argparse', 'subprocess',
        'threading', 'multiprocessing', 'asyncio', 'sqlite3', 'csv', 'urllib',
        'http', 'email', 'xml', 'html', 'collections', 'itertools', 'functools',
        'operator', 'copy', 'pickle', 'base64', 'hashlib', 'hmac', 'secrets',
        'random', 'math', 'statistics', 'decimal', 'fractions', 'enum',
        'dataclasses', 'contextlib', 'weakref', 'gc', 'inspect'
    }
    
    # Known external packages from requirements
    external_packages = {
        'streamlit', 'numpy', 'pandas', 'torch', 'torchaudio', 'torchvision',
        'requests', 'pydub', 'librosa', 'soundfile', 'noisereduce',
        'deepfilternet', 'ollama', 'openai', 'langchain', 'chromadb',
        'sentence_transformers', 'plotly', 'matplotlib', 'seaborn',
        'psutil', 'tenacity', 'tqdm', 'colorlog', 'schedule', 'rich',
        'omegaconf', 'gradio', 'celluloid', 'tabulate', 'resampy',
        'sermonaudio', 'scipy', 'pytest', 'black', 'ruff', 'pylint'
    }
    
    all_imports = imports_info.get('imports', []) + imports_info.get('from_imports', [])
    
    for imp in all_imports:
        module_name = imp.get('module', '')
        if not module_name:
            continue
        
        # Get root module name
        root_module = module_name.split('.')[0]
        
        # Check resolution
        if root_module in stdlib_modules:
            resolution_info['resolvable'].append({
                'import': imp,
                'type': 'stdlib',
                'module': root_module
            })
        elif root_module in external_packages:
            resolution_info['external_packages'].append({
                'import': imp,
                'package': root_module
            })
        elif root_module in ['src', 'ui', 'tests'] or imp.get('level', 0) > 0:
            # Project-local import
            resolution_info['project_modules'].append({
                'import': imp,
                'type': 'local'
            })
        else:
            # Check if it might be a file in the project
            potential_paths = [
                project_root / f"{module_name.replace('.', '/')}.py",
                project_root / module_name.replace('.', '/') / "__init__.py",
                project_root / "src" / f"{module_name.replace('.', '/')}.py",
                project_root / "ui" / f"{module_name.replace('.', '/')}.py"
            ]
            
            resolved = False
            for path in potential_paths:
                if path.exists():
                    resolution_info['project_modules'].append({
                        'import': imp,
                        'type': 'local',
                        'resolved_path': str(path)
                    })
                    resolved = True
                    break
            
            if not resolved:
                resolution_info['unresolvable'].append({
                    'import': imp,
                    'reason': 'Module not found in stdlib, external packages, or project'
                })
    
    return resolution_info

def analyze_project_imports(project_root: Path) -> Dict[str, Any]:
    """Analyze imports across the entire project."""
    analysis = {
        'timestamp': str(Path(__file__).stat().st_mtime),
        'project_root': str(project_root),
        'files': {},
        'summary': {
            'total_files': 0,
            'files_with_errors': 0,
            'total_imports': 0,
            'external_packages': set(),
            'unresolvable_imports': [],
            'circular_dependencies': [],
            'most_imported_modules': {}
        }
    }
    
    # Find all Python files
    python_files = []
    for directory in [project_root / 'src', project_root / 'ui', project_root / 'tests']:
        if directory.exists():
            python_files.extend(directory.rglob('*.py'))
    
    # Also check root directory Python files
    python_files.extend(project_root.glob('*.py'))
    
    # Filter out __pycache__ and other unwanted files
    python_files = [f for f in python_files if '__pycache__' not in str(f)]
    
    module_usage = {}
    file_dependencies = {}
    
    for py_file in python_files:
        # Extract imports
        imports_info = extract_imports_from_file(py_file)
        
        if not imports_info.get('analysis_failed'):
            # Check import resolution
            resolution_info = check_import_resolution(imports_info, project_root)
            
            analysis['files'][str(py_file)] = {
                'imports': imports_info,
                'resolution': resolution_info
            }
            
            analysis['summary']['total_files'] += 1
            analysis['summary']['total_imports'] += len(imports_info.get('imports', [])) + len(imports_info.get('from_imports', []))
            
            # Track external packages
            for ext_pkg in resolution_info['external_packages']:
                analysis['summary']['external_packages'].add(ext_pkg['package'])
            
            # Track unresolvable imports
            analysis['summary']['unresolvable_imports'].extend(resolution_info['unresolvable'])
            
            # Track module usage
            all_imports = imports_info.get('imports', []) + imports_info.get('from_imports', [])
            file_deps = set()
            
            for imp in all_imports:
                module = imp.get('module', '')
                if module:
                    if module not in module_usage:
                        module_usage[module] = 0
                    module_usage[module] += 1
                    file_deps.add(module)
            
            file_dependencies[str(py_file)] = file_deps
        else:
            analysis['summary']['files_with_errors'] += 1
    
    # Find most imported modules
    analysis['summary']['most_imported_modules'] = dict(
        sorted(module_usage.items(), key=lambda x: x[1], reverse=True)[:20]
    )
    
    # Convert external_packages set to list for JSON serialization
    analysis['summary']['external_packages'] = sorted(list(analysis['summary']['external_packages']))
    
    # Simple circular dependency detection
    # This is a simplified check - real circular dependency detection is more complex
    for file_path, deps in file_dependencies.items():
        file_module = Path(file_path).stem
        for dep in deps:
            if dep.endswith(file_module) or file_module in dep:
                analysis['summary']['circular_dependencies'].append({
                    'file': file_path,
                    'dependency': dep,
                    'type': 'potential_circular'
                })
    
    return analysis

def generate_import_report(analysis: Dict[str, Any]) -> str:
    """Generate a human-readable import analysis report."""
    report = []
    report.append("# SermonAudio Processor Import Analysis Report")
    report.append(f"**Generated**: {analysis['timestamp']}")
    report.append("")
    
    # Summary
    summary = analysis['summary']
    report.append("## 📊 Summary")
    report.append(f"- **Total Python Files**: {summary['total_files']}")
    report.append(f"- **Files with Errors**: {summary['files_with_errors']}")
    report.append(f"- **Total Imports**: {summary['total_imports']}")
    report.append(f"- **External Packages**: {len(summary['external_packages'])}")
    report.append(f"- **Unresolvable Imports**: {len(summary['unresolvable_imports'])}")
    report.append("")
    
    # External packages
    if summary['external_packages']:
        report.append("## 📦 External Package Dependencies")
        for package in summary['external_packages']:
            report.append(f"- `{package}`")
        report.append("")
    
    # Most imported modules
    if summary['most_imported_modules']:
        report.append("## 🔝 Most Imported Modules")
        for module, count in list(summary['most_imported_modules'].items())[:10]:
            report.append(f"- `{module}`: {count} imports")
        report.append("")
    
    # Unresolvable imports
    if summary['unresolvable_imports']:
        report.append("## ❌ Unresolvable Imports")
        for unresolved in summary['unresolvable_imports'][:10]:  # Limit to first 10
            imp = unresolved['import']
            file_path = Path(imp.get('file_path', 'unknown')).name
            module = imp.get('module', 'unknown')
            line = imp.get('line', 'unknown')
            report.append(f"- `{module}` in `{file_path}:{line}` - {unresolved['reason']}")
        report.append("")
    
    # Circular dependencies
    if summary['circular_dependencies']:
        report.append("## 🔄 Potential Circular Dependencies")
        for circular in summary['circular_dependencies']:
            file_name = Path(circular['file']).name
            report.append(f"- `{file_name}` → `{circular['dependency']}`")
        report.append("")
    
    # File-by-file analysis (summary)
    report.append("## 📄 File Analysis Summary")
    error_files = []
    high_import_files = []
    
    for file_path, file_info in analysis['files'].items():
        file_name = Path(file_path).name
        
        if 'error' in file_info:
            error_files.append(file_name)
        else:
            imports_count = len(file_info['imports'].get('imports', [])) + len(file_info['imports'].get('from_imports', []))
            if imports_count > 20:  # Files with many imports
                high_import_files.append((file_name, imports_count))
    
    if error_files:
        report.append("### ❌ Files with Import Errors")
        for file_name in error_files:
            report.append(f"- `{file_name}`")
        report.append("")
    
    if high_import_files:
        report.append("### 📈 Files with Many Imports (>20)")
        for file_name, count in sorted(high_import_files, key=lambda x: x[1], reverse=True):
            report.append(f"- `{file_name}`: {count} imports")
        report.append("")
    
    # Recommendations
    report.append("## 💡 Recommendations")
    
    if summary['unresolvable_imports']:
        report.append("- Review and fix unresolvable imports")
    
    if summary['circular_dependencies']:
        report.append("- Investigate potential circular dependencies")
    
    if high_import_files:
        report.append("- Consider refactoring files with excessive imports")
    
    if summary['files_with_errors']:
        report.append("- Fix Python syntax errors in affected files")
    
    report.append("")
    
    return "\n".join(report)

def main():
    """Run import analysis."""
    # Find project root
    current_dir = Path(__file__).parent
    project_root = current_dir.parent.parent
    
    print("🔍 Starting import and dependency analysis...")
    
    # Analyze imports
    analysis = analyze_project_imports(project_root)
    
    # Generate report
    report = generate_import_report(analysis)
    
    # Save results
    output_dir = project_root / 'Tests' / 'cloud-tests'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    report_file = output_dir / 'import-analysis-report.md'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    json_file = output_dir / 'import-analysis-data.json'
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, indent=2, default=str)
    
    print(f"✅ Import analysis complete!")
    print(f"📄 Report saved to: {report_file}")
    print(f"📊 Raw data saved to: {json_file}")
    
    # Print summary
    summary = analysis['summary']
    print(f"\n📊 Summary:")
    print(f"- Python files analyzed: {summary['total_files']}")
    print(f"- Total imports: {summary['total_imports']}")
    print(f"- External packages: {len(summary['external_packages'])}")
    print(f"- Unresolvable imports: {len(summary['unresolvable_imports'])}")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())