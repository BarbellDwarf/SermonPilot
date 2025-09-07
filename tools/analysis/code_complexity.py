#!/usr/bin/env python3
"""
Code Complexity Analysis Tool

Analyzes Python files for complexity metrics to identify refactoring opportunities.
Based on the refactoring plan in copilot-plans/code-refactoring-plan.md
"""

import ast
import os
from pathlib import Path
from typing import Dict, List, Tuple, Any
import argparse


class ComplexityAnalyzer:
    """Analyzes Python code complexity metrics."""
    
    def __init__(self, root_path: str):
        self.root_path = Path(root_path)

    def analyze_file(self, file_path: Path) -> Dict[str, Any]:
        """Analyze a single Python file for complexity metrics."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except (UnicodeDecodeError, IOError) as e:
            return {
                'file_path': str(file_path),
                'error': str(e),
                'lines_of_code': 0,
                'functions': [],
                'classes': [],
                'imports': []
            }

        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            return {
                'file_path': str(file_path),
                'error': f"Syntax error: {e}",
                'lines_of_code': len(content.splitlines()),
                'functions': [],
                'classes': [],
                'imports': []
            }

        metrics = {
            'file_path': str(file_path),
            'lines_of_code': len(content.splitlines()),
            'functions': [],
            'classes': [],
            'imports': []
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                func_info = {
                    'name': node.name,
                    'line_start': node.lineno,
                    'line_end': getattr(node, 'end_lineno', node.lineno),
                    'complexity': self._calculate_complexity(node),
                    'parameters': len(node.args.args),
                    'decorators': len(node.decorator_list)
                }
                func_info['lines'] = func_info['line_end'] - func_info['line_start'] + 1
                metrics['functions'].append(func_info)
                
            elif isinstance(node, ast.ClassDef):
                methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]
                metrics['classes'].append({
                    'name': node.name,
                    'line_start': node.lineno,
                    'line_end': getattr(node, 'end_lineno', node.lineno),
                    'methods': len(methods),
                    'method_names': [m.name for m in methods]
                })
                
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        metrics['imports'].append(alias.name)
                else:  # ImportFrom
                    if node.module:
                        metrics['imports'].append(node.module)

        return metrics

    def _calculate_complexity(self, node: ast.FunctionDef) -> int:
        """Calculate cyclomatic complexity of a function."""
        complexity = 1  # Base complexity

        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.With, ast.AsyncWith, ast.AsyncFor)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
            elif isinstance(child, ast.Try):
                complexity += len(child.handlers)
            elif isinstance(child, (ast.ExceptHandler,)):
                complexity += 1
            elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                complexity += 1

        return complexity

    def analyze_project(self, skip_patterns: List[str] = None) -> List[Dict[str, Any]]:
        """Analyze all Python files in the project."""
        if skip_patterns is None:
            skip_patterns = ['__pycache__', '.venv', '.git', 'venv', 'env', '.pytest_cache']
            
        results = []

        for py_file in self.root_path.rglob('*.py'):
            # Skip files matching skip patterns
            if any(skip in str(py_file) for skip in skip_patterns):
                continue
                
            result = self.analyze_file(py_file)
            # Make path relative to root for cleaner output
            result['file_path'] = str(py_file.relative_to(self.root_path))
            results.append(result)

        return results

    def generate_report(self, results: List[Dict[str, Any]], detailed: bool = False) -> str:
        """Generate a complexity analysis report."""
        report = ["# Code Complexity Analysis Report", ""]
        
        # Filter out files with errors
        valid_results = [r for r in results if 'error' not in r]
        error_results = [r for r in results if 'error' in r]
        
        if error_results:
            report.append("## Files with Errors")
            for result in error_results:
                report.append(f"- **{result['file_path']}**: {result['error']}")
            report.append("")

        # Sort by lines of code
        sorted_results = sorted(valid_results, key=lambda x: x['lines_of_code'], reverse=True)

        report.append("## Top Files by Size")
        report.append("| File | Lines | Functions | Classes | Avg Function Complexity |")
        report.append("|------|-------|-----------|---------|-------------------------|")
        
        for result in sorted_results[:20]:  # Top 20 most complex files
            functions = result['functions']
            avg_complexity = sum(f['complexity'] for f in functions) / len(functions) if functions else 0
            
            report.append(f"| {result['file_path']} | {result['lines_of_code']} | {len(functions)} | {len(result['classes'])} | {avg_complexity:.1f} |")

        # Identify high-complexity functions across all files
        all_functions = []
        for result in valid_results:
            for func in result['functions']:
                func_copy = func.copy()
                func_copy['file'] = result['file_path']
                all_functions.append(func_copy)
        
        # Sort by complexity
        high_complexity = [f for f in all_functions if f['complexity'] > 20]
        high_complexity.sort(key=lambda x: x['complexity'], reverse=True)
        
        if high_complexity:
            report.append("")
            report.append("## High Complexity Functions (>20)")
            report.append("| Function | File | Complexity | Lines | Parameters |")
            report.append("|----------|------|------------|-------|------------|")
            
            for func in high_complexity[:20]:  # Top 20 most complex functions
                report.append(f"| {func['name']} | {func['file']} | {func['complexity']} | {func['lines']} | {func['parameters']} |")

        # Long functions
        long_functions = [f for f in all_functions if f['lines'] > 50]
        long_functions.sort(key=lambda x: x['lines'], reverse=True)
        
        if long_functions:
            report.append("")
            report.append("## Long Functions (>50 lines)")
            report.append("| Function | File | Lines | Complexity |")
            report.append("|----------|------|-------|------------|")
            
            for func in long_functions[:20]:
                report.append(f"| {func['name']} | {func['file']} | {func['lines']} | {func['complexity']} |")

        if detailed:
            report.append("")
            report.append("## Detailed Analysis")
            
            for result in sorted_results[:5]:  # Top 5 files for detailed analysis
                report.append(f"### {result['file_path']}")
                report.append(f"- **Lines of Code**: {result['lines_of_code']}")
                report.append(f"- **Functions**: {len(result['functions'])}")
                report.append(f"- **Classes**: {len(result['classes'])}")
                report.append(f"- **Imports**: {len(result['imports'])}")
                
                # Show functions
                if result['functions']:
                    report.append("- **Functions**:")
                    for func in sorted(result['functions'], key=lambda x: x['complexity'], reverse=True)[:10]:
                        status = "🔴" if func['complexity'] > 20 else "🟡" if func['complexity'] > 10 else "🟢"
                        report.append(f"  - {status} `{func['name']}`: {func['complexity']} complexity, {func['lines']} lines")
                
                report.append("")

        return "\n".join(report)

    def get_refactoring_recommendations(self, results: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """Get specific refactoring recommendations based on analysis."""
        recommendations = {
            'critical': [],
            'high_priority': [],
            'medium_priority': []
        }
        
        valid_results = [r for r in results if 'error' not in r]
        
        for result in valid_results:
            file_path = result['file_path']
            lines = result['lines_of_code']
            functions = result['functions']
            
            # Critical: Very large files
            if lines > 2000:
                recommendations['critical'].append(
                    f"{file_path}: {lines} lines - Break into multiple modules"
                )
            
            # High priority: Large files or high complexity functions
            elif lines > 1000:
                recommendations['high_priority'].append(
                    f"{file_path}: {lines} lines - Consider splitting into modules"
                )
            
            # Check for high complexity functions
            for func in functions:
                if func['complexity'] > 30:
                    recommendations['critical'].append(
                        f"{file_path}:{func['name']}(): {func['complexity']} complexity - Urgent refactoring needed"
                    )
                elif func['complexity'] > 20:
                    recommendations['high_priority'].append(
                        f"{file_path}:{func['name']}(): {func['complexity']} complexity - Should be refactored"
                    )
                elif func['lines'] > 100:
                    recommendations['medium_priority'].append(
                        f"{file_path}:{func['name']}(): {func['lines']} lines - Consider breaking down"
                    )
        
        return recommendations


def main():
    """Main entry point for the complexity analyzer."""
    parser = argparse.ArgumentParser(description="Analyze code complexity")
    parser.add_argument("--path", default=".", help="Path to analyze (default: current directory)")
    parser.add_argument("--output", help="Output file for report")
    parser.add_argument("--detailed", action="store_true", help="Generate detailed report")
    parser.add_argument("--recommendations", action="store_true", help="Show refactoring recommendations")
    
    args = parser.parse_args()
    
    analyzer = ComplexityAnalyzer(args.path)
    print("Analyzing code complexity...")
    
    results = analyzer.analyze_project()
    report = analyzer.generate_report(results, detailed=args.detailed)
    
    if args.output:
        with open(args.output, 'w') as f:
            f.write(report)
        print(f"Report written to {args.output}")
    else:
        print("\n" + report)
    
    if args.recommendations:
        recommendations = analyzer.get_refactoring_recommendations(results)
        
        print("\n" + "="*60)
        print("REFACTORING RECOMMENDATIONS")
        print("="*60)
        
        for priority, items in recommendations.items():
            if items:
                print(f"\n{priority.upper().replace('_', ' ')}:")
                for item in items:
                    print(f"  • {item}")


if __name__ == "__main__":
    main()