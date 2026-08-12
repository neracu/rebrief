from __future__ import annotations

import platform
import subprocess
from collections.abc import Callable, Iterator

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from rebrief.chat.client import stream_completion
from rebrief.chat.credentials import ChatError, ResolvedAuth
from rebrief.chat.session import ChatSession
from rebrief.core.tokens import format_compact_count

StreamFactory = Callable[..., Iterator[str]]


def copy_to_clipboard(text: str) -> None:
    if not text:
        raise ChatError("No assistant reply to copy.")
    encoded = text.encode("utf-8")
    system = platform.system()
    try:
        if system == "Windows":
            subprocess.run(
                ["clip"],
                input=text,
                text=True,
                check=True,
                encoding="utf-8",
            )
            return
        if system == "Darwin":
            subprocess.run(["pbcopy"], input=encoded, check=True)
            return
        for command in (["wl-copy"], ["xclip", "-selection", "clipboard"]):
            try:
                subprocess.run(command, input=encoded, check=True)
                return
            except FileNotFoundError:
                continue
        raise ChatError("Clipboard tool not found (install wl-copy or xclip).")
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ChatError(f"Could not copy to clipboard: {exc}") from exc


def run_repl(
    session: ChatSession,
    auth: ResolvedAuth,
    console: Console,
    *,
    stream: StreamFactory = stream_completion,
) -> None:
    _print_header(session, console)
    console.print(
        "[dim]/clear  /copy  /context  /exit[/dim]",
        highlight=False,
    )
    while True:
        try:
            line = Prompt.ask("[bold cyan]You[/bold cyan]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            return
        text = (line or "").strip()
        if not text:
            continue
        if text in {"/exit", "/quit"}:
            console.print("[dim]Goodbye.[/dim]")
            return
        if text == "/clear":
            session.clear()
            console.print("[dim]Conversation memory cleared.[/dim]")
            continue
        if text == "/copy":
            try:
                copy_to_clipboard(session.last_assistant)
            except ChatError as exc:
                console.print(f"[yellow]{exc}[/yellow]")
            else:
                console.print("[dim]Copied last reply to clipboard.[/dim]")
            continue
        if text == "/context":
            console.print(session.format_context_summary())
            continue
        if text.startswith("/"):
            console.print("[yellow]Unknown command. Use /clear, /copy, /context, /exit.[/yellow]")
            continue

        session.add_user(text)
        chunks: list[str] = []
        try:
            iterator = stream(
                auth=auth,
                system_prompt=session.context.system_prompt,
                messages=session.history(),
            )
            with Live(
                Markdown(""),
                console=console,
                refresh_per_second=12,
                vertical_overflow="visible",
            ) as live:
                for delta in iterator:
                    chunks.append(delta)
                    live.update(Markdown("".join(chunks) or "…"))
        except ChatError as exc:
            session.drop_last_user()
            console.print(f"[red]{exc}[/red]")
            continue
        except (KeyboardInterrupt, EOFError):
            session.drop_last_user()
            console.print("\n[dim]Interrupted.[/dim]")
            continue
        reply = "".join(chunks)
        session.add_assistant(reply)
        if not reply:
            console.print("[dim](empty reply)[/dim]")


def _print_header(session: ChatSession, console: Console) -> None:
    usage = session.token_usage()
    body = (
        f"model: {session.model}\n"
        f"context: {format_compact_count(usage.context_tokens)} tokens "
        f"({session.context.source})"
    )
    console.print(
        Panel(
            body,
            title="rebrief chat",
            border_style="cyan",
        )
    )
