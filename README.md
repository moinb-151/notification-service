# Notification Service

A Django-based asynchronous notification service for managing user notification preferences and delivering notifications across multiple channels.

## Stack

- Python 3.13
- Django 6.0
- Django REST Framework
- Simple JWT (cookie-based authentication)
- PostgreSQL 18
- Valkey 9.1.2
- RabbitMQ 3.13
- Uvicorn
- Docker & Docker Compose
- uv

## Features

- User registration and authentication
- JWT authentication via HTTP-only cookies
- Token refresh and logout with token blacklisting
- Per-user notification preferences
- Notification template management
- Multi-channel notification support
- Notification status and failure tracking
- Scheduled/deferred notifications
- Health check endpoint
- Containerized development environment
- Asynchronous notification processing with Celery (application configuration present; worker deployment is part of the next infrastructure stage)

## Architecture

The service is designed around asynchronous notification processing.

Current Docker infrastructure:

```text
                    ┌──────────────────┐
                    │ Django / Uvicorn │
                    │      :8000       │
                    └───────┬──────────┘
                            │
             ┌──────────────┼──────────────┐
             ▼              ▼              ▼
        PostgreSQL        Valkey       RabbitMQ
          :5432           :6379          :5672
        persistent       cache          broker
```

PostgreSQL is the primary persistent data store.

Valkey is used for application caching and the Celery result backend.

RabbitMQ is used as the Celery message broker.

The RabbitMQ management UI is exposed to the host on port `15672` for local development.

## Local Development

### Prerequisites

- Python 3.13
- uv
- PostgreSQL
- Valkey/Redis-compatible server
- RabbitMQ

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

- Django/Uvicorn
- PostgreSQL 18
- Valkey 9.1.2
- RabbitMQ 3.13 with the management plugin

The Django image uses a multi-stage build with `uv` to install dependencies.

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
CELERY_BROKER_URL=amqp://notification_user:notification_password@rabbitmq:5672/notification_vhost
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

RabbitMQ persistence will be configured according to the durability requirements of the asynchronous processing infrastructure as the Celery queue topology is finalized.

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

### Service Health

PostgreSQL, Valkey, and RabbitMQ have Docker healthchecks.

The web service exposes an application-level health endpoint.

## RabbitMQ

RabbitMQ is configured with:

- User: `notification_user`
- Virtual host: `notification_vhost`
- AMQP port: `5672`
- Management UI port: `15672`

Containers communicate with RabbitMQ through:

```text
rabbitmq:5672
```

The AMQP port does not need to be published to the host because Docker Compose provides service-to-service networking.

The management UI is available locally at:

```text
http://localhost:15672
```

### Dead-Letter Queue and Parking Queue

The RabbitMQ dead-letter queue and parking queue are intended for messages that cannot be processed normally. Create them in the `notification_vhost` virtual host using the RabbitMQ Management UI.

Open `http://localhost:15672`, sign in, and select **Virtual Hosts → `notification_vhost`** (or select that virtual host from the UI's virtual-host selector before creating resources).

#### 1. Create the dead-letter exchange

Under **Exchanges → Add a new exchange**, create:

| Setting | Value |
|---|---|
| Name | `notifications.dlx` |
| Type | `direct` |
| Durable | Enabled |
| Auto-delete | Disabled |
| Internal | Disabled |

Click **Add exchange**.

#### 2. Create the dead-letter queue

Under **Queues and Streams → Add a new queue**, create:

| Setting | Value |
|---|---|
| Type | Classic queue |
| Name | `notification.dlq` |
| Durable | Enabled |
| Auto-delete | Disabled |

Click **Add queue**.

Open `notification.dlq`, find **Bindings**, and add a binding from `notifications.dlx` with routing key `notification.dlq`.

#### 3. Create the parking queue

Create another durable classic queue:

| Setting | Value |
|---|---|
| Name | `notification.parking` |
| Durable | Enabled |
| Auto-delete | Disabled |

Open `notification.parking`, then add a binding from `notifications.dlx` with routing key `notification.parking`.

The parking queue is a holding area for messages that have been inspected and deliberately moved aside for later investigation or manual handling. It is not automatically populated just because the DLQ exists.

#### 4. Route messages from application queues to the DLQ

For each source/work queue that should dead-letter failed messages, configure these queue arguments when the queue is declared:

| Argument | Value |
|---|---|
| `x-dead-letter-exchange` | `notifications.dlx` |
| `x-dead-letter-routing-key` | `notification.dlq` |

The source queue must be declared with these arguments for RabbitMQ to route dead-lettered messages to `notification.dlq`. Creating the exchange and destination queues alone does not enable dead-lettering.

If Celery or application configuration declares the source queues, configure the arguments in that declaration and recreate/redeclare the queue as appropriate. RabbitMQ does not allow a queue to be redeclared with different arguments while the existing queue remains; back up any messages and plan queue recreation carefully.

#### 5. Move a message to the parking queue

After investigating a message in `notification.dlq`, an operator can deliberately republish it through `notifications.dlx` using routing key `notification.parking`, then acknowledge/remove the original DLQ message. Do not remove the original before confirming the republished message is present in the parking queue.

Use the Management UI's **Get messages** action only for controlled troubleshooting. Fetching with acknowledgement can remove a message; choose the acknowledgement mode carefully.

#### 6. Verify the topology

In the `notification_vhost`, verify:

- Exchange `notifications.dlx` exists and is durable.
- Queue `notification.dlq` is durable and bound with routing key `notification.dlq`.
- Queue `notification.parking` is durable and bound with routing key `notification.parking`.
- Each source queue that should dead-letter has the `x-dead-letter-exchange` and `x-dead-letter-routing-key` arguments.
- A test message dead-lettered from a configured source queue appears in `notification.dlq`.

**Important:** The DLQ and parking queue are holding queues, not ordinary Celery worker queues. Do not attach the normal notification workers to them. A dead-letter queue also does not automatically mean Celery's task retry or failure handling will send every failed task there; confirm the task acknowledgement/retry behavior and queue declarations used by this project.

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

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health/` | Application health check |

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/register/` | Register a new user |
| `POST` | `/api/auth/login/` | Login and receive tokens as cookies |
| `POST` | `/api/auth/refresh/` | Refresh access token |
| `POST` | `/api/auth/logout/` | Logout and clear cookies |

### Notifications

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/notifications/preferences/` | Get user notification preferences |
| `PATCH` | `/api/notifications/preferences/` | Update notification preferences |

## Environment Variables

Application configuration is loaded through environment variables.

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | Enable/disable Django debug mode |
| `ALLOWED_HOSTS` | Comma-separated list of allowed hosts |
| `DB_NAME` | PostgreSQL database name |
| `DB_USER` | PostgreSQL database user |
| `DB_PASSWORD` | PostgreSQL database password |
| `DB_HOST` | PostgreSQL hostname |
| `DB_PORT` | PostgreSQL port |
| `REDIS_URL` | Valkey/Redis connection URL |
| `CELERY_BROKER_URL` | Celery message broker URL |
| `CELERY_RESULT_BACKEND` | Celery result backend URL |

Environment-specific values are supplied through separate environment files while keeping the application variable names consistent.

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

- Auth tokens are stored as HTTP-only cookies rather than `localStorage`.
- Refresh tokens are blacklisted on logout and rotation.
- Notification preferences are automatically seeded for supported channels when a user is created.

## Current Docker Services

| Service | Image | Port | Purpose |
|---|---|---:|---|
| `web` | Local application image | `8000` | Django + Uvicorn |
| `postgres` | PostgreSQL 18 | `5432` (internal) | Primary database |
| `valkey` | Valkey 9.1.2 | `6379` (internal) | Cache and Celery result backend |
| `rabbitmq` | RabbitMQ 3.13 Management | `5672` (internal), `15672` (host) | Celery message broker + management UI |

## Roadmap

Planned infrastructure and functionality include:

- Celery worker containers
- Celery Beat container
- Priority notification queues
- RabbitMQ topic exchanges and bindings
- Automated RabbitMQ topology declarations for dead-letter and parking queues
- End-to-end verification of retry, dead-letter, and failure handling
- Nginx reverse proxy
- WebSocket/SSE-based in-app notifications
- Production deployment configuration
- Deeper application readiness checks