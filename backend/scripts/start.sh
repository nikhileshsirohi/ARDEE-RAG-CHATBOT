#!/bin/sh
# Container start command for the backend web service on Render.
# Runs database migrations, then launches the API on the port Render provides.
# Kept as a script because Render's dockerCommand is not run through a shell,
# so operators like "&&" cannot be used inline.
set -e

echo "Running database migrations..."
alembic upgrade head

# Optional one-time seeding of baseline admin/user accounts.
# Set SEED_ON_START=true for a single deploy, then set it back to false.
# Idempotent (existing emails are skipped); --force allows it under APP_ENV=production.
if [ "${SEED_ON_START:-false}" = "true" ]; then
    echo "Seeding baseline accounts..."
    python -m scripts.seed_staging --force || echo "Seeding skipped or failed (continuing)."
fi

echo "Starting API on port ${PORT:-8000}..."
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers "${WEB_CONCURRENCY:-2}" \
    --timeout-graceful-shutdown 30
