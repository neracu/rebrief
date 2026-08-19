# Rebrief VS Code Extension

Scan any workspace with the [rebrief](https://github.com/neracu/rebrief) CLI and explore the interactive `REBRIEF.html` dashboard inside VS Code or Cursor.

## Features

- Status bar `⚡ Rebrief` for one-click workspace scans
- Activity bar sidebar with risk summary and quick actions
- Explorer context menu: **Rebrief this folder**
- Interactive dashboard webview with VS Code theme integration
- **Copy AI Prompt** for Cursor, Claude Code, or Windsurf
- Auto-refresh on manifest/config saves (optional)

## Prerequisites

Install the CLI locally first:

```bash
pipx install rebrief
# or
pip install rebrief
```

Verify:

```bash
rebrief scan . -y
```

## Development

```bash
cd rebrief-vscode
npm install
npm run compile
```

Press **F5** in VS Code to launch an Extension Development Host.

## Commands

| Command | Description |
| --- | --- |
| `Rebrief: Scan Workspace` | Scan the first workspace folder |
| `Rebrief: Copy Briefing for Cursor / Claude` | Copy the AI-ready prompt |
| `Rebrief: Open Interactive Dashboard` | Open the HTML dashboard webview |
| `Rebrief this folder` | Scan a folder from the Explorer context menu |

## Settings

| Setting | Default | Description |
| --- | --- | --- |
| `rebrief.executablePath` | `""` | Custom path to the `rebrief` binary |
| `rebrief.format` | `markdown` | Workspace report format (`markdown`, `json`, `html`) |
| `rebrief.minConfidence` | `medium` | Risk confidence threshold (`high`, `medium`, `low`) |
| `rebrief.autoScanOnSave` | `false` | Re-scan when manifest/config files are saved |

## Packaging

```bash
npm run package
```

Produces `rebrief-0.3.0.vsix` for local install (`Extensions: Install from VSIX...`) or Marketplace upload via `vsce publish`.

## License

MIT
