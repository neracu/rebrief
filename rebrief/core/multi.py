from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from typing import TYPE_CHECKING

from rebrief.core.confidence import Confidence
from rebrief.core.remote import (
    RemoteCloneError,
    resolve_remote_target,
    temporary_clone,
)
from rebrief.core.scan import run_scan
from rebrief.core.system_report import ScannedService, SystemReportGenerator
from rebrief.core.workspace import WorkspaceMember, expand_workspace_members
from rebrief.ui import ScanUI

if TYPE_CHECKING:
    from rebrief.core.config import SecretPatternConfig


def _resolve_local_target(target: str) -> Path:
    path = Path(target).expanduser()
    try:
        resolved = path.resolve()
    except OSError as exc:
        raise FileNotFoundError(f"Path does not exist: {target}") from exc
    if not resolved.exists():
        raise FileNotFoundError(f"Path does not exist: {target}")
    if not resolved.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {target}")
    return resolved


def resolve_target_members(
    targets: list[str],
    stack: ExitStack,
    *,
    scan_ui: ScanUI,
) -> list[WorkspaceMember]:
    if not targets:
        targets = ["."]

    members: list[WorkspaceMember] = []
    for target in targets:
        remote = resolve_remote_target(target)
        if remote is not None:
            scan_ui.console.print(scan_ui.fetch_message(remote.display_name), markup=False)
            try:
                repo = stack.enter_context(
                    temporary_clone(
                        remote,
                        status=lambda: scan_ui.clone_status(remote.display_name),
                    )
                )
            except RemoteCloneError:
                raise
            members.extend(expand_workspace_members(repo, source=target))
            continue

        root = _resolve_local_target(target)
        members.extend(expand_workspace_members(root, source=target))

    return _dedupe_members(members)


def _dedupe_members(members: list[WorkspaceMember]) -> list[WorkspaceMember]:
    seen: set[str] = set()
    result: list[WorkspaceMember] = []
    for member in members:
        key = str(Path(member["path"]).resolve())
        if key in seen:
            continue
        seen.add(key)
        result.append(member)
    return result


def run_multi_scan(
    members: list[WorkspaceMember],
    min_confidence: Confidence,
    *,
    scan_ui: ScanUI,
    skip_vulnerability_check: bool = False,
    no_blame: bool = False,
    max_churn_files: int | None = None,
    extra_ignore_patterns: tuple[str, ...] | None = None,
    entropy_cutoff: float | None = None,
    custom_secret_patterns: tuple[SecretPatternConfig, ...] | None = None,
) -> list[ScannedService]:
    services: list[ScannedService] = []
    total = len(members)

    for index, member in enumerate(members, start=1):
        scan_ui.console.print(
            f"Scanning {member['name']} ({index}/{total})...",
            markup=False,
        )
        with scan_ui.scan_progress() as status:
            generator = run_scan(
                member["path"],
                min_confidence,
                status=status,
                skip_vulnerability_check=skip_vulnerability_check,
                no_blame=no_blame,
                git_root=member["git_root"],
                path_prefix=member["path_prefix"],
                max_churn_files=max_churn_files,
                extra_ignore_patterns=extra_ignore_patterns,
                entropy_cutoff=entropy_cutoff,
                custom_secret_patterns=custom_secret_patterns,
            )
        services.append(
            ScannedService(
                name=member["name"],
                source=member["source"],
                generator=generator,
            )
        )

    return services


def build_system_report(services: list[ScannedService]) -> SystemReportGenerator:
    return SystemReportGenerator(services)
