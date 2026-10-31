#!/usr/bin/env bash
# Push KEY=VALUE lines from a dotenv file to the linked Vercel project (Production).
# Values travel over stdin and are never printed. Inline "  # comments" are ignored.
#
# Safe to run on a copy of .env.example with a few keys filled in. Skipped automatically:
#   - empty values and values identical to the .env.example default
#   - values that point at localhost / 127.0.0.1
#   - core settings production already has (secrets, database, URLs, runtime mode),
#     unless you pass --include-core
#
#   scripts/vercel-env-push.sh --dry-run            # list the key names it would set
#   scripts/vercel-env-push.sh                      # reads .env.production.local (gitignored)
#   scripts/vercel-env-push.sh path/to/file.env
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
example="$root/.env.example"
dry=0; core=0; file=".env.production.local"
for arg in "$@"; do
  case "$arg" in
    --dry-run) dry=1 ;;
    --include-core) core=1 ;;
    -*) echo "Unknown option: $arg" >&2; exit 2 ;;
    *) file="$arg" ;;
  esac
done
PROTECTED=" SECRET_KEY ENCRYPTION_KEY CRON_SECRET DATABASE_URL DEMO_ACCOUNT_PASSWORD APP_ENV FRONTEND_URL BACKEND_URL JOB_RUNNER STORAGE_TYPE STORAGE_LOCAL_PATH SESSION_COOKIE_SECURE LOCATION_PROVIDER TRUSTED_PROXIES "

if [[ ! -f "$file" ]]; then
  echo "No $file yet. Put the keys you have in it (see docs/ENVIRONMENT.md), then run this again." >&2
  exit 1
fi

# KEY=VALUE -> value with inline comment, surrounding whitespace and quotes removed.
clean_value() {
  local v="${1#*=}"
  v="${v%%[[:space:]]#*}"
  v="$(printf '%s' "$v" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  v="${v%\"}"; v="${v#\"}"
  printf '%s' "$v"
}

count=0
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
  key="$(printf '%s' "${line%%=*}" | tr -d '[:space:]')"
  value="$(clean_value "$line")"
  [[ -z "$key" || -z "$value" ]] && continue

  if [[ $core -eq 0 && "$PROTECTED" == *" $key "* ]]; then
    echo "skip $key (core setting; use --include-core to overwrite production)"
    continue
  fi
  if [[ "$value" == *localhost* || "$value" == *127.0.0.1* ]]; then
    echo "skip $key (points at localhost)"
    continue
  fi
  default_line="$(grep -E "^${key}=" "$example" 2>/dev/null | head -1 || true)"
  if [[ -n "$default_line" && "$(clean_value "$default_line")" == "$value" ]]; then
    continue  # same as the shipped default; nothing to set
  fi

  if [[ $dry -eq 1 ]]; then
    echo "would set $key"
  else
    printf '%s' "$value" | vercel env add "$key" production --force --sensitive >/dev/null
    echo "set $key"
  fi
  count=$((count + 1))
done < "$file"

if [[ $dry -eq 1 ]]; then
  echo "$count variable(s) would be set. Run again without --dry-run to apply."
else
  echo "$count variable(s) updated. Redeploy so they take effect:  vercel deploy --prod"
fi
