import * as crypto from "crypto";
import * as vscode from "vscode";
import type { ScanCache } from "./scan";

const THEME_OVERRIDE = `
<style id="rebrief-vscode-theme">
:root {
  --bg: var(--vscode-editor-background);
  --surface: var(--vscode-sideBar-background);
  --border: var(--vscode-panel-border);
  --text: var(--vscode-editor-foreground);
  --muted: var(--vscode-descriptionForeground);
}
body { background: var(--bg); color: var(--text); }
</style>
`;

const BRIDGE_SCRIPT = (nonce: string) => `
<script nonce="${nonce}">
(function () {
  const vscode = acquireVsCodeApi();
  function bindCopyButton(id, messageType) {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.addEventListener("click", () => {
      vscode.postMessage({ type: messageType });
    });
  }
  bindCopyButton("copy-prompt-btn", "copyPrompt");
  bindCopyButton("copy-md-btn", "copyMarkdown");
  window.addEventListener("DOMContentLoaded", () => {
    bindCopyButton("copy-prompt-btn", "copyPrompt");
    bindCopyButton("copy-md-btn", "copyMarkdown");
  });
})();
</script>
`;

export function prepareDashboardHtml(
  html: string,
  webview: vscode.Webview,
): string {
  const nonce = crypto.randomBytes(16).toString("base64");
  const csp = [
    "default-src 'none'",
    `style-src ${webview.cspSource} 'unsafe-inline'`,
    `script-src 'nonce-${nonce}'`,
    `img-src ${webview.cspSource} data:`,
    `font-src ${webview.cspSource}`,
  ].join("; ");

  let prepared = html;
  if (!prepared.includes("<head>")) {
    prepared = prepared.replace("<html", "<html><head></head");
  }
  prepared = prepared.replace(
    "<head>",
    `<head><meta http-equiv="Content-Security-Policy" content="${csp}">`,
  );
  prepared = prepared.replace(
    "</head>",
    `${THEME_OVERRIDE}</head>`,
  );
  prepared = prepared.replace(
    /<script>([\s\S]*?)<\/script>/,
    `<script nonce="${nonce}">$1</script>`,
  );
  prepared = prepared.replace(
    "</body>",
    `${BRIDGE_SCRIPT(nonce)}</body>`,
  );
  return prepared;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function sidebarHtml(cache: ScanCache | null): string {
  const hasScan = cache !== null;
  const repo = hasScan ? escapeHtml(cache.summary.repoName) : "No scan yet";
  const folder = hasScan ? escapeHtml(cache.summary.folder) : "";
  const scannedAt = hasScan
    ? escapeHtml(new Date(cache.summary.scannedAt).toLocaleString())
    : "";
  const critical = hasScan ? cache.summary.critical : 0;
  const warning = hasScan ? cache.summary.warning : 0;
  const info = hasScan ? cache.summary.info : 0;

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root {
      --bg: var(--vscode-editor-background);
      --surface: var(--vscode-sideBar-background);
      --border: var(--vscode-panel-border);
      --text: var(--vscode-editor-foreground);
      --muted: var(--vscode-descriptionForeground);
      --accent: var(--vscode-button-background);
      --accent-fg: var(--vscode-button-foreground);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 16px;
      background: var(--bg);
      color: var(--text);
      font-family: var(--vscode-font-family);
      font-size: var(--vscode-font-size);
      line-height: 1.45;
    }
    h1 {
      margin: 0 0 4px;
      font-size: 16px;
      font-weight: 600;
    }
    .muted { color: var(--muted); font-size: 12px; word-break: break-all; }
    .stats {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
      margin: 16px 0;
    }
    .stat {
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 10px;
      text-align: center;
      background: var(--surface);
    }
    .stat strong { display: block; font-size: 18px; }
    .stat span { color: var(--muted); font-size: 11px; text-transform: uppercase; }
    .actions { display: grid; gap: 8px; margin-top: 16px; }
    button {
      appearance: none;
      border: 1px solid var(--border);
      background: var(--surface);
      color: var(--text);
      border-radius: 6px;
      padding: 8px 12px;
      font: inherit;
      cursor: pointer;
      text-align: left;
    }
    button.primary {
      background: var(--accent);
      color: var(--accent-fg);
      border-color: transparent;
    }
    button:disabled { opacity: 0.5; cursor: default; }
    .empty {
      margin-top: 12px;
      padding: 12px;
      border: 1px dashed var(--border);
      border-radius: 6px;
      color: var(--muted);
      font-size: 12px;
    }
  </style>
</head>
<body>
  <h1>${repo}</h1>
  ${folder ? `<div class="muted">${folder}</div>` : ""}
  ${scannedAt ? `<div class="muted">Last scan: ${scannedAt}</div>` : ""}
  ${
    hasScan
      ? `<div class="stats">
          <div class="stat"><strong>${critical}</strong><span>Critical</span></div>
          <div class="stat"><strong>${warning}</strong><span>Warning</span></div>
          <div class="stat"><strong>${info}</strong><span>Info</span></div>
        </div>`
      : `<div class="empty">Run a scan to generate an interactive briefing for this workspace.</div>`
  }
  <div class="actions">
    <button class="primary" data-action="scan">Scan workspace</button>
    <button data-action="dashboard" ${hasScan ? "" : "disabled"}>Open dashboard</button>
    <button data-action="copy" ${hasScan ? "" : "disabled"}>Copy AI prompt</button>
  </div>
  <script>
    const vscode = acquireVsCodeApi();
    document.querySelectorAll("[data-action]").forEach((btn) => {
      btn.addEventListener("click", () => {
        vscode.postMessage({ type: btn.getAttribute("data-action") });
      });
    });
  </script>
</body>
</html>`;
}

export class SidebarProvider implements vscode.WebviewViewProvider {
  public static readonly viewType = "rebrief.sidebar";

  private view?: vscode.WebviewView;
  private cache: ScanCache | null = null;

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly onScan: () => Promise<void>,
    private readonly onOpenDashboard: () => Promise<void>,
    private readonly onCopyPrompt: () => Promise<void>,
  ) {}

  public setCache(cache: ScanCache | null): void {
    this.cache = cache;
    this.refresh();
  }

  public refresh(): void {
    if (!this.view) {
      return;
    }
    this.view.webview.html = sidebarHtml(this.cache);
  }

  resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken,
  ): void {
    this.view = webviewView;
    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this.context.extensionUri],
    };

    webviewView.webview.onDidReceiveMessage(async (message: { type: string }) => {
      if (message.type === "scan") {
        await this.onScan();
      } else if (message.type === "dashboard") {
        await this.onOpenDashboard();
      } else if (message.type === "copy") {
        await this.onCopyPrompt();
      }
    });

    this.refresh();
  }
}

let dashboardPanel: vscode.WebviewPanel | undefined;

export function openDashboardPanel(
  context: vscode.ExtensionContext,
  cache: ScanCache,
): void {
  if (dashboardPanel) {
    dashboardPanel.reveal(vscode.ViewColumn.One);
    dashboardPanel.webview.html = prepareDashboardHtml(
      cache.html,
      dashboardPanel.webview,
    );
    wireDashboardClipboard(dashboardPanel, cache);
    return;
  }

  dashboardPanel = vscode.window.createWebviewPanel(
    "rebriefDashboard",
    `Rebrief — ${cache.summary.repoName}`,
    vscode.ViewColumn.One,
    {
      enableScripts: true,
      retainContextWhenHidden: true,
      localResourceRoots: [context.extensionUri],
    },
  );

  dashboardPanel.webview.html = prepareDashboardHtml(
    cache.html,
    dashboardPanel.webview,
  );
  wireDashboardClipboard(dashboardPanel, cache);

  dashboardPanel.onDidDispose(() => {
    dashboardPanel = undefined;
  });
}

function wireDashboardClipboard(
  panel: vscode.WebviewPanel,
  cache: ScanCache,
): void {
  panel.webview.onDidReceiveMessage(async (message: { type: string }) => {
    if (message.type === "copyPrompt") {
      await vscode.env.clipboard.writeText(cache.prompt);
      void vscode.window.showInformationMessage("Rebrief AI prompt copied.");
    } else if (message.type === "copyMarkdown") {
      await vscode.env.clipboard.writeText(cache.markdown);
      void vscode.window.showInformationMessage("REBRIEF markdown copied.");
    }
  });
}
