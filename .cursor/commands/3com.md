Implement a module to determine the technology stack.
Create the file `rebrief/parsers/stack.py` and tests in `tests/test_stack.py`.

Requirements:
1. Create a class called `StackParser`. It must accept `repo_path: str`.
2. The `parse()` method must return a dictionary containing the identified stack:
   - `languages`: a list of languages used (Python, JavaScript/TypeScript, Go, Rust, etc.) based on the manifests found.
   - `manifests`: a list of configuration files found (`package.json`, `requirements.txt`, `poetry.lock`, `pyproject.toml`, `go.mod`, `Cargo.toml`) .
   - `frameworks`: a list of detected frameworks based on signature files (for example: `next.config.js` or `next.config.mjs` -> Next.js; `manage.py` -> Django; `nuxt.config.js` -> Nuxt.js; `vite.config.js` -> Vite).
3. Parse `package.json` and `requirements.txt`/`pyproject.toml`: if these files exist, extract the main dependencies (dependencies/devDependencies) as a raw list of strings for further analysis.
4. Write tests using the `tmp_path` fixture to simulate the presence of these files in the repository.

Write clean, type-safe code without unnecessary comments.