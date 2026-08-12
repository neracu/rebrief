from __future__ import annotations

from unittest.mock import patch

import pytest

from rebrief.chat.context import ChatContext, format_system_prompt
from rebrief.chat.credentials import ChatError
from rebrief.chat.repl import copy_to_clipboard
from rebrief.chat.session import ChatSession


def _session() -> ChatSession:
    prompt = format_system_prompt("# brief")
    context = ChatContext(
        content="# brief",
        source="REBRIEF.md",
        system_prompt=prompt,
        token_count=12,
    )
    return ChatSession(context=context, model="openai/gpt-4o-mini")


def test_clear_resets_turns_keeps_context() -> None:
    session = _session()
    session.add_user("hello")
    session.add_assistant("world")
    assert session.last_assistant == "world"
    session.clear()
    assert session.messages == []
    assert session.last_assistant == ""
    assert session.context.content == "# brief"
    assert "BEGIN REBRIEF CONTEXT" in session.context.system_prompt


def test_token_usage_summary() -> None:
    session = _session()
    session.add_user("What is the stack?")
    session.add_assistant("Python.")
    summary = session.format_context_summary()
    assert "openai/gpt-4o-mini" in summary
    assert "turns: 1" in summary
    assert "context:" in summary
    assert "conversation:" in summary
    assert "total:" in summary
    usage = session.token_usage()
    assert usage.total_tokens == usage.context_tokens + usage.conversation_tokens
    assert usage.turns == 1


def test_copy_uses_last_assistant() -> None:
    session = _session()
    with pytest.raises(ChatError, match="No assistant reply"):
        copy_to_clipboard(session.last_assistant)
    session.add_assistant("copy me")
    with patch("rebrief.chat.repl.subprocess.run") as run:
        copy_to_clipboard(session.last_assistant)
    run.assert_called_once()
    assert run.call_args.kwargs["input"] in ("copy me", b"copy me")
