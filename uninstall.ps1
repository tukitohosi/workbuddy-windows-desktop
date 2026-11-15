[CmdletBinding()]
param([string]$PythonExe)
& (Join-Path $PSScriptRoot 'install.ps1') @PSBoundParameters -Uninstall
exit $LASTEXITCODE
