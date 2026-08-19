import * as vscode from "vscode";

export type ReportFormat = "markdown" | "json" | "html";
export type MinConfidence = "high" | "medium" | "low";

export interface RebriefSettings {
  executablePath: string;
  format: ReportFormat;
  minConfidence: MinConfidence;
  autoScanOnSave: boolean;
}

export const AUTO_SCAN_FILENAMES = new Set([
  "package.json",
  "pyproject.toml",
  "poetry.lock",
  "requirements.txt",
  "go.mod",
  "Cargo.toml",
  "pom.xml",
  "build.gradle",
  "build.gradle.kts",
  "composer.json",
  "Gemfile",
  "rebrief.toml",
  ".rebrief.toml",
]);

export function getSettings(): RebriefSettings {
  const config = vscode.workspace.getConfiguration("rebrief");
  return {
    executablePath: config.get<string>("executablePath", ""),
    format: config.get<ReportFormat>("format", "markdown"),
    minConfidence: config.get<MinConfidence>("minConfidence", "medium"),
    autoScanOnSave: config.get<boolean>("autoScanOnSave", false),
  };
}
