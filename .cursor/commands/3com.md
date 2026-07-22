Implement a static risk analyzer for Vibe code.
Create the file `rebrief/parsers/risks.py` and tests in `tests/test_risks.py`.

Requirements:
1. Create a `RisksParser` class.
2. Check for the presence of a test directory in the project root. Look for folders named `tests/`, `test/`, or `__tests__/`. If they are missing, log a risk for the absence of tests.
3. Scan all indexable text files in the project line by line (excluding files listed in `.gitignore` or `.cursorignore`, if provided, as well as binaries):
   - Look for the markers `TODO`, `FIXME`, `HACK`, `BUG` (using regex). Collect the filename and line number.
   - Look for patterns of potential hard-coded secrets using simple, lightweight regular expressions (for example, `(?:secret|password|api_key|token|passwd)\s*=\s*[‘“][a-zA-Z0-9_\-]{16,}[’”]`).
4. Check for duplicates: if `StackParser` has passed a list of dependencies from `package.json` or `requirements.txt`, check it for obvious duplicate libraries or version conflicts (if the same library is listed twice with different versions).
5. The `parse()` method returns a structured risk report. Write the corresponding tests.