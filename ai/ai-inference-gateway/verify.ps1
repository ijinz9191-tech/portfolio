$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$build = Join-Path $root '.build'
New-Item -ItemType Directory -Force -Path $build | Out-Null
$sources = @(Get-ChildItem (Join-Path $root 'src'),(Join-Path $root 'tests') -Recurse -Filter '*.java' | Sort-Object FullName)
$manifest = @($sources | ForEach-Object { @{path=$_.FullName.Substring($root.Length+1).Replace('\','/'); sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLower()} })
$hashText = ($manifest | ForEach-Object { $_.path + ':' + $_.sha256 }) -join "`n"
$hash = [Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($hashText))).ToLower()
& javac --release 21 -d $build $sources.FullName
$compileExit = $LASTEXITCODE
$output = @()
$testExit = $null
if ($compileExit -eq 0) {
    $output = @(& java -ea -cp $build lab.GatewayTest 2>&1 | ForEach-Object { "$_" })
    $testExit = $LASTEXITCODE
}
$report = @{
    checked_at=[DateTime]::UtcNow.ToString('o'); source_hash=$hash; sources=$manifest
    command='javac --release 21 -d .build src/lab/Gateway.java tests/lab/GatewayTest.java; java -ea -cp .build lab.GatewayTest'
    compile_exit=$compileExit; test_exit=$testExit; status=$(if($compileExit -eq 0 -and $testExit -eq 0){'PASS'}else{'FAIL'})
    java_version=(@(& java -version 2>&1 | ForEach-Object { "$_" }) -join "`n")
    output=$output; scope='Local synthetic model, real HTTP and bounded failure tests; no external model or deployment'
}
New-Item -ItemType Directory -Force -Path (Join-Path $root 'artifacts') | Out-Null
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $root 'artifacts/verification.json') -Encoding utf8
$output | ForEach-Object { Write-Output $_ }
if($report.status -ne 'PASS'){exit 1}
