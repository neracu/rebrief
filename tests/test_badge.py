from pathlib import Path

from rebrief.core.badge import (
    BADGE_END,
    BADGE_START,
    build_badge,
    find_readme_path,
    inject_badge_content,
    inject_readme_badge,
)


def test_build_badge_clean() -> None:
    badge = build_badge(0, 0, 0)
    assert (
        badge["badge_url"]
        == "https://img.shields.io/badge/rebrief-clean-brightgreen"
    )
    assert badge["badge_markdown"] == (
        "[![Rebrief](https://img.shields.io/badge/rebrief-clean-brightgreen)]"
        "(https://github.com/neracu/rebrief)"
    )
    assert 'src="https://img.shields.io/badge/rebrief-clean-brightgreen"' in badge[
        "badge_html"
    ]


def test_build_badge_warnings_only() -> None:
    badge = build_badge(0, 1, 1)
    assert badge["badge_url"] == "https://img.shields.io/badge/rebrief-2%20risks-yellow"
    assert badge["badge_markdown"] == (
        "[![Rebrief](https://img.shields.io/badge/rebrief-2%20risks-yellow)]"
        "(https://github.com/neracu/rebrief)"
    )


def test_build_badge_critical() -> None:
    badge = build_badge(1, 5, 2)
    assert (
        badge["badge_url"]
        == "https://img.shields.io/badge/rebrief-1%20critical-red"
    )
    assert badge["badge_markdown"] == (
        "[![Rebrief](https://img.shields.io/badge/rebrief-1%20critical-red)]"
        "(https://github.com/neracu/rebrief)"
    )


def test_inject_replaces_between_markers_only() -> None:
    original = (
        "# Project\n"
        "\n"
        "Intro paragraph stays.\n"
        "\n"
        f"{BADGE_START}\n"
        "[![Rebrief](https://img.shields.io/badge/rebrief-clean-brightgreen)]"
        "(https://github.com/neracu/rebrief)\n"
        f"{BADGE_END}\n"
        "\n"
        "## Features\n"
        "Still here.\n"
    )
    new_md = (
        "[![Rebrief](https://img.shields.io/badge/rebrief-1%20critical-red)]"
        "(https://github.com/neracu/rebrief)"
    )
    updated = inject_badge_content(original, new_md)

    assert updated.startswith("# Project\n")
    assert "Intro paragraph stays." in updated
    assert "## Features\nStill here.\n" in updated
    assert "rebrief-1%20critical-red" in updated
    assert "rebrief-clean-brightgreen" not in updated
    assert updated.count(BADGE_START) == 1
    assert updated.count(BADGE_END) == 1


def test_inject_under_primary_header_when_markers_missing() -> None:
    content = "# Demo App\n\nSome description.\n"
    badge_md = (
        "[![Rebrief](https://img.shields.io/badge/rebrief-clean-brightgreen)]"
        "(https://github.com/neracu/rebrief)"
    )
    updated = inject_badge_content(content, badge_md)

    assert updated.startswith("# Demo App\n\n")
    assert f"{BADGE_START}\n{badge_md}\n{BADGE_END}" in updated
    assert "Some description." in updated
    header_idx = updated.index("# Demo App")
    badge_idx = updated.index(BADGE_START)
    desc_idx = updated.index("Some description.")
    assert header_idx < badge_idx < desc_idx


def test_inject_prepends_when_no_h1() -> None:
    content = "No header here.\nJust text.\n"
    badge_md = (
        "[![Rebrief](https://img.shields.io/badge/rebrief-2%20risks-yellow)]"
        "(https://github.com/neracu/rebrief)"
    )
    updated = inject_badge_content(content, badge_md)

    assert updated.startswith(f"{BADGE_START}\n{badge_md}\n{BADGE_END}\n")
    assert "No header here." in updated


def test_find_readme_case_insensitive(tmp_path: Path) -> None:
    (tmp_path / "readme.md").write_text("# Hi\n", encoding="utf-8")
    found = find_readme_path(tmp_path)
    assert found is not None
    assert found.name == "readme.md"


def test_inject_readme_badge_creates_file(tmp_path: Path) -> None:
    badge_md = (
        "[![Rebrief](https://img.shields.io/badge/rebrief-clean-brightgreen)]"
        "(https://github.com/neracu/rebrief)"
    )
    path = inject_readme_badge(tmp_path, badge_md)
    assert path.name == "README.md"
    text = path.read_text(encoding="utf-8")
    assert BADGE_START in text
    assert badge_md in text
