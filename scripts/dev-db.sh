#!/usr/bin/env bash
# Local development PostgreSQL using the binaries bundled with the `pgserver` pip package.
# Usage: scripts/dev-db.sh start|stop|status
# Production and Docker deployments use a normal PostgreSQL server instead (see docs/DEPLOYMENT.md).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PGBIN="$(ls -d "$ROOT"/backend/.venv/lib/python3.*/site-packages/pgserver/pginstall/bin | head -1)"
PGDATA="$ROOT/backend/var/pgdata"
PGPORT="${TANDEM_DEV_PG_PORT:-5433}"
LOG="$ROOT/backend/var/postgres.log"

case "${1:-start}" in
  start)
    mkdir -p "$ROOT/backend/var"
    if [ ! -f "$PGDATA/PG_VERSION" ]; then
      "$PGBIN/initdb" -D "$PGDATA" -U tandem --auth=trust -E UTF8 --locale=C >/dev/null
    fi
    if "$PGBIN/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1; then
      echo "PostgreSQL already running on port $PGPORT"
    else
      "$PGBIN/pg_ctl" -D "$PGDATA" -l "$LOG" -o "-p $PGPORT -k /tmp -c listen_addresses=127.0.0.1" -w start >/dev/null
      echo "PostgreSQL started on port $PGPORT"
    fi
    for db in tandem tandem_test; do
      "$PGBIN/psql" -h 127.0.0.1 -p "$PGPORT" -U tandem -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1 \
        || "$PGBIN/createdb" -h 127.0.0.1 -p "$PGPORT" -U tandem "$db"
    done
    echo "DATABASE_URL=postgresql+psycopg://tandem@127.0.0.1:$PGPORT/tandem"
    ;;
  stop)
    "$PGBIN/pg_ctl" -D "$PGDATA" -m fast stop ;;
  status)
    "$PGBIN/pg_ctl" -D "$PGDATA" status ;;
  *) echo "usage: $0 start|stop|status"; exit 1 ;;
esac
