import * as fs from "fs/promises";
import * as path from "path";
import * as vscode from "vscode";
import { getSettings, type ReportFormat } from "./config";
import { ensureExecutable, runCommand } from "./cli";

export interface ScanSummary {
  repoName: string;
  folder: string;
  scannedAt: string;
  critical: number;
  warning: number;
  info: number;
  format: ReportFormat;
}

export interface ScanCache {
  folder: string;
  htmlPath: string;
  html: string;
  markdown: string;
  prompt: string;
  summary: ScanSummary;
}

const CACHE_DIR = "scans";
const HTML_NAME = "REBRIEF.html";
const META_NAME = "meta.json";

function decodeHtmlEntities(value: string): string {
  return value
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
}

function extractBetweenTags(
  html: string,
  tag: string,
  id: string,
): string | null {
  const open = new RegExp(
    `<${tag}[^>]*id=["']${id}["'][^>]*>([\\s\\S]*?)</${tag}>`,
    "i",
  );
  const match = html.match(open);
  if (!match) {
    return null;
  }
  return decodeHtmlEntities(match[1].trim());
}

function extractTextarea(html: string, id: string): string | null {
  const open = new RegExp(
    `<textarea[^>]*id=["']${id}["'][^>]*>([\\s\\S]*?)</textarea>`,
    "i",
  );
  const match = html.match(open);
  if (!match) {
    return null;
  }
  return decodeHtmlEntities(match[1].trim());
}

function countRiskCards(html: string, severity: string): number {
  const pattern = new RegExp(
    `class="risk-card"[^>]*data-severity=["']${severity}["']`,
    "gi",
  );
  return (html.match(pattern) ?? []).length;
}

function parseRepoName(html: string, folder: string): string {
  const titleMatch = html.match(/<title>([^<]+)<\/title>/i);
  if (titleMatch) {
    const title = decodeHtmlEntities(titleMatch[1].trim());
    const parts = title.split("—");
    if (parts.length > 1) {
      return parts.slice(1).join("—").trim();
    }
    return title;
  }
  return path.basename(folder);
}

export function parseScanArtifacts(
  html: string,
  folder: string,
  format: ReportFormat,
): Omit<ScanCache, "htmlPath" | "folder"> {
  const markdown = extractBetweenTags(html, "code", "raw-md") ?? "";
  const prompt = extractTextarea(html, "copy-prompt") ?? "";
  const summary: ScanSummary = {
    repoName: parseRepoName(html, folder),
    folder,
    scannedAt: new Date().toISOString(),
    critical: countRiskCards(html, "CRITICAL"),
    warning: countRiskCards(html, "WARNING"),
    info: countRiskCards(html, "INFO"),
    format,
  };
  return { html, markdown, prompt, summary };
}

function cacheKeyForFolder(folder: string): string {
  return Buffer.from(folder).toString("base64url");
}

export function getCacheDir(context: vscode.ExtensionContext): string {
  return path.join(context.globalStorageUri.fsPath, CACHE_DIR);
}

export async function getCacheForFolder(
  context: vscode.ExtensionContext,
  folder: string,
): Promise<ScanCache | null> {
  const key = cacheKeyForFolder(folder);
  const base = path.join(getCacheDir(context), key);
  const htmlPath = path.join(base, HTML_NAME);
  const metaPath = path.join(base, META_NAME);
  try {
    const [html, metaRaw] = await Promise.all([
      fs.readFile(htmlPath, "utf8"),
      fs.readFile(metaPath, "utf8"),
    ]);
    const meta = JSON.parse(metaRaw) as ScanCache;
    return {
      ...meta,
      folder,
      htmlPath,
      html,
    };
  } catch {
    return null;
  }
}

async function writeWorkspaceReport(
  folder: string,
  format: ReportFormat,
  artifacts: { html: string; markdown: string },
  executableLabel: string,
  token?: vscode.CancellationToken,
): Promise<void> {
  if (format === "html") {
    await fs.writeFile(path.join(folder, "REBRIEF.html"), artifacts.html, "utf8");
    return;
  }
  if (format === "markdown") {
    await fs.writeFile(
      path.join(folder, "REBRIEF.md"),
      artifacts.markdown,
      "utf8",
    );
    return;
  }

  const executable = await ensureExecutable();
  const outputPath = path.join(folder, "REBRIEF.json");
  const settings = getSettings();
  const result = await runCommand(executable, {
    cwd: folder,
    args: [
      "scan",
      folder,
      "-y",
      "--plain",
      "-f",
      "json",
      "-c",
      settings.minConfidence,
      "-o",
      outputPath,
    ],
    token,
    onStderr: (chunk) => {
      outputChannel.append(chunk);
    },
  });
  if (result.exitCode !== 0) {
    throw new Error(
      `rebrief json export failed (${executableLabel}): ${result.stderr.trim() || "unknown error"}`,
    );
  }
}

let outputChannel: vscode.OutputChannel;

export function setScanOutputChannel(channel: vscode.OutputChannel): void {
  outputChannel = channel;
}

export async function runScan(
  context: vscode.ExtensionContext,
  folder: string,
  options?: {
    token?: vscode.CancellationToken;
    writeWorkspaceReport?: boolean;
    showProgress?: boolean;
  },
): Promise<ScanCache> {
  const settings = getSettings();
  const executable = await ensureExecutable();
  const key = cacheKeyForFolder(folder);
  const cacheBase = path.join(getCacheDir(context), key);
  const htmlPath = path.join(cacheBase, HTML_NAME);

  await fs.mkdir(cacheBase, { recursive: true });

  const run = async (token?: vscode.CancellationToken): Promise<ScanCache> => {
    outputChannel.clear();
    outputChannel.appendLine(
      `Scanning ${folder} via ${executable.label} ...`,
    );

    const result = await runCommand(executable, {
      cwd: folder,
      args: [
        "scan",
        folder,
        "-y",
        "--plain",
        "-f",
        "html",
        "-c",
        settings.minConfidence,
        "-o",
        htmlPath,
      ],
      token,
      onStderr: (chunk) => outputChannel.append(chunk),
    });

    if (result.exitCode !== 0) {
      throw new Error(
        result.stderr.trim() || `rebrief scan exited with code ${result.exitCode}`,
      );
    }

    const html = await fs.readFile(htmlPath, "utf8");
    const parsed = parseScanArtifacts(html, folder, settings.format);
    const cache: ScanCache = {
      folder,
      htmlPath,
      ...parsed,
    };

    await fs.writeFile(
      path.join(cacheBase, META_NAME),
      JSON.stringify(cache, null, 2),
      "utf8",
    );

    if (options?.writeWorkspaceReport !== false) {
      await writeWorkspaceReport(
        folder,
        settings.format,
        { html, markdown: parsed.markdown },
        executable.label,
        token,
      );
    }

    return cache;
  };

  if (options?.showProgress === false) {
    return run(options.token);
  }

  return vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: "Rebrief",
      cancellable: true,
    },
    async (progress, token) => {
      progress.report({ message: `Scanning ${path.basename(folder)}...` });
      return run(token);
    },
  );
}
