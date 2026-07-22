Implement a module for collecting context and instructions for AI agents.
Create the file `rebrief/parsers/rules.py` and tests in `tests/test_rules.py`.

Requirements:
1. Create a `RulesParser` class.
2. Scan the root of the repository for the following files (case-insensitive): `.cursorrules`, `CLAUDE.md`, `AGENTS.md`, `.claudecode`, `README.md`.
3. If a file is found:
   - Read its contents (handle encoding errors; use `errors=‘ignore’`).
   - Extract a brief summary: the file size in lines and the first 5–10 lines as a preview (for README), or the full text (for small configuration files like `.cursorrules`, if they are fewer than 200 lines).
4. The `parse()` method must return a data structure: `{“filename”: {‘content’: “...”, “lines_count”: X}}`.
5. Write unit tests to verify that existing files are read correctly and missing files are ignored.