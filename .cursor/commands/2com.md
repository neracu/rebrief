Implement a module to analyze the history of decisions based on Git logs.
Create the file `rebrief/parsers/git_log.py` and the tests in `tests/test_git_log.py`.

Requirements:
1. Create a `GitLogParser` class. If the `.git` folder is missing, the `parse()` method must safely return an empty structure without causing the CLI to crash.
2. Use `subprocess` to call `git log --pretty=format:“%h|%an|%ad|%s” --date=short -n 100`.
3. Filter out “noisy” commits from AI agents using regular expressions. Ignore commits whose message exactly matches or contains patterns such as: `r'^(fix typo|wip|update|checkpoint|save|fix|refactor|cleanup|minor|test)(.*)?$'` (case-insensitive).
4. Keep only meaningful commits (the chronology of decisions), limiting the output to the last 25 entries.
5. Extract the code churn (change density): run `git log --name-only --pretty=format:` for the last 30 days and count the top 5 most frequently modified files (files that the AI endlessly rewritten).
6. Write tests (you can use mocks for `subprocess.run`).