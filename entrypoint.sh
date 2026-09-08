#!/bin/sh

set -e

echo "Running database migrations..."
python manage.py migrate --noinput

echo "Starting Uvicorn..."
exec uvicorn config.asgi:application \
    --host 0.0.0.0 \
    --port 8000