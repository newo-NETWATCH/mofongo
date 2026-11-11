<#
Builds the folder that infra/modules/api_lambda zips: build/api

  - backend/api/*.py
  - jsonschema (and its dependencies), built for Linux with pip --platform
  - api/schemas/requests and api/schemas/shared, copied recursively to schemas/

boto3 is not bundled: the python3.13 Lambda runtime provides it.
Run from anywhere:  ./scripts/build-api.ps1   (add -Architecture arm64 if the module uses arm64)
#>
param(
    [ValidateSet('x86_64', 'arm64')]
    [string]$Architecture = 'x86_64'
)

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$out = Join-Path $root 'build/api'
$platform = if ($Architecture -eq 'arm64') { 'manylinux2014_aarch64' } else { 'manylinux2014_x86_64' }

# Start clean so a deleted file cannot linger in the zip.
if (Test-Path $out) { Remove-Item -Recurse -Force $out }
New-Item -ItemType Directory -Force $out | Out-Null

# Dependencies. The Linux wheels are required: jsonschema pulls in rpds-py, which has a native part.
python -m pip install `
    --requirement (Join-Path $root 'backend/api/requirements.txt') `
    --target $out `
    --platform $platform `
    --python-version 3.13 `
    --implementation cp `
    --only-binary=:all: `
    --upgrade
if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }

# Handler code (top level, so the handler is app.handler).
Copy-Item (Join-Path $root 'backend/api/*.py') $out

# Schemas, recursively, keeping requests/ and shared/. The Lambda reads schemas/requests/*.json.
$schemas = Join-Path $out 'schemas'
foreach ($folder in 'requests', 'shared') {
    Copy-Item (Join-Path $root "api/schemas/$folder") (Join-Path $schemas $folder) -Recurse
}

# Do not ship bytecode caches or pip's metadata caches.
Get-ChildItem $out -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force

Write-Host "Package folder ready: $out"
