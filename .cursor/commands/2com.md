Fix RisksParser in `rebrief/parsers/risks.py`.
Currently, it parses TODOs from third-party libraries and static files (jQuery, Bootstrap, Django Rest Framework backend/staticfiles), which clutters the report.

What needs to be done:
1. Add a strict blacklist of directories (and paths) that RisksParser must IGNORE during the build-time file scan.
2. The blacklist should include:
   - `node_modules/`, `bower_components/`
   - `staticfiles/`, `static/vendor/`, `assets/vendor/`
   - `venv/`, `.venv/`, `env/`, `site-packages/`
   - Any files with the extensions `.min.js`, `.min.css`, `.map`, `.json` (except manifests), `.md` (to avoid parsing TODOs from README files).
3. Check the file’s relative path: if it contains any of these patterns, skip it. We should look for TODOs and secrets ONLY in the source code written by the AI agent/founder (the `src/`, `app/`, `backend/`, `frontend/` folders, etc., excluding vendors).

Provide the updated code for `rebrief/parsers/risks.py`.