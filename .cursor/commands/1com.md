Rewrite `README.md`, ensuring the utility is positioned as a universal tool for any source code (not just AI-generated). The text must be in English, concise, and professionally formatted.

The README structure should be as follows:
1. **Header:** Project name `rebrief`, a concise subtitle (e.g., “Instantly turn any unfamiliar repository into a clean developer handoff dossier”).
2. **The Pain (HN / Product Hunt Style):** A short paragraph about the real pain points of onboarding. When a developer joins a new project (after working with outsourcing teams, freelancers, or years of legacy development), the first week goes down the drain: manually digging through the tech stack, searching for hidden TODOs, sorting through a chaotic Git history, and identifying risks.
3. **The Solution (Before vs. After):**
   - *Before:* 1 week of manually digging through code, guessing project boundaries, and hunting for hidden setup context.
   - *After:* A 30-second local scan, generating a structured, human-readable `REBRIEF.md` report.
4. **Demo Placeholder:** A text block for a future GIF/Asciinema demonstration of the CLI’s rich output.
5. **Key Features:**
   - Deep Stack & Manifest Detection: A deep, recursive scan for languages and frameworks (Django, React, Next.js, Go, etc.) across complex or mono-repositories.
   - Context & Rules Harvesting: Automatically extracts local context from files such as `.cursorrules`, `CLAUDE.md`, and `README.md`.
   - Noise-Filtered Git Archaeology: Filters out low-value semantic noise (wip, fix typo, minor updates) to provide a clean chronological timeline of architectural decisions and identifies high-churn hotspots.
   - Local-First Risk Mapping: Instant static analysis for hardcoded secrets, unresolved technical debt (TODO/FIXME), and missing test coverage.
6. **Installation & Quick Start:** Install via PyPI (`pip install rebrief`) and run (`rebrief scan .`).
7. **Example Output:** A brief overview of what the generated `REBRIEF.md` file looks like.

Use modern Markdown formatting (templates, lists, code blocks). Keep the text strictly to the point, avoiding an excessive focus on AI code.