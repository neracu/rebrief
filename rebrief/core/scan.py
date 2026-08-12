from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path

from rebrief.core.confidence import Confidence
from rebrief.core.diff import DiffScope
from rebrief.core.reporter import ReportGenerator
from rebrief.parsers.git_log import GitLogParser
from rebrief.parsers.risks import RisksParser
from rebrief.parsers.rules import RulesParser
from rebrief.parsers.stack import StackParser

StatusFactory = Callable[[str], AbstractContextManager[object]]


def run_scan(
    repo_path: str | Path,
    min_confidence: Confidence,
    *,
    diff_scope: DiffScope | None = None,
    max_churn_files: int | None = None,
    status: StatusFactory | None = None,
) -> ReportGenerator:
    """Run parsers and construct a ReportGenerator for the target repo."""
    step = status or (lambda _message: nullcontext())
    repo = str(repo_path)
    paths = diff_scope["files"] if diff_scope is not None else None
    diff_ref = diff_scope["ref"] if diff_scope is not None else None

    with step("Analyzing technology stack..."):
        stack = StackParser(repo, paths=paths).parse()

    with step("Parsing AI rules..."):
        rules = RulesParser(repo).parse()

    with step("Reading git history..."):
        if max_churn_files is None:
            git_log = GitLogParser(repo, diff_ref=diff_ref).parse()
        else:
            git_log = GitLogParser(
                repo, diff_ref=diff_ref, max_churn_files=max_churn_files
            ).parse()

    with step("Scanning for risks..."):
        risks = RisksParser(
            repo, dependencies=stack["dependencies"], paths=paths
        ).parse()

    return ReportGenerator(
        repo,
        stack,
        rules,
        git_log,
        risks,
        min_confidence=min_confidence,
        diff_scope=diff_scope,
    )
