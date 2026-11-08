$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\apps\web")
if (!(Test-Path .env.local)) { Copy-Item .env.local.example .env.local }
if (!(Test-Path node_modules)) { npm install }
npm run dev
