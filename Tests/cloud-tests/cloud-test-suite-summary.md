# Cloud-Safe Test Suite Summary Report
**Generated**: 1757205776.2195537

## ⚠️ Overall Status: MOSTLY_PASSED

## 📊 Test Summary
- **Total Tests**: 4
- **Passed**: 3
- **Failed**: 1
- **Total Execution Time**: 1.2 seconds
- **Success Rate**: 75.0%

## 🔥 Critical Issues
- Configuration Validation failed: ...

## ⚠️ Warnings
- High complexity UI files detected
- Large UI files detected
- Configuration contains placeholder values
- Unresolvable imports detected
- Mock data patterns found

## 📋 Test Results Details
### ✅ UI Static Analysis
**Description**: Analyze UI component structure and complexity
**Execution Time**: 0.2 seconds
**Status**: Passed

### ❌ Configuration Validation
**Description**: Validate YAML configuration structure and completeness
**Execution Time**: 0.1 seconds
**Status**: Failed

### ✅ Import Analysis
**Description**: Check import statements and dependency resolution
**Execution Time**: 0.4 seconds
**Status**: Passed

### ✅ Quick Mock Data Detection
**Description**: Quick scan for placeholder values and test data
**Execution Time**: 0.6 seconds
**Status**: Passed

## 💡 Recommendations
- Address critical issues before production deployment
- Review warnings for code quality improvements

## 🚀 Next Steps
1. **Fix failed tests** before proceeding
2. **Address critical issues** identified
3. **Re-run test suite** to verify fixes
4. **Proceed with local testing** once all tests pass

## 📄 Detailed Reports
Individual test reports are available in `Tests/cloud-tests/`:
- `ui-static-analysis-report.md` - UI component analysis
- `config-validation-report.md` - Configuration validation
- `import-analysis-report.md` - Import and dependency analysis
- `mock-data-analysis-report.md` - Mock data detection
