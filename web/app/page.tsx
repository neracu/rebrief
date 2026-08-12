"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { ChatPanel } from "@/components/ChatPanel";
import { ProgressLog, SCAN_STEPS } from "@/components/ProgressLog";
import { ResultsDashboard } from "@/components/ResultsDashboard";
import { postScan, type ScanResponse } from "@/lib/api";

const EXAMPLES = ["fastapi/fastapi", "vercel/next.js", "expressjs/express"] as const;

export default function HomePage() {
  const [url, setUrl] = useState("");
  const [scanning, setScanning] = useState(false);
  const [step, setStep] = useState(0);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ScanResponse | null>(null);
  const startedAt = useRef<number | null>(null);

  useEffect(() => {
    if (!scanning) {
      return;
    }
    const tick = window.setInterval(() => {
      if (startedAt.current !== null) {
        setElapsedMs(Date.now() - startedAt.current);
      }
    }, 250);
    const advance = window.setTimeout(() => {
      setStep((current) => (current < 1 ? 1 : current));
    }, 300);
    return () => {
      window.clearInterval(tick);
      window.clearTimeout(advance);
    };
  }, [scanning]);

  async function runScan(target: string) {
    const trimmed = target.trim();
    if (!trimmed || scanning) {
      return;
    }
    setUrl(trimmed);
    setScanning(true);
    setError(null);
    setResult(null);
    setStep(0);
    setElapsedMs(0);
    startedAt.current = Date.now();

    try {
      const payload = await postScan({ url: trimmed, min_confidence: "medium" });
      setStep(SCAN_STEPS.length - 1);
      setResult(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed.");
    } finally {
      if (startedAt.current !== null) {
        setElapsedMs(Date.now() - startedAt.current);
      }
      setScanning(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void runScan(url);
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-4xl flex-col px-4 py-6 sm:px-5">
      <header className="mb-4 space-y-0.5">
        <h1 className="text-[15px] font-semibold tracking-tight">rebrief</h1>
        <p className="text-[12px] text-muted">
          Repository summarizer for LLMs &amp; AI agents.
        </p>
      </header>

      <form onSubmit={onSubmit} className="space-y-2">
        <div className="flex flex-col gap-1.5 sm:flex-row">
          <input
            type="text"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://github.com/owner/repository"
            spellCheck={false}
            autoCapitalize="off"
            autoCorrect="off"
            className="h-8 flex-1 rounded-md border border-border bg-card px-2.5 font-mono text-[12px] text-fg outline-none placeholder:text-muted/70 focus:border-accent"
          />
          <button
            type="submit"
            disabled={scanning || !url.trim()}
            className="h-8 rounded-md bg-fg px-3 text-[12px] font-medium text-bg disabled:cursor-not-allowed disabled:opacity-40"
          >
            Generate REBRIEF
          </button>
        </div>
        <p className="flex flex-wrap gap-x-3 gap-y-1 text-[11px]">
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => void runScan(example)}
              className="font-mono text-muted underline-offset-2 hover:text-fg hover:underline"
            >
              {example}
            </button>
          ))}
        </p>
      </form>

      <div className="mt-4 space-y-3">
        <ProgressLog
          active={scanning}
          current={step}
          elapsedMs={elapsedMs}
          error={error}
          done={Boolean(result)}
        />
        {result ? <ResultsDashboard result={result} /> : null}
        {result ? <ChatPanel repoUrl={url} /> : null}
      </div>

      <footer className="mt-auto pt-8 text-[11px] text-muted">
        Local CLI: <span className="font-mono">pip install rebrief</span>
      </footer>
    </main>
  );
}
