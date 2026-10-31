#!/usr/bin/env bash
# Push the non-empty KEY=VALUE lines of a dotenv file to the linked Vercel project (Production).
# Values travel over stdin and are never printed. Lines are plain KEY=VALUE: no inline comments.
#
#   scripts/vercel-env-push.sh                       # reads .env.production.local (gitignored)
#   scripts/vercel-env-push.sh path/to/file.env
set -euo pipefail

file="${1:-.env.production.local}"
if [[ ! -f "$file" ]]; then
  echo "No $file yet. Put the keys you have in it (see docs/ENVIRONMENT.md), then run this again." >&2
  exit 1
fi

count=0
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
  key="$(printf '%s' "${line%%=*}" | tr -d '[:space:]')"
  value="${line#*=}"
  value="${value%\"}"; value="${value#\"}"
  [[ -z "$key" || -z "$value" ]] && continue
  printf '%s' "$value" | vercel env add "$key" production --force --sensitive >/dev/null
  echo "set $key"
  count=$((count + 1))
done < "$file"

echo "$count variable(s) updated. Redeploy so they take effect:  vercel deploy --prod"
