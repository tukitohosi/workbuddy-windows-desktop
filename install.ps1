[CmdletBinding()]
param([string]$PythonExe, [switch]$Uninstall)
$ErrorActionPreference = 'Stop'
$candidates = @()
if ($PythonExe) {
    $candidates += @{ Exe = (Get-Item -LiteralPath $PythonExe).FullName; Prefix = @() }
} else {
    foreach ($name in @('python.exe', 'py.exe')) {
        foreach ($command in @(Get-Command $name -All -ErrorAction SilentlyContinue)) {
            if ($command.Source -like '*\Microsoft\WindowsApps\*') { continue }
            $prefix = if ($name -eq 'py.exe') { '-3' }
            $candidates += @{ Exe = $command.Source; Prefix = @($prefix | Where-Object { $_ }) }
        }
    }
}
foreach ($candidate in $candidates) {
    $exe = $candidate.Exe
    $prefix = $candidate.Prefix
    & $exe @prefix -I -B -c 'import sys; sys.exit(sys.version_info < (3,10))' 2>$null
    if ($LASTEXITCODE -ne 0) { continue }
    $action = if ($Uninstall) { 'uninstall' } else { 'install' }
    & $exe @prefix -I -B (Join-Path $PSScriptRoot 'setup.py') $action
    exit $LASTEXITCODE
}
throw 'Python 3.10+ is required. Pass -PythonExe with its full python.exe path.'
