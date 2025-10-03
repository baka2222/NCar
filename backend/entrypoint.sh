#!/bin/sh
set -e

echo "=== Waiting for Postgres to be available ==="

RETRIES=12
until python - <<'PY'
import os, sys, time
try:
    import psycopg2
    conn = psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("DB_HOST", "db"),
        port=os.getenv("DB_PORT", "5432"),
        connect_timeout=5
    )
    conn.close()
except Exception:
    sys.exit(1)
sys.exit(0)
PY
do
  RETRIES=$((RETRIES-1))
  if [ $RETRIES -le 0 ]; then
    echo "Postgres not ready - exiting"
    exit 1
  fi
  echo "Postgres not ready, sleeping 2s..."
  sleep 2
done

echo "Apply migrations..."
python manage.py migrate --noinput

echo "Collect static files..."
python manage.py collectstatic --noinput

echo "Starting Gunicorn..."
exec gunicorn backend.wsgi:application --bind 0.0.0.0:8000 --workers 2
