import logging
import time

import pika
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Initialize the notification RabbitMQ exchanges, queues, and bindings"

    def handle(self, *args, **options):
        parameters = pika.URLParameters(settings.CELERY_BROKER_URL)

        for attempt in range(1, 6):
            try:
                with pika.BlockingConnection(parameters) as connection:
                    channel = connection.channel()

                    # Dead-letter exchange used by the Celery source queue.
                    channel.exchange_declare(
                        exchange="notification.dlx",
                        exchange_type="direct",
                        durable=True,
                    )

                    # Parking exchange routes messages that the DLQ consumer
                    # cannot process to the parking queue.
                    channel.exchange_declare(
                        exchange="notification.parking",
                        exchange_type="direct",
                        durable=True,
                    )

                    channel.queue_declare(
                        queue="notification.dlq",
                        durable=True,
                    )
                    channel.queue_bind(
                        queue="notification.dlq",
                        exchange="notification.dlx",
                        routing_key="notification.dlq",
                    )

                    channel.queue_declare(
                        queue="notification.parking",
                        durable=True,
                    )
                    channel.queue_bind(
                        queue="notification.parking",
                        exchange="notification.parking",
                        routing_key="notification.parking",
                    )

                self.stdout.write(
                    self.style.SUCCESS(
                        "RabbitMQ notification topology initialized successfully."
                    )
                )
                return

            except pika.exceptions.AMQPError as exc:
                logger.warning(
                    "RabbitMQ topology initialization attempt %s/5 failed: %s",
                    attempt,
                    exc,
                )
                if attempt == 5:
                    raise CommandError(
                        "RabbitMQ topology initialization failed after 5 attempts. "
                        "Check broker credentials, vhost, and existing queue arguments."
                    ) from exc
                time.sleep(3)
