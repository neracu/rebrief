"use client";

import { formatElapsed } from "@/lib/format";

export const SCAN_STEPS = [
  "Resolving HEAD",
  "Cloning --depth 50",
  "[1/4] Parsing repository manifests & tech stack...",
  "[2/4] Analyzing git history & hotspots...",
  "[3/4] Running risk detectors & confidence checks...",
  "[4/4] Calculating token metrics & generating report...",
] as const;

type ProgressLogProps = {
  active: boolean;
  current: number;
  elapsedMs: number;
  error: string | null;
  done: boolean;
};

export function ProgressLog({
  active,
  current,
  elapsedMs,
  error,
  done,
}: ProgressLogProps) {
  if (!active && !done && !error) {
    return null;
  }

  return (
    <section className="overflow-hidden rounded-md border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <span className="font-mono text-[10px] uppercase tracking-wider text-muted">
          scan log
        </span>
        <span className="font-mono text-[10px] text-muted">
          {formatElapsed(elapsedMs)}
        </span>
      </div>
      <ol className="space-y-0.5 px-2.5 py-2 font-mono text-[11px] leading-5">
        {SCAN_STEPS.map((step, index) => {
          const isDone = done || index < current;
          const isCurrent = !done && !error && index === current;
          const isPending = !done && index > current;
          let prefix = "  ";
          let color = "text-muted/50";
          if (isDone) {
            prefix = "ok";
            color = "text-accent";
          } else if (isCurrent) {
            prefix = ">";
            color = "text-fg";
          } else if (isPending) {
            prefix = "  ";
            color = "text-muted/40";
          }
          return (
            <li key={step} className={`flex gap-3 ${color}`}>
              <span className="w-4 shrink-0 text-right">{prefix}</span>
              <span>{step}</span>
            </li>
          );
        })}
        {error ? (
          <li className="flex gap-3 text-red-400">
            <span className="w-4 shrink-0 text-right">!</span>
            <span>{error}</span>
          </li>
        ) : null}
      </ol>
    </section>
  );
}
