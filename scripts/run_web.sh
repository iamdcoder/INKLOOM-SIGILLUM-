#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/apps/web"
[ -f .env.local ] || cp .env.local.example .env.local
[ -d node_modules ] || npm install
npm run dev
