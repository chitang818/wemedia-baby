# Wrapper (PowerShell) -> Python implementation
$ErrorActionPreference = "Stop"

Set-Location (Split-Path -Parent $PSScriptRoot)
Set-Location ..

if (Test-Path ".venv\\Scripts\\python.exe") {
    $pythonPath = ".venv\\Scripts\\python.exe"
} else {
    $pythonPath = "python"
}

$scriptPath = Join-Path $PSScriptRoot "factory_reset.py"
& $pythonPath $scriptPath $args

