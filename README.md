# Notification Service

A Django-based microservice for sending notifications and managing user notification preferences.

## Stack

- Python 3.13
- Django 6.0
- Django REST Framework
- Simple JWT (cookie-based auth)
- PostgreSQL

## Features

- User registration and authentication (JWT via HTTP-only cookies)
- Token refresh and logout with blacklisting
- Per-user notification preferences seeded on registration
- Multi-channel notification support (email, SMS, etc.)

## Setup

```bash
git clone <repo-url>
cd notification-service
uv sync
source .venv/bin/activate
```

Copy and configure environment variables:

```bash
cp .env.example .env
```

Run migrations and start the server:

```bash
python manage.py migrate
python manage.py runserver
```

## Environment Variables

| Variable | Description |
|---|---|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | `True` or `False` |
| `DATABASE_URL` | PostgreSQL connection string |
| `ALLOWED_HOSTS` | Comma-separated list of allowed hosts |

## API Endpoints

### Auth

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
| `PATCH` | `/api/notifications/preferences/` | Update preferences |

## Notes

- Auth tokens are stored as HTTP-only cookies, not in `localStorage`.
- Refresh tokens are blacklisted on logout and rotation.
- Notification preferences are automatically seeded for all channels when a user is created.
