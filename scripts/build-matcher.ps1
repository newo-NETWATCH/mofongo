<#
Builds the folder that infra/modules/matcher zips: build/matcher

  - backend/matcher/*.py (tests are not copied)

The matcher has no extra dependencies: boto3 comes with the python3.13 Lambda runtime.
Run from anywhere:  ./scripts/build-matcher.ps1
#>
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $root 'build/matcher'

# Start clean so a deleted file cannot linger in the zip.
if (Test-Path $out) { Remove-Item -Recurse -Force $out }
New-Item -ItemType Directory -Force $out | Out-Null

Copy-Item -Path (Join-Path $root 'backend/matcher/*.py') -Destination $out

Write-Host "Built $out"
