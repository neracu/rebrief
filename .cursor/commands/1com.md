Fix StackParser in `rebrief/parsers/stack.py`.
Currently, it does not resolve the stack if configuration files are located in nested folders (for example, in subfolders such as `frontend/package.json` or `backend/requirements.txt`).

What to do:
1. Update the search for manifest files (`package.json`, `requirements.txt`, `pyproject.toml`, `go.mod`, `Cargo.toml`) and signature files (`next.config.js`, `manage.py`, `vite.config.js`). Don’t just search for them in the root (`repo_path`); instead, recursively traverse the directory tree (for example, using `os.walk`), but with a depth limit (`max_depth = 3`) to avoid going too deep into system folders.
2. Exclude the following folders from the search: `node_modules`, `venv`, `.venv`, `env`, `dist`, `build`, `.git`.
3. If `react` is found inside `package.json` (regardless of its location), add “React” to `frameworks`; if `next` is found, add “Next.js”.
4. If `manage.py` is found or `django` is present in `requirements.txt`, add “Django” to the frameworks. If `djangorestframework` is present, add “Django REST Framework”.

Generate the updated code for `rebrief/parsers/stack.py`.