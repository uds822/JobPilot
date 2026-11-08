#!/usr/bin/env bash
set -e

echo "[JobPilot Entrypoint] Checking database connectivity..."

# Wait for database connection before running migrations
python - <<'EOF'
import sys
import time
import os
from sqlalchemy import create_engine, text

db_url = os.environ.get("DATABASE_URL", "")
# Convert asyncpg/psycopg URL to synchronous psycopg for lightweight check if needed
sync_url = db_url.replace("+asyncpg", "").replace("+psycopg", "")
retries = 30

for i in range(retries):
    try:
        engine = create_engine(sync_url, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("[JobPilot Entrypoint] Database is ready!")
        sys.exit(0)
    except Exception as exc:
        print(f"[JobPilot Entrypoint] Waiting for DB... ({i+1}/{retries}) - {exc}")
        time.sleep(1)

print("[JobPilot Entrypoint] ERROR: Timed out waiting for database.", file=sys.stderr)
sys.exit(1)
EOF

echo "[JobPilot Entrypoint] Running database migrations (alembic upgrade head)..."
alembic upgrade head

echo "[JobPilot Entrypoint] Database ready and schema up to date. Starting command: $@"
exec "$@"

