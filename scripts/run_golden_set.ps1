Param(
    [string]$PytestArgs = ""
)

if (-not (Get-Command pytest -ErrorAction SilentlyContinue)) {
    Write-Error "pytest is not available in PATH."
    exit 1
}

Invoke-Expression "pytest -m golden_set $PytestArgs"
