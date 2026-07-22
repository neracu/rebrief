# Build and validate rebrief distributions for PyPI.
# Upload (manual, after review): python -m twine upload dist/*

$ErrorActionPreference = "Stop"

python -m pip install --upgrade pip build twine
python -m build
python -m twine check dist/*
