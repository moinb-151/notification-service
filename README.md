# Notification Service

A Django-based asynchronous notification service for managing user notification preferences and delivering notifications across multiple channels.

## Stack

* Python 3.13
* Django 6.0
* Django REST Framework
* Simple JWT (cookie-based authentication)
* PostgreSQL 18
* Valkey 9.1
* Uvicorn
* Docker & Docker Compose
* uv

## Features

* User registration and authentication
* JWT authentication via HTTP-only cookies
* Token refresh and logout with token blacklisting
* Per-user notification preferences
* Notification template management
* Multi-channel notification support
* Notification status and failure tracking
* Scheduled/deferred notifications
* Health check endpoint
* Containerized development environment

## Architecture

The service is designed around asynchronous notification processing.

Current infrastructure:

```text
                    ┌────────────────────┐
                    │      Client        │
                    └─────────┬──────────┘
                              │
                              ▼
                    ┌────────────────────┐
                    │ Django / Uvicorn   │
                    │      :8000         │
                    └──────┬───────┬─────┘
                           │       │
                  ┌────────┘       └────────┐
                  ▼                         ▼
        ┌──────────────────┐       ┌──────────────────┐
        │   PostgreSQL     │       │     Valkey       │
        │      :5432       │       │      :6379       │
        └──────────────────┘       └──────────────────┘
```

PostgreSQL is the primary persistent data store.

Valkey is used for application caching and will also serve as the Celery result backend.

Additional asynchronous infrastructure, including RabbitMQ and Celery workers, will be added as the project progresses.

## Local Development

### Prerequisites

* Python 3.13
* uv
* PostgreSQL
* Valkey/Redis-compatible server

Install dependencies:

```bash
uv sync
```

Activate the virtual environment:

```bash
source .venv/bin/activate
```

Copy and configure environment variables:

```bash
cp .env.example .env
```

Run migrations:

```bash
python manage.py migrate
```

Start the development server:

```bash
python manage.py runserver
```

## Docker Development

The project includes a Docker Compose environment containing:

* Django/Uvicorn
* PostgreSQL 18
* Valkey 9.1.2

The Django image uses a multi-stage build with `uv` to install production dependencies.

### Environment

Docker uses a separate environment file:

```text
.env.docker
```

The Docker environment uses Compose service names for internal communication:

```env
DB_HOST=postgres
REDIS_URL=redis://valkey:6379/1
CELERY_RESULT_BACKEND=redis://valkey:6379/0
```

`.env.docker` should not be committed to the repository.

### Start the Containers

Build the Django image and start all services:

```bash
sudo docker compose --env-file .env.docker up -d --build
```

Check service status:

```bash
sudo docker compose --env-file .env.docker ps
```

View logs:

```bash
sudo docker compose logs -f
```

Stop the environment:

```bash
sudo docker compose down
```

### Database Persistence

PostgreSQL uses a named Docker volume:

```text
postgres_data
```

This allows the PostgreSQL database to survive container recreation.

Valkey currently does not use a persistent volume because it is used for cache data and Celery result storage rather than as the source of truth for application data.

### Application Startup

The Django container uses `entrypoint.sh` to perform application initialization before starting Uvicorn.

The startup sequence is:

```text
PostgreSQL
    │
    ▼
PostgreSQL healthcheck
    │
    ▼
Django container
    │
    ▼
Run migrations
    │
    ▼
Start Uvicorn
```

Database migrations are automatically executed when the web container starts.

The entrypoint uses `exec` when starting Uvicorn so that Uvicorn becomes the container's main process and receives container signals correctly.

## Health Check

The application exposes:

```http
GET /health/
```

Example:

```bash
curl http://localhost:8000/health/
```

Response:

```json
{
  "status": "ok"
}
```

This endpoint currently provides a basic application liveness check.

## API Endpoints

### Health

| Method | Endpoint   | Description              |
| ------ | ---------- | ------------------------ |
| `GET`  | `/health/` | Application health check |

### Authentication

| Method | Endpoint              | Description                         |
| ------ | --------------------- | ----------------------------------- |
| `POST` | `/api/auth/register/` | Register a new user                 |
| `POST` | `/api/auth/login/`    | Login and receive tokens as cookies |
| `POST` | `/api/auth/refresh/`  | Refresh access token                |
| `POST` | `/api/auth/logout/`   | Logout and clear cookies            |

### Notifications

| Method  | Endpoint                          | Description                       |
| ------- | --------------------------------- | --------------------------------- |
| `GET`   | `/api/notifications/preferences/` | Get user notification preferences |
| `PATCH` | `/api/notifications/preferences/` | Update notification preferences   |

## Environment Variables

Application configuration is loaded through environment variables.

| Variable                | Description                           |
| ----------------------- | ------------------------------------- |
| `SECRET_KEY`            | Django secret key                     |
| `DEBUG`                 | Enable/disable Django debug mode      |
| `ALLOWED_HOSTS`         | Comma-separated list of allowed hosts |
| `DB_NAME`               | PostgreSQL database name              |
| `DB_USER`               | PostgreSQL database user              |
| `DB_PASSWORD`           | PostgreSQL database password          |
| `DB_HOST`               | PostgreSQL hostname                   |
| `DB_PORT`               | PostgreSQL port                       |
| `REDIS_URL`             | Valkey/Redis connection URL           |
| `CELERY_BROKER_URL`     | Celery message broker URL             |
| `CELERY_RESULT_BACKEND` | Celery result backend URL             |

Values differ between local development and Docker environments, while the application variable names remain the same.

## Project Structure

```text
notification-service/
├── config/
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── ...
├── apps/
│   ├── notifications/
│   ├── orders/
│   ├── products/
│   └── users/
├── keys/
│   ├── public.pem
│   └── private.pem
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh
├── pyproject.toml
├── uv.lock
├── .dockerignore
└── README.md
```

The `keys/` directory contains runtime cryptographic keys and is excluded from the Docker image and version control. The keys are mounted into the container at runtime.

## Authentication Notes

* Auth tokens are stored as HTTP-only cookies rather than `localStorage`.
* Refresh tokens are blacklisted on logout and rotation.
* Notification preferences are automatically seeded for supported channels when a user is created.

## Current Docker Services

| Service    | Image                   |   Port | Purpose                         |
| ---------- | ----------------------- | -----: | ------------------------------- |
| `web`      | Local application image | `8000` | Django + Uvicorn                |
| `postgres` | PostgreSQL 18           | `5432` | Primary database                |
| `valkey`   | Valkey 9.1.2            | `6379` | Cache and Celery result backend |

## Roadmap

Planned infrastructure and functionality include:

* RabbitMQ message broker
* Celery workers
* Celery Beat
* Priority notification queues
* Dead-letter queues
* Retry and failure handling
* Nginx reverse proxy
* WebSocket/SSE-based in-app notifications
* Production deployment configuration
* Deeper application readiness checks
