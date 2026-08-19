import { execFile, spawn } from "child_process";
import * as fs from "fs";
import * as path from "path";
import { promisify } from "util";
import * as vscode from "vscode";

const execFileAsync = promisify(execFile);

export interface ResolvedExecutable {
  command: string;
  args: string[];
  label: string;
}

export interface RunOptions {
  cwd: string;
  args: string[];
  token?: vscode.CancellationToken;
  onStderr?: (chunk: string) => void;
}

export interface RunResult {
  exitCode: number;
  stderr: string;
}

let cachedExecutable: ResolvedExecutable | null | undefined;

export function resetExecutableCache(): void {
  cachedExecutable = undefined;
}

async function commandExists(command: string): Promise<boolean> {
  const checker = process.platform === "win32" ? "where" : "command";
  const checkerArgs =
    process.platform === "win32" ? [command] : ["-v", command];
  try {
    const { stdout } = await execFileAsync(checker, checkerArgs, {
      windowsHide: true,
    });
    return stdout.trim().length > 0;
  } catch {
    return false;
  }
}

async function probeModuleInvocation(
  command: string,
  moduleArgs: string[],
): Promise<boolean> {
  return new Promise((resolve) => {
    const child = spawn(command, moduleArgs, {
      cwd: process.cwd(),
      windowsHide: true,
      stdio: ["ignore", "ignore", "pipe"],
    });
    let stderr = "";
    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf8");
    });
    child.on("error", () => resolve(false));
    child.on("close", (code) => {
      if (code === 0) {
        resolve(true);
        return;
      }
      resolve(
        !stderr.includes("No module named") &&
          !stderr.includes("can't find") &&
          !stderr.includes("not found"),
      );
    });
  });
}

async function resolveFromSetting(
  executablePath: string,
): Promise<ResolvedExecutable | null> {
  const expanded = executablePath.trim();
  if (!expanded) {
    return null;
  }
  const resolved = path.isAbsolute(expanded)
    ? expanded
    : path.resolve(expanded);
  if (!fs.existsSync(resolved)) {
    return null;
  }
  return {
    command: resolved,
    args: [],
    label: resolved,
  };
}

async function resolveFromPath(): Promise<ResolvedExecutable | null> {
  if (await commandExists("rebrief")) {
    return { command: "rebrief", args: [], label: "rebrief" };
  }
  return null;
}

async function resolveFromPython(): Promise<ResolvedExecutable | null> {
  const candidates: Array<{ command: string; prefix: string[] }> = [
    { command: "python", prefix: ["-m", "rebrief"] },
    { command: "python3", prefix: ["-m", "rebrief"] },
    { command: "py", prefix: ["-3", "-m", "rebrief"] },
  ];
  for (const candidate of candidates) {
    if (!(await commandExists(candidate.command))) {
      continue;
    }
    const ok = await probeModuleInvocation(candidate.command, [
      ...candidate.prefix,
      "--version",
    ]);
    if (ok) {
      return {
        command: candidate.command,
        args: candidate.prefix,
        label: `${candidate.command} ${candidate.prefix.join(" ")}`,
      };
    }
  }
  return null;
}

export async function resolveExecutable(
  force = false,
): Promise<ResolvedExecutable | null> {
  if (!force && cachedExecutable !== undefined) {
    return cachedExecutable;
  }

  const settings = vscode.workspace
    .getConfiguration("rebrief")
    .get<string>("executablePath", "");

  const fromSetting = await resolveFromSetting(settings);
  if (fromSetting) {
    cachedExecutable = fromSetting;
    return fromSetting;
  }

  const fromPath = await resolveFromPath();
  if (fromPath) {
    cachedExecutable = fromPath;
    return fromPath;
  }

  const fromPython = await resolveFromPython();
  cachedExecutable = fromPython;
  return fromPython;
}

export async function ensureExecutable(): Promise<ResolvedExecutable> {
  const resolved = await resolveExecutable();
  if (resolved) {
    return resolved;
  }

  const choice = await vscode.window.showErrorMessage(
    "Rebrief CLI was not found. Install it with pipx or set rebrief.executablePath.",
    "Install with pipx",
    "Open Settings",
  );

  if (choice === "Install with pipx") {
    const terminal = vscode.window.createTerminal("Rebrief Install");
    terminal.show();
    terminal.sendText("pipx install rebrief");
  } else if (choice === "Open Settings") {
    await vscode.commands.executeCommand(
      "workbench.action.openSettings",
      "rebrief.executablePath",
    );
  }

  throw new Error("Rebrief CLI not found");
}

export function runCommand(
  executable: ResolvedExecutable,
  options: RunOptions,
): Promise<RunResult> {
  return new Promise((resolve, reject) => {
    const args = [...executable.args, ...options.args];
    const child = spawn(executable.command, args, {
      cwd: options.cwd,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stderr = "";

    child.stdout.on("data", () => {
      // stdout is reserved for report payloads when -o - is used; HTML scans write to file.
    });

    child.stderr.on("data", (chunk: Buffer) => {
      const text = chunk.toString("utf8");
      stderr += text;
      options.onStderr?.(text);
    });

    const onCancellation = () => {
      child.kill();
      reject(new vscode.CancellationError());
    };

    if (options.token?.isCancellationRequested) {
      onCancellation();
      return;
    }

    const cancellationListener = options.token?.onCancellationRequested(
      onCancellation,
    );

    child.on("error", (error) => {
      cancellationListener?.dispose();
      reject(error);
    });

    child.on("close", (code) => {
      cancellationListener?.dispose();
      resolve({
        exitCode: code ?? 1,
        stderr,
      });
    });
  });
}
