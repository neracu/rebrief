Implement the module for generating the final report.
Create the file `rebrief/core/reporter.py` and the tests in `tests/test_reporter.py`.

Requirements:
1. Create a `ReportGenerator` class that accepts aggregated data from all Phase 1 parsers (StackParser, RulesParser, GitLogParser, RisksParser).
2. The `generate()` method must assemble the data into a single Markdown string strictly following this structure:

   # REBRIEF REPORT: [Repository Folder Name]

   ## 1. Project Overview (Executive Summary)
   - Overall impression of the repository.
   - Presence of AI instructions (.cursorrules, CLAUDE.md, etc.) with a summary (size, files found).

   ## 2. Technology Stack and Dependencies
   - Detected languages and frameworks.
   - Found manifest configuration files.
   - List of key dependencies.

   ## 3. Solution Timeline (Git History)
   - List of recent meaningful commits (without noise).
   - “Hotspots (Change Density)” section: the top 5 files that were modified most frequently (with the number of changes indicated).

   ## 4. Risk Map (AI Debt & Security)
   - Categorize risks by severity level:
     - [CRITICAL]: Hard-coded secrets/tokens.
     - [WARNING]: Missing tests (tests/ folder), duplicate dependencies.
     - [INFO]: Found TODO/FIXME/HACK entries (with file and line number).

   ## 5. Developer Checklist (“Where to Start”)
   - Automatically generated step-by-step checklist based on risks and the tech stack (for example: 1. Find hardcoded keys in file X. 2. Set up the environment for framework Y. 3. Cover critical areas with tests).

3. The `write_report(output_path)` method must safely write Markdown to a file (by default, `REBRIEF.md`).
4. Write unit tests with mock parser data to verify the correct formatting of Markdown and file writing.

Write clean code; use f-strings to build Markdown (without using external templating engines like Jinja2 to keep the package lightweight).