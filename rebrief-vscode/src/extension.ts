import * as path from "path";
import * as vscode from "vscode";
import { resetExecutableCache } from "./cli";
import { AUTO_SCAN_FILENAMES, getSettings } from "./config";
import {
  getCacheForFolder,
  runScan,
  setScanOutputChannel,
  type ScanCache,
} from "./scan";
import { openDashboardPanel, SidebarProvider } from "./webview";

let statusBarItem: vscode.StatusBarItem;
let sidebarProvider: SidebarProvider;
let outputChannel: vscode.OutputChannel;
let autoScanTimer: NodeJS.Timeout | undefined;
let latestCache: ScanCache | null = null;

function workspaceFolder(): string | undefined {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    return undefined;
  }
  return folders[0].uri.fsPath;
}

function resolveTargetFolder(uri?: vscode.Uri): string | undefined {
  if (uri) {
    return uri.fsPath;
  }
  return workspaceFolder();
}

async function refreshSidebar(cache: ScanCache | null): Promise<void> {
  latestCache = cache;
  sidebarProvider.setCache(cache);
}

async function ensureCache(
  context: vscode.ExtensionContext,
  folder: string,
): Promise<ScanCache | null> {
  if (latestCache && latestCache.folder === folder) {
    return latestCache;
  }
  const cached = await getCacheForFolder(context, folder);
  if (cached) {
    await refreshSidebar(cached);
  }
  return cached;
}

async function performScan(
  context: vscode.ExtensionContext,
  folder: string,
  options?: { showProgress?: boolean; writeWorkspaceReport?: boolean },
): Promise<ScanCache> {
  const cache = await runScan(context, folder, options);
  await refreshSidebar(cache);
  return cache;
}

async function scanWorkspace(
  context: vscode.ExtensionContext,
  uri?: vscode.Uri,
): Promise<ScanCache | undefined> {
  const folder = resolveTargetFolder(uri);
  if (!folder) {
    void vscode.window.showWarningMessage(
      "Open a workspace folder before running Rebrief.",
    );
    return undefined;
  }

  try {
    const cache = await performScan(context, folder);
    void vscode.window.showInformationMessage(
      `Rebrief scan complete for ${cache.summary.repoName}.`,
    );
    return cache;
  } catch (error) {
    if (error instanceof vscode.CancellationError) {
      return undefined;
    }
    const message =
      error instanceof Error ? error.message : "Rebrief scan failed.";
    void vscode.window.showErrorMessage(message);
    return undefined;
  }
}

async function copyBriefing(
  context: vscode.ExtensionContext,
  folder?: string,
): Promise<void> {
  const target = folder ?? workspaceFolder();
  if (!target) {
    void vscode.window.showWarningMessage("No workspace folder is open.");
    return;
  }

  let cache = await ensureCache(context, target);
  if (!cache) {
    const scanned = await scanWorkspace(context, vscode.Uri.file(target));
    if (!scanned) {
      return;
    }
    cache = scanned;
  }

  await vscode.env.clipboard.writeText(cache.prompt);
  void vscode.window.showInformationMessage(
    "Rebrief AI prompt copied to clipboard.",
  );
}

async function openDashboard(
  context: vscode.ExtensionContext,
  folder?: string,
): Promise<void> {
  const target = folder ?? workspaceFolder();
  if (!target) {
    void vscode.window.showWarningMessage("No workspace folder is open.");
    return;
  }

  let cache = await ensureCache(context, target);
  if (!cache) {
    const scanned = await scanWorkspace(context, vscode.Uri.file(target));
    if (!scanned) {
      return;
    }
    cache = scanned;
  }

  openDashboardPanel(context, cache);
}

function scheduleAutoScan(
  context: vscode.ExtensionContext,
  folder: string,
): void {
  if (autoScanTimer) {
    clearTimeout(autoScanTimer);
  }
  autoScanTimer = setTimeout(() => {
    void performScan(context, folder, {
      showProgress: false,
      writeWorkspaceReport: true,
    }).catch((error) => {
      if (error instanceof vscode.CancellationError) {
        return;
      }
      const message =
        error instanceof Error ? error.message : "Auto-scan failed.";
      outputChannel.appendLine(message);
    });
  }, 1500);
}

export function activate(context: vscode.ExtensionContext): void {
  outputChannel = vscode.window.createOutputChannel("Rebrief");
  setScanOutputChannel(outputChannel);
  context.subscriptions.push(outputChannel);

  statusBarItem = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Left,
    100,
  );
  statusBarItem.command = "rebrief.scanWorkspace";
  statusBarItem.text = "Rebrief";
  statusBarItem.tooltip = "Scan workspace with Rebrief";
  statusBarItem.show();
  context.subscriptions.push(statusBarItem);

  sidebarProvider = new SidebarProvider(
    context,
    async () => {
      const folder = workspaceFolder();
      if (!folder) {
        void vscode.window.showWarningMessage("No workspace folder is open.");
        return;
      }
      await scanWorkspace(context, vscode.Uri.file(folder));
    },
    async () => {
      await openDashboard(context);
    },
    async () => {
      await copyBriefing(context);
    },
  );

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(
      SidebarProvider.viewType,
      sidebarProvider,
    ),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("rebrief.scanWorkspace", async () => {
      await scanWorkspace(context);
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand(
      "rebrief.scanFolder",
      async (uri: vscode.Uri) => {
        await scanWorkspace(context, uri);
      },
    ),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("rebrief.copyBriefing", async () => {
      await copyBriefing(context);
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("rebrief.openDashboard", async () => {
      await openDashboard(context);
    }),
  );

  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration("rebrief.executablePath")) {
        resetExecutableCache();
      }
    }),
  );

  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument((document) => {
      const settings = getSettings();
      if (!settings.autoScanOnSave) {
        return;
      }
      const folder = workspaceFolder();
      if (!folder) {
        return;
      }
      const fileName = path.basename(document.uri.fsPath);
      if (!AUTO_SCAN_FILENAMES.has(fileName)) {
        return;
      }
      if (!document.uri.fsPath.startsWith(folder)) {
        return;
      }
      scheduleAutoScan(context, folder);
    }),
  );

  const folder = workspaceFolder();
  if (folder) {
    void ensureCache(context, folder);
  }
}

export function deactivate(): void {
  if (autoScanTimer) {
    clearTimeout(autoScanTimer);
  }
}
