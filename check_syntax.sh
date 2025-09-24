#!/bin/bash

# Pre-commit syntax check for Python files
echo "Checking Python syntax..."

# Check if rfp_webapp.py compiles without errors
if python -m py_compile rfp_webapp.py; then
    echo "✅ Syntax check passed - no indentation errors"
    exit 0
else
    echo "❌ Syntax check failed - indentation errors found"
    echo "Please fix the syntax errors before committing"
    exit 1
fi
