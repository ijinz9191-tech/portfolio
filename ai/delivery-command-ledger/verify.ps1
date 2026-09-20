$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$build = Join-Path $root 'build\classes'
if (Test-Path $build) { Remove-Item -Recurse -Force $build }
New-Item -ItemType Directory -Force -Path $build | Out-Null
$sources = Get-ChildItem -LiteralPath (Join-Path $root 'src') -Recurse -Filter '*.java' | ForEach-Object FullName
javac --release 21 -d $build $sources
if ($LASTEXITCODE -ne 0) { throw 'javac failed' }
java -ea -cp $build lab.delivery.DeliveryCommandLedgerTest
if ($LASTEXITCODE -ne 0) { throw 'tests failed' }
