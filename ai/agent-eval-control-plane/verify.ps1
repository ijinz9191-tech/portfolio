$ErrorActionPreference = 'Stop'
$env:PYTHONPATH = Join-Path $PSScriptRoot 'src'
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
$condaPython = Join-Path $env:USERPROFILE 'miniconda3\python.exe'
if (Test-Path -LiteralPath $condaPython) { $python = $condaPython }
if (-not $python) { throw 'Python 3.11+ is required.' }
& $python -m unittest discover -s (Join-Path $PSScriptRoot 'tests') -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $python -m agent_eval_control_plane.cli demo --db (Join-Path $PSScriptRoot 'artifacts\demo.sqlite')
exit $LASTEXITCODE
