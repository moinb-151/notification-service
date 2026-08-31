import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()

CELERY_BEAT_SCHEDULE = {
    "process-deferred-notifications": {
        "task": "apps.notifications.tasks.process_deferred_notifications",
        "schedule": 60.0,
    },
}
