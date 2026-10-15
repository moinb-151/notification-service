#!/bin/sh

set -e

case "$1" in
    web)
        echo "Running database migrations..."
        python manage.py migrate --noinput

        echo "Starting Uvicorn..."
        exec uvicorn config.asgi:application \
            --host 0.0.0.0 \
            --port 8000
        ;;

    rabbitmq-init)
        echo "Initializing RabbitMQ notification topology..."
        exec python manage.py setup_rabbitmq_topology
        ;;

    worker)
        echo "Starting Celery worker..."
        exec celery -A config worker --loglevel=info
        ;;

    beat)
        echo "Starting Celery Beat..."
        exec celery -A config beat --loglevel=info
        ;;

    dlq)
        echo "Starting notification DLQ consumer..."
        exec python manage.py consume_dlq
        ;;

    *)
        exec "$@"
        ;;
esac
