from __future__ import annotations

from dataclasses import dataclass, field

from rebrief.chat.context import ChatContext
from rebrief.core.tokens import active_tokenizer, count_tokens

SLASH_COMMANDS = frozenset({"/clear", "/copy", "/context", "/exit", "/quit"})


@dataclass
class ChatTurn:
    role: str
    content: str


@dataclass
class TokenUsage:
    context_tokens: int
    conversation_tokens: int
    total_tokens: int
    turns: int
    tokenizer: str
    model: str


@dataclass
class ChatSession:
    context: ChatContext
    model: str
    messages: list[ChatTurn] = field(default_factory=list)
    last_assistant: str = ""

    def clear(self) -> None:
        self.messages.clear()
        self.last_assistant = ""

    def add_user(self, content: str) -> None:
        self.messages.append(ChatTurn(role="user", content=content))

    def add_assistant(self, content: str) -> None:
        self.last_assistant = content
        self.messages.append(ChatTurn(role="assistant", content=content))

    def drop_last_user(self) -> None:
        if self.messages and self.messages[-1].role == "user":
            self.messages.pop()

    def history(self) -> list[dict[str, str]]:
        return [{"role": turn.role, "content": turn.content} for turn in self.messages]

    def token_usage(self) -> TokenUsage:
        conversation = "".join(turn.content for turn in self.messages)
        conversation_tokens = count_tokens(conversation)
        context_tokens = self.context.token_count
        return TokenUsage(
            context_tokens=context_tokens,
            conversation_tokens=conversation_tokens,
            total_tokens=context_tokens + conversation_tokens,
            turns=sum(1 for turn in self.messages if turn.role == "user"),
            tokenizer=active_tokenizer(),
            model=self.model,
        )

    def format_context_summary(self) -> str:
        usage = self.token_usage()
        return (
            f"model: {usage.model}\n"
            f"source: {self.context.source}\n"
            f"turns: {usage.turns}\n"
            f"context: {usage.context_tokens:,} tokens\n"
            f"conversation: {usage.conversation_tokens:,} tokens\n"
            f"total: {usage.total_tokens:,} tokens\n"
            f"tokenizer: {usage.tokenizer}"
        )
