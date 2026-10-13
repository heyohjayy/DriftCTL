[CmdletBinding()]
param(
    [string]$VenvPath = (Join-Path $PSScriptRoot "..\.venv")
)

$venv = (Resolve-Path -LiteralPath $VenvPath -ErrorAction Stop).Path
$scriptsPath = Join-Path $venv "Scripts"
$python = Join-Path $scriptsPath "python.exe"
$launcher = Join-Path $scriptsPath "driftctl.exe"
$blockedLauncher = "$launcher.wdac-blocked"
$commandShim = Join-Path $scriptsPath "driftctl.cmd"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python was not found in the virtual environment: $python"
}

if (Test-Path -LiteralPath $launcher) {
    if (Test-Path -LiteralPath $blockedLauncher) {
        Remove-Item -LiteralPath $launcher -Force
    }
    else {
        Rename-Item -LiteralPath $launcher -NewName "driftctl.exe.wdac-blocked"
    }
}

@'
@echo off
"%~dp0python.exe" -c "from driftctl.cli import app; app(prog_name='driftctl')" %*
'@ | Set-Content -LiteralPath $commandShim -Encoding ascii

Write-Host "Enabled the Windows DriftCTL development command shim: $commandShim"
Write-Host "Activate the virtual environment normally, then run: driftctl scan"
