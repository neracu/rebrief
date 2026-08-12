"use client";

import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { ScanResponse } from "@/lib/api";
import { CURSOR_PROMPT_PREFIX, formatCompactCount } from "@/lib/format";

type ResultsDashboardProps = {
  result: ScanResponse;
};

export function ResultsDashboard({ result }: ResultsDashboardProps) {
  const [tab, setTab] = useState<"preview" | "raw">("preview");
  const [copied, setCopied] = useState<string | null>(null);

  const stats = result.token_stats;
  const tags = [
    ...result.tech_stack.languages,
    ...result.tech_stack.frameworks,
    ...result.tech_stack.manifests,
  ];

  async function copy(label: string, text: string) {
    await navigator.clipboard.writeText(text);
    setCopied(label);
    window.setTimeout(() => setCopied(null), 1500);
  }

  function download() {
    const blob = new Blob([result.markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "REBRIEF.md";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  const prompt = `${CURSOR_PROMPT_PREFIX}\n\n---\n${result.markdown}`;

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-md border border-border bg-card px-2.5 py-1.5 text-[11px]">
        <p className="font-mono text-fg">
          <span className="text-muted">{formatCompactCount(stats.raw_codebase_tokens)} raw</span>
          {" → "}
          <span>{stats.brief_tokens.toLocaleString()} brief</span>
          <span className="text-muted"> | </span>
          <span className="text-accent">{stats.savings_percentage.toFixed(1)}% saved</span>
        </p>
        <p className="text-muted">
          <span className={result.risks.critical > 0 ? "text-red-400" : "text-fg"}>
            {result.risks.critical} Critical
          </span>
          {" / "}
          <span>{result.risks.warning} Warnings</span>
        </p>
        {tags.length > 0 ? (
          <ul className="flex flex-wrap gap-1.5">
            {tags.map((tag) => (
              <li
                key={tag}
                className="rounded border border-border px-1.5 py-0.5 font-mono text-[10px] text-muted"
              >
                {tag}
              </li>
            ))}
          </ul>
        ) : null}
        {result.cached ? (
          <span className="ml-auto font-mono text-[10px] text-accent">cached</span>
        ) : null}
      </div>

      <div className="overflow-hidden rounded-md border border-border bg-card">
        <div className="flex flex-wrap items-center gap-2 border-b border-border px-2 py-2">
          <div className="flex rounded border border-border p-0.5 text-[11px]">
            <TabButton active={tab === "preview"} onClick={() => setTab("preview")}>
              Formatted Preview
            </TabButton>
            <TabButton active={tab === "raw"} onClick={() => setTab("raw")}>
              Raw Markdown
            </TabButton>
          </div>
          <div className="ml-auto flex flex-wrap gap-1.5">
            <ToolbarButton
              onClick={() => copy("copy", result.markdown)}
              pressed={copied === "copy"}
            >
              {copied === "copy" ? "Copied" : "Copy to Clipboard"}
            </ToolbarButton>
            <ToolbarButton onClick={download}>Download REBRIEF.md</ToolbarButton>
            <ToolbarButton
              onClick={() => copy("prompt", prompt)}
              pressed={copied === "prompt"}
            >
              {copied === "prompt" ? "Copied" : "Copy Prompt for Cursor/Claude"}
            </ToolbarButton>
          </div>
        </div>
        <div className="max-h-[70vh] overflow-auto p-3">
          {tab === "preview" ? (
            <div className="markdown-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.markdown}</ReactMarkdown>
            </div>
          ) : (
            <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-5 text-fg">
              {result.markdown}
            </pre>
          )}
        </div>
      </div>
    </section>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        active
          ? "rounded-sm bg-accent px-2 py-0.5 font-medium text-bg"
          : "rounded-sm px-2 py-0.5 text-muted hover:text-fg"
      }
    >
      {children}
    </button>
  );
}

function ToolbarButton({
  onClick,
  children,
  pressed = false,
}: {
  onClick: () => void;
  children: React.ReactNode;
  pressed?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        pressed
          ? "rounded border border-accent px-2 py-0.5 text-[11px] text-accent"
          : "rounded border border-border bg-bg px-2 py-0.5 text-[11px] text-fg hover:border-muted"
      }
    >
      {children}
    </button>
  );
}
