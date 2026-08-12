export function formatCompactCount(count: number): string {
  if (count >= 1_000_000) {
    const value = count / 1_000_000;
    const text = value.toFixed(1).replace(/\.0$/, "");
    return `${text}M`;
  }
  if (count >= 1_000) {
    const value = count / 1_000;
    const text = value.toFixed(1).replace(/\.0$/, "");
    return `${text}k`;
  }
  return String(count);
}

export function formatElapsed(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export const CURSOR_PROMPT_PREFIX =
  "Read the following REBRIEF.md before starting to understand the project's architecture and hotspots.";
