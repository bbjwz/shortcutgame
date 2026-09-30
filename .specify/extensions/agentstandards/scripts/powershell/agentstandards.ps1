$ErrorActionPreference = "Stop"
$Runner = Join-Path $PSScriptRoot "../python/agentstandards.py"
& uv run --script $Runner @args
exit $LASTEXITCODE
