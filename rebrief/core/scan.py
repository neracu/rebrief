from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import TYPE_CHECKING

from rebrief.core.confidence import Confidence
from rebrief.core.diff import DiffScope
from rebrief.core.reporter import ReportGenerator
from rebrief.core.tokens import count_repo_tokens
from rebrief.core.vulnerabilities import check_vulnerabilities
from rebrief.parsers.freshness import FreshnessParser
from rebrief.parsers.git_log import GitLogParser
from rebrief.parsers.ownership import OwnershipParser
from rebrief.parsers.risks import ENTROPY_THRESHOLD, RisksParser
from rebrief.parsers.rules import RulesParser
from rebrief.parsers.stack import StackParser

if TYPE_CHECKING:
    import re

    from rebrief.core.config import SecretPatternConfig

StatusFactory = Callable[[str], AbstractContextManager[object]]


def _pattern_pairs(
    custom_secret_patterns: tuple[SecretPatternConfig, ...] | None,
) -> tuple[tuple[re.Pattern[str], Confidence], ...]:
    if not custom_secret_patterns:
        return ()
    return tuple((pattern.regex, pattern.confidence) for pattern in custom_secret_patterns)


def run_scan(
    repo_path: str | Path,
    min_confidence: Confidence,
    *,
    diff_scope: DiffScope | None = None,
    max_churn_files: int | None = None,
    extra_ignore_patterns: tuple[str, ...] | None = None,
    entropy_cutoff: float | None = None,
    custom_secret_patterns: tuple[SecretPatternConfig, ...] | None = None,
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
    ignore_patterns = extra_ignore_patterns or ()
    resolved_entropy_cutoff = (
        entropy_cutoff if entropy_cutoff is not None else ENTROPY_THRESHOLD
    )
    secret_patterns = _pattern_pairs(custom_secret_patterns)

    with step("[1/4] Parsing repository manifests & tech stack..."):
        stack = StackParser(
            repo, paths=paths, extra_ignore_patterns=ignore_patterns
        ).parse()
        rules = RulesParser(repo).parse()
        doc_drift = FreshnessParser(
            repo, stack, extra_ignore_patterns=ignore_patterns
        ).parse()

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
            extra_ignore_patterns=ignore_patterns,
        ).parse()

    with step("[3/4] Running risk detectors & vulnerability checks..."):
        risks = RisksParser(
            repo,
            dependencies=stack["dependencies"],
            paths=paths,
            extra_ignore_patterns=ignore_patterns,
            entropy_cutoff=resolved_entropy_cutoff,
            custom_patterns=secret_patterns,
        ).parse()
        vulnerabilities = check_vulnerabilities(
            stack["packages"],
            skip=skip_vulnerability_check,
        )

    with step("[4/4] Calculating token metrics & generating report..."):
        raw_token_stats = count_repo_tokens(
            repo, paths=paths, extra_ignore_patterns=ignore_patterns
        )
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
