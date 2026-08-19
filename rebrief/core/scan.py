from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path

from rebrief.core.confidence import Confidence
from rebrief.core.diff import DiffScope
from rebrief.core.reporter import ReportGenerator
from rebrief.core.tokens import count_repo_tokens
from rebrief.core.vulnerabilities import check_vulnerabilities
from rebrief.parsers.freshness import FreshnessParser
from rebrief.parsers.git_log import GitLogParser
from rebrief.parsers.ownership import OwnershipParser
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
    skip_vulnerability_check: bool = False,
    no_blame: bool = False,
    git_root: str | Path | None = None,
    path_prefix: str | None = None,
) -> ReportGenerator:
    """Run parsers and construct a ReportGenerator for the target repo."""
    step = status or (lambda _message: nullcontext())
    repo = str(Path(repo_path).resolve())
    resolved_git_root = str(Path(git_root).resolve()) if git_root is not None else None
    paths = diff_scope["files"] if diff_scope is not None else None
    diff_ref = diff_scope["ref"] if diff_scope is not None else None

    with step("[1/4] Parsing repository manifests & tech stack..."):
        stack = StackParser(repo, paths=paths).parse()
        rules = RulesParser(repo).parse()
        doc_drift = FreshnessParser(repo, stack).parse()

    with step("[2/4] Analyzing git history & hotspots..."):
        git_kwargs = {
            "git_root": resolved_git_root,
            "path_prefix": path_prefix,
        }
        if max_churn_files is None:
            git_log = GitLogParser(repo, diff_ref=diff_ref, **git_kwargs).parse()
        else:
            git_log = GitLogParser(
                repo,
                diff_ref=diff_ref,
                max_churn_files=max_churn_files,
                **git_kwargs,
            ).parse()
        ownership = OwnershipParser(
            repo,
            paths=paths,
            skip=no_blame,
            git_root=resolved_git_root,
            path_prefix=path_prefix,
        ).parse()

    with step("[3/4] Running risk detectors & vulnerability checks..."):
        risks = RisksParser(
            repo, dependencies=stack["dependencies"], paths=paths
        ).parse()
        vulnerabilities = check_vulnerabilities(
            stack["packages"],
            skip=skip_vulnerability_check,
        )

    with step("[4/4] Calculating token metrics & generating report..."):
        raw_token_stats = count_repo_tokens(repo, paths=paths)
        return ReportGenerator(
            repo,
            stack,
            rules,
            git_log,
            risks,
            min_confidence=min_confidence,
            diff_scope=diff_scope,
            raw_token_stats=raw_token_stats,
            vulnerabilities=vulnerabilities,
            skip_vulnerability_check=skip_vulnerability_check,
            ownership=ownership,
            no_blame=no_blame,
            doc_drift=doc_drift,
        )
