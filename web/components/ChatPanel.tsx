"use client";

import { FormEvent, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { streamChat, type ChatMessage } from "@/lib/api";

type ChatPanelProps = {
  repoUrl: string;
};

export function ChatPanel({ repoUrl }: ChatPanelProps) {
  const [model, setModel] = useState("openai/gpt-4o-mini");
  const [apiKey, setApiKey] = useState("");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = input.trim();
    if (!question || busy) {
      return;
    }
    const nextMessages: ChatMessage[] = [...messages, { role: "user", content: question }];
    setMessages(nextMessages);
    setInput("");
    setDraft("");
    setError(null);
    setBusy(true);
    let reply = "";
    try {
      await streamChat(
        {
          repo_url: repoUrl,
          messages: nextMessages,
          api_key: apiKey.trim() || undefined,
          model: model.trim() || undefined,
        },
        (delta) => {
          reply += delta;
          setDraft(reply);
        },
      );
      if (reply) {
        setMessages([...nextMessages, { role: "assistant", content: reply }]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chat failed.");
      setMessages(messages);
    } finally {
      setBusy(false);
      setDraft("");
    }
  }

  return (
    <section className="overflow-hidden rounded-md border border-border bg-card">
      <div className="border-b border-border px-2.5 py-2">
        <p className="text-[12px] font-medium">Ask this repo</p>
        <p className="text-[11px] text-muted">
          BYO API key is kept in memory only and is never stored.
        </p>
      </div>
      <div className="flex flex-col gap-1.5 border-b border-border p-2 sm:flex-row">
        <input
          type="text"
          value={model}
          onChange={(event) => setModel(event.target.value)}
          placeholder="openai/gpt-4o-mini"
          spellCheck={false}
          className="h-7 flex-1 rounded-md border border-border bg-bg px-2 font-mono text-[11px] text-fg outline-none"
        />
        <input
          type="password"
          value={apiKey}
          onChange={(event) => setApiKey(event.target.value)}
          placeholder="API key (optional if the server has env keys)"
          autoComplete="off"
          className="h-7 flex-1 rounded-md border border-border bg-bg px-2 font-mono text-[11px] text-fg outline-none"
        />
      </div>
      <div className="flex max-h-72 flex-col gap-2 overflow-auto p-2.5">
        {messages.map((message, index) => (
          <div
            key={`${message.role}-${index}`}
            className={
              message.role === "user"
                ? "ml-auto max-w-[90%] rounded-md border border-border bg-bg px-2 py-1.5 text-[12px]"
                : "markdown-body rounded-md border border-border px-2 py-1.5"
            }
          >
            {message.role === "assistant" ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
            ) : (
              message.content
            )}
          </div>
        ))}
        {draft ? (
          <div className="markdown-body rounded-md border border-border px-2 py-1.5">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{draft}</ReactMarkdown>
          </div>
        ) : null}
        {error ? <p className="text-[12px] text-red-400">{error}</p> : null}
      </div>
      <form onSubmit={onSubmit} className="flex gap-1.5 border-t border-border p-2">
        <input
          type="text"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask about this repo’s architecture, hotspots, or risks…"
          autoComplete="off"
          className="h-8 flex-1 rounded-md border border-border bg-bg px-2.5 text-[12px] text-fg outline-none"
        />
        <button
          type="submit"
          disabled={busy || !input.trim()}
          className="h-8 rounded-md bg-fg px-3 text-[12px] font-medium text-bg disabled:cursor-not-allowed disabled:opacity-40"
        >
          Send
        </button>
      </form>
    </section>
  );
}
