from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import TypedDict

NOISY_COMMIT_RE = re.compile(
    r"^(fix typo|wip|update|checkpoint|save|fix|refactor|cleanup|minor|test)(.*)?$",
    re.IGNORECASE,
)
MAX_COMMITS_FETCH = 100
MAX_COMMITS_RETURN = 25
MAX_CHURN_FILES = 5
CHURN_SINCE = "30 days ago"


class GitCommit(TypedDict):
    hash: str
    author: str
    date: str
    subject: str


class ModifiedFile(TypedDict):
    file: str
    count: int


class GitLogResult(TypedDict):
    commits: list[GitCommit]
    top_modified_files: list[ModifiedFile]


def _empty_result() -> GitLogResult:
    return {
        "commits": [],
        "top_modified_files": [],
    }


class GitLogParser:
    def __init__(self, repo_path: str) -> None:
        self._repo_path = Path(repo_path)

    def parse(self) -> GitLogResult:
        if not (self._repo_path / ".git").exists():
            return _empty_result()

        try:
            log_output = self._run_git(
                [
                    "log",
                    f"--pretty=format:%h|%an|%ad|%s",
                    "--date=short",
                    f"-n{MAX_COMMITS_FETCH}",
                ]
            )
            churn_output = self._run_git(
                [
                    "log",
                    "--name-only",
                    "--pretty=format:",
                    f"--since={CHURN_SINCE}",
                ]
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return _empty_result()

        commits = self._parse_commits(log_output)[:MAX_COMMITS_RETURN]
        top_modified_files = self._parse_churn(churn_output)

        return {
            "commits": commits,
            "top_modified_files": top_modified_files,
        }

    def _run_git(self, args: list[str]) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self._repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def _parse_commits(self, raw: str) -> list[GitCommit]:
        commits: list[GitCommit] = []

        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            parts = stripped.split("|", 3)
            if len(parts) != 4:
                continue

            subject = parts[3].strip()
            if self._is_noisy(subject):
                continue

            commits.append(
                {
                    "hash": parts[0].strip(),
                    "author": parts[1].strip(),
                    "date": parts[2].strip(),
                    "subject": subject,
                }
            )

        return commits

    def _is_noisy(self, subject: str) -> bool:
        return NOISY_COMMIT_RE.match(subject) is not None

    def _parse_churn(self, raw: str) -> list[ModifiedFile]:
        counts = Counter(
            line.strip()
            for line in raw.splitlines()
            if line.strip()
        )

        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return [
            {"file": path, "count": count}
            for path, count in ranked[:MAX_CHURN_FILES]
        ]
