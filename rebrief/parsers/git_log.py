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
ITERATION_SUFFIX_RE = re.compile(
    r"^(?P<base>.+?)\s+(?P<suffix>\d+(?:\.\d+)*|\w+)$",
    re.IGNORECASE,
)
MAX_COMMITS_FETCH = 100
MAX_COMMITS_RETURN = 25
MAX_CHURN_FILES = 5
CHURN_SINCE = "30 days ago"
POINT_ZERO_MESSAGE = "No commits detected yet. Repository is at point zero."


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
    status_message: str | None


def _empty_result(status_message: str | None = None) -> GitLogResult:
    return {
        "commits": [],
        "top_modified_files": [],
        "status_message": status_message,
    }


class GitLogParser:
    def __init__(
        self,
        repo_path: str,
        diff_ref: str | None = None,
        max_churn_files: int = MAX_CHURN_FILES,
        *,
        git_root: str | Path | None = None,
        path_prefix: str | None = None,
    ) -> None:
        self._repo_path = Path(repo_path)
        self._git_root = Path(git_root) if git_root is not None else self._repo_path
        self._path_prefix = path_prefix
        self._diff_ref = diff_ref
        self._max_churn_files = max_churn_files

    def parse(self) -> GitLogResult:
        if not (self._git_root / ".git").exists():
            return _empty_result(POINT_ZERO_MESSAGE)

        if self._diff_ref is not None:
            return self._parse_diff_range()

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
            return _empty_result(POINT_ZERO_MESSAGE)

        commits = self._collapse_iteration_series(
            self._parse_commits(log_output)
        )[:MAX_COMMITS_RETURN]
        top_modified_files = self._parse_churn(churn_output)

        return {
            "commits": commits,
            "top_modified_files": top_modified_files,
            "status_message": None,
        }

    def _parse_diff_range(self) -> GitLogResult:
        assert self._diff_ref is not None
        range_spec = f"{self._diff_ref}...HEAD"
        try:
            log_output = self._run_git(
                [
                    "log",
                    range_spec,
                    f"--pretty=format:%h|%an|%ad|%s",
                    "--date=short",
                    f"-n{MAX_COMMITS_FETCH}",
                ]
            )
            numstat_output = self._run_git(
                [
                    "diff",
                    "--numstat",
                    range_spec,
                ]
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return _empty_result(POINT_ZERO_MESSAGE)

        commits = self._collapse_iteration_series(
            self._parse_commits(log_output)
        )[:MAX_COMMITS_RETURN]
        top_modified_files = self._parse_numstat(numstat_output)

        return {
            "commits": commits,
            "top_modified_files": top_modified_files,
            "status_message": None,
        }

    def _run_git(self, args: list[str]) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self._git_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def _matches_prefix(self, path: str) -> bool:
        if self._path_prefix is None:
            return True
        normalized = path.replace("\\", "/")
        prefix = self._path_prefix
        if prefix.endswith("/"):
            return normalized.startswith(prefix) or normalized == prefix.rstrip("/")
        return normalized.startswith(f"{prefix}/") or normalized == prefix

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

    def _split_iteration_subject(self, subject: str) -> tuple[str, str] | None:
        match = ITERATION_SUFFIX_RE.match(subject)
        if match is None:
            return None
        return match.group("base"), match.group("suffix")

    def _collapse_iteration_series(self, commits: list[GitCommit]) -> list[GitCommit]:
        if not commits:
            return []

        result: list[GitCommit] = []
        index = 0
        while index < len(commits):
            parsed = self._split_iteration_subject(commits[index]["subject"])
            if parsed is None:
                result.append(commits[index])
                index += 1
                continue

            base, _ = parsed
            end = index + 1
            while end < len(commits):
                next_parsed = self._split_iteration_subject(commits[end]["subject"])
                if next_parsed is None or next_parsed[0].casefold() != base.casefold():
                    break
                end += 1

            group = commits[index:end]
            if len(group) >= 2:
                result.append(
                    {
                        "hash": group[0]["hash"],
                        "author": group[0]["author"],
                        "date": f"{group[-1]['date']} — {group[0]['date']}",
                        "subject": f"{base}: {len(group)} iterations",
                    }
                )
            else:
                result.append(commits[index])
            index = end

        return result

    def _parse_churn(self, raw: str) -> list[ModifiedFile]:
        counts = Counter(
            line.strip()
            for line in raw.splitlines()
            if line.strip() and self._matches_prefix(line.strip())
        )

        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return [
            {"file": path, "count": count}
            for path, count in ranked[: self._max_churn_files]
        ]

    def _parse_numstat(self, raw: str) -> list[ModifiedFile]:
        counts: Counter[str] = Counter()

        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            parts = stripped.split("\t")
            if len(parts) < 3:
                continue
            added_raw, deleted_raw, path = parts[0], parts[1], parts[2]
            # Binary files show "-" for counts; skip deleted-only missing paths later.
            if added_raw == "-" or deleted_raw == "-":
                continue
            try:
                changes = int(added_raw) + int(deleted_raw)
            except ValueError:
                continue
            if changes <= 0:
                continue
            # Renames may appear as "old => new"; take the new side.
            if " => " in path:
                path = path.split(" => ", 1)[1]
            path = path.replace("\\", "/")
            if not self._matches_prefix(path):
                continue
            if not (self._git_root / path).is_file():
                continue
            counts[path] += changes

        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return [
            {"file": path, "count": count}
            for path, count in ranked[: self._max_churn_files]
        ]
