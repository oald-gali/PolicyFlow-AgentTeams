$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = Join-Path $projectRoot "src"
Set-Location $projectRoot
python -m uvicorn policyflow.api:app --host 127.0.0.1 --port 8787

