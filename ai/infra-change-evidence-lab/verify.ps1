$ErrorActionPreference = "Stop"
$work = Join-Path $PSScriptRoot "test-work"
New-Item -ItemType Directory -Force -Path $work | Out-Null
$env:TEST_WORK_ROOT = (Resolve-Path $work).Path
$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
python -m unittest discover -s (Join-Path $PSScriptRoot "tests") -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
