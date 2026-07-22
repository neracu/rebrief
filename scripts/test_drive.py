from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import colorama
from colorama import Fore, Style

from rebrief.parsers.git_log import MAX_COMMITS_FETCH, GitLogParser
from rebrief.parsers.risks import RisksParser
from rebrief.parsers.rules import RulesParser
from rebrief.parsers.stack import StackParser


def _count_raw_commits(repo_path: Path) -> int:
    if not (repo_path / ".git").exists():
        return 0

    try:
        result = subprocess.run(
            [
                "git",
                "log",
                f"-n{MAX_COMMITS_FETCH}",
                "--pretty=format:%s",
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return 0

    return len([line for line in result.stdout.splitlines() if line.strip()])


def _count_risks(risks: dict) -> int:
    return (
        len(risks["secrets"])
        + len(risks["markers"])
        + len(risks["dependency_conflicts"])
        + (1 if risks["missing_tests"] else 0)
    )


def _run_rebrief_scan(project_path: str, output: str) -> None:
    commands = [
        ["rebrief", "scan", project_path, "-o", output],
        [sys.executable, "-m", "rebrief.cli", "scan", project_path, "-o", output],
    ]

    last_error: subprocess.CalledProcessError | FileNotFoundError | None = None

    for command in commands:
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            return
        except FileNotFoundError as exc:
            last_error = exc
        except subprocess.CalledProcessError as exc:
            last_error = exc

    if isinstance(last_error, subprocess.CalledProcessError):
        raise last_error
    if last_error is not None:
        raise last_error


def _print_failure(project_path: str, message: str) -> None:
    print(f"{Fore.RED}{Style.BRIGHT}[FAIL]{Style.RESET_ALL} {project_path}")
    print(f"  {message}")


def run_project(project_path: str, output: str = "REBRIEF.md") -> bool:
    repo_path = Path(project_path).resolve()

    if not repo_path.is_dir():
        _print_failure(project_path, "Path is not a directory.")
        return False

    try:
        _run_rebrief_scan(str(repo_path), output)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        detail = stderr or stdout or str(exc)
        _print_failure(str(repo_path), detail)
        return False
    except FileNotFoundError:
        _print_failure(str(repo_path), "rebrief command not found.")
        return False
    except OSError as exc:
        _print_failure(str(repo_path), str(exc))
        return False

    stack = StackParser(str(repo_path)).parse()
    RulesParser(str(repo_path)).parse()
    git_log = GitLogParser(str(repo_path)).parse()
    risks = RisksParser(str(repo_path), dependencies=stack["dependencies"]).parse()

    risk_count = _count_risks(risks)
    raw_commits = _count_raw_commits(repo_path)
    commits_filtered = max(0, raw_commits - len(git_log["commits"]))
    report_path = repo_path / output
    report_created = report_path.is_file()

    if report_created:
        status = f"{Fore.GREEN}{Style.BRIGHT}[SUCCESS]{Style.RESET_ALL}"
    else:
        status = f"{Fore.RED}{Style.BRIGHT}[FAIL]{Style.RESET_ALL}"

    print(f"{status} {repo_path}")
    print(f"  Risks found:       {risk_count}")
    print(f"  Commits filtered:  {commits_filtered}")
    print(
        f"  Report created:    {'yes' if report_created else 'no'} ({output})"
    )

    return report_created


def main() -> None:
    colorama.init()
    paths = sys.argv[1:]

    if not paths:
        print("Usage: python scripts/test_drive.py <repo_path> [...]")
        sys.exit(1)

    results = [run_project(path) for path in paths]
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
