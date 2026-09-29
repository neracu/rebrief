"""Web3 / Foundry integration checks for stack detection, lib/ pruning, and MD secrets.

Run offline tests (default):

    pytest tests/integration/test_web3_solidity_fixes.py

Run live clone of the target assignments repo (network + git):

    pytest -m integration tests/integration/test_web3_solidity_fixes.py
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from rebrief.core.confidence import Confidence
from rebrief.core.ignore import IgnoreMatcher
from rebrief.core.remote import resolve_remote_target, temporary_clone
from rebrief.core.scan import run_scan
from rebrief.parsers.risks import RisksParser
from rebrief.parsers.stack import StackParser

TARGET_REPO_URL = (
    "https://github.com/temitopejosiah2-source/web3bridge-solidity-assignments"
)
ANVIL_DEFAULT_PRIVATE_KEY = (
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
)

_MD_MARKER_RISK_RE = re.compile(
    r"^(TODO|FIXME|HACK|BUG) in .+\.md:\d+$"
)


def assert_web3_tech_stack(
    languages: Sequence[str],
    frameworks: Sequence[str],
    manifests: Sequence[str],
    *,
    forbidden_languages: tuple[str, ...] = ("JavaScript/TypeScript", "JavaScript", "Node.js"),
    forbidden_frameworks: tuple[str, ...] = ("React", "Next.js"),
) -> None:
    assert "Solidity" in languages
    assert "Foundry" in frameworks
    assert "foundry.toml" in manifests
    for language in forbidden_languages:
        assert language not in languages
    for framework in forbidden_frameworks:
        assert framework not in frameworks


def assert_anvil_secret_in_report(
    payload: Mapping[str, Any],
    md_path: str = "README.md",
) -> None:
    warning_messages = [item["message"] for item in payload["risk_map"]["warning"]]
    critical_messages = [item["message"] for item in payload["risk_map"]["critical"]]
    candidates = warning_messages + critical_messages
    assert any(md_path in message for message in candidates), candidates
    assert any(
        ANVIL_DEFAULT_PRIVATE_KEY in message or "[Test / Public Anvil Key]" in message
        for message in candidates
    ), candidates


def assert_no_md_marker_risks(payload: Mapping[str, Any]) -> None:
    for item in payload["risk_map"]["info"]:
        assert not _MD_MARKER_RISK_RE.match(item["message"]), item["message"]


def _seed_foundry_with_root_lib(tmp_path: Path) -> None:
    (tmp_path / "foundry.toml").write_text(
        '[profile.default]\nsrc = "src"\n',
        encoding="utf-8",
    )
    (tmp_path / "Contract.sol").write_text(
        "// SPDX-License-Identifier: MIT\npragma solidity ^0.8.0;\n",
        encoding="utf-8",
    )
    vendored = tmp_path / "lib" / "evil-lib"
    vendored.mkdir(parents=True)
    (vendored / "package.json").write_text(
        '{"dependencies": {"react": "^18.0.0"}}',
        encoding="utf-8",
    )


def _seed_combined_web3_fixture(tmp_path: Path) -> None:
    _seed_foundry_with_root_lib(tmp_path)
    (tmp_path / "test").mkdir()
    (tmp_path / "test" / "Contract.t.sol").write_text(
        "// SPDX-License-Identifier: MIT\npragma solidity ^0.8.0;\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        f"# Docs\n\nTODO document deploy steps\n\n"
        f"export PRIVATE_KEY={ANVIL_DEFAULT_PRIVATE_KEY}\n",
        encoding="utf-8",
    )


def test_web3_fixture_stack_and_lib_pruning(tmp_path: Path) -> None:
    _seed_foundry_with_root_lib(tmp_path)

    stack = StackParser(str(tmp_path)).parse()

    assert_web3_tech_stack(
        stack["languages"],
        stack["frameworks"],
        stack["manifests"],
    )


def test_web3_fixture_src_lib_not_pruned(tmp_path: Path) -> None:
    nested = tmp_path / "src" / "lib" / "nested"
    nested.mkdir(parents=True)
    manifest = nested / "package.json"
    manifest.write_text('{"name": "nested-lib"}\n', encoding="utf-8")

    relative = manifest.relative_to(tmp_path).as_posix()
    matcher = IgnoreMatcher(tmp_path)
    assert matcher.should_prune_dir("lib", "src") is False
    assert matcher.is_ignored(relative, is_dir=False) is False

    stack = StackParser(str(tmp_path)).parse()
    assert relative in stack["manifests"]
    assert "JavaScript/TypeScript" in stack["languages"]


def test_web3_fixture_markdown_secret_without_markers(tmp_path: Path) -> None:
    (tmp_path / "test").mkdir()
    (tmp_path / "README.md").write_text(
        f"# TODO readme\n\nkey: {ANVIL_DEFAULT_PRIVATE_KEY}\n",
        encoding="utf-8",
    )

    risks = RisksParser(str(tmp_path)).parse()
    assert risks["markers"] == []
    assert len(risks["secrets"]) == 1
    assert risks["secrets"][0]["file"] == "README.md"
    assert risks["secrets"][0].get("kind") == "evm_public"

    payload = run_scan(
        tmp_path,
        Confidence.LOW,
        skip_vulnerability_check=True,
    ).to_dict()
    assert_anvil_secret_in_report(payload)
    assert_no_md_marker_risks(payload)


def test_web3_fixture_full_scan_pipeline(tmp_path: Path) -> None:
    _seed_combined_web3_fixture(tmp_path)

    payload = run_scan(
        tmp_path,
        Confidence.LOW,
        skip_vulnerability_check=True,
    ).to_dict()

    tech_stack = payload["tech_stack"]
    assert_web3_tech_stack(
        tech_stack["languages"],
        tech_stack["frameworks"],
        tech_stack["manifests"],
    )
    assert_anvil_secret_in_report(payload)
    assert_no_md_marker_risks(payload)


@pytest.mark.integration
def test_live_web3bridge_assignments_scan() -> None:
    target = resolve_remote_target(TARGET_REPO_URL)
    assert target is not None

    with temporary_clone(target) as repo:
        payload = run_scan(
            repo,
            Confidence.LOW,
            skip_vulnerability_check=True,
        ).to_dict()

    tech_stack = payload["tech_stack"]
    assert_web3_tech_stack(
        tech_stack["languages"],
        tech_stack["frameworks"],
        tech_stack["manifests"],
    )
    assert_anvil_secret_in_report(payload)
    assert_no_md_marker_risks(payload)
