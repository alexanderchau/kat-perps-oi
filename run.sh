#!/bin/bash
set -eo pipefail

cd /Users/helm/Projects/kat-perps-oi || exit 1
export PATH="/Users/helm/.nvm/versions/node/v22.22.0/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

# Source API keys for wrangler (CLOUDFLARE_API_TOKEN) — launchd does not inherit shell env
[ -f /Users/helm/.api-keys ] && source /Users/helm/.api-keys

PYTHON="/Users/helm/.claude/venv/bin/python3"

# Scrape — if this fails, skip deploy entirely
$PYTHON scrape.py

# Only commit data.json (never __pycache__, logs, etc.)
if [ -d .git ]; then
    git add data.json
    CHANGES=$(git diff --cached --stat)
    if [ -n "$CHANGES" ]; then
        git commit -m "auto: $(date +%Y-%m-%d\ %H:%M)" >/dev/null
        git push origin main 2>&1 || echo "Push failed (ok if no remote yet)" >&2
    fi
fi

# Deploy to Cloudflare Pages (direct upload — git push does NOT trigger auto-deploy)
npx wrangler pages deploy . --project-name=kat-perps-oi --branch=main --commit-dirty=true 2>&1 \
    || echo "CF Pages deploy failed, will retry next run" >&2
