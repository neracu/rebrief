# Package and publish the Rebrief VS Code extension.
# Marketplace publish requires VSCE_PAT (Azure DevOps PAT with Marketplace Manage scope).
# Local install works without a token.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ExtDir = Join-Path $Root "rebrief-vscode"

Push-Location $ExtDir
try {
    npm run package
    $vsix = Get-ChildItem -Filter "rebrief-*.vsix" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $vsix) {
        throw "No VSIX produced by npm run package"
    }

    if ($env:VSCE_PAT) {
        Write-Host "Publishing $($vsix.Name) to Visual Studio Marketplace..."
        npm run publish
        Write-Host "Published successfully."
    }
    else {
        Write-Host "VSCE_PAT not set — installing locally into Cursor instead."
        $cursorCmd = Get-Command cursor -ErrorAction SilentlyContinue
        if ($cursorCmd) {
            & cursor --install-extension $vsix.FullName --force
        }
        else {
            Write-Host "cursor CLI not found. Install manually: Extensions -> Install from VSIX -> $($vsix.FullName)"
        }
        Write-Host "Installed $($vsix.Name). Reload Cursor to see the logo."
        Write-Host "To publish to Marketplace: set VSCE_PAT, or add it as a GitHub secret and run the Publish workflow."
    }
}
finally {
    Pop-Location
}
