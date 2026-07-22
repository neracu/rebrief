#!/usr/bin/env bash
# Build and validate rebrief distributions for PyPI.
#
# PowerShell equivalent:
#   pip install --upgrade pip build twine
#   python -m build
#   python -m twine check dist/*
#
# Upload (manual, after review):
#   python -m twine upload dist/*

set -euo pipefail

python -m pip install --upgrade pip build twine
python -m build
python -m twine check dist/*
