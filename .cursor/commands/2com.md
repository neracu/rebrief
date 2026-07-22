Create a `CONTRIBUTING.md` file in the root of the repository to make it easier for external developers to get started. Keep it concise and omit the “Code Style Guidelines” section.

Include the following sections:
1. **Welcome Note:** A welcome message for contributors and the project’s philosophy (Keep it local, lightning-fast, and minimal dependencies).
2. **How to Help:** A list of areas where the community can contribute (adding parsers for new languages/frameworks to `stack.py`, improving regular expressions for searching for secrets in `risks.py`, supporting new types of context files).
3. **Local Development Setup:** A step-by-step guide to setting up your environment:
   - Clone the repository.
   - Create a virtual environment (`python -m venv .venv`).
   - Install the package in edit mode along with dependencies for testing (`pip install -e . && pip install pytest`).
4. **Running Tests:** Instructions for running tests using the `pytest` command.
5. **Submitting a Pull Request:** Checklist before submitting a PR (verify that the tests pass and that the CLI successfully handles empty folders or folders without Git history).

Write clearly, in a structured manner, and in a friendly tone.