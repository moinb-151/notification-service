import json

import pika
import logging
from django.conf import settings
from django.core.management.base import BaseCommand
from ...services.dlq_service import NotificationDLQService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Consume messages from the notification DLQ"

    def handle(self, *args, **options):
        connection = pika.BlockingConnection(
            pika.URLParameters(settings.CELERY_BROKER_URL)
        )

        channel = connection.channel()

        channel.confirm_delivery()

        channel.queue_declare(
            queue="notification.dlq",
            durable=True,
        )

        def callback(ch, method, properties, body):
            try:
                message = json.loads(body)

            except json.JSONDecodeError:
                self.stderr.write(
                    self.style.ERROR("Malformed JSON received from notification DLQ.")
                )

                ch.basic_ack(
                    delivery_tag=method.delivery_tag,
                )
                return

            headers = properties.headers or {}

            notification_id = NotificationDLQService.extract_notification_id(message)

            if notification_id is None:
                self.stderr.write(
                    self.style.ERROR(
                        "Could not extract notification_id from DLQ message."
                    )
                )

                ch.basic_ack(
                    delivery_tag=method.delivery_tag,
                )
                return

            task_id = headers.get("id")
            retries = headers.get("retries", 0)

            try:
                NotificationDLQService.handle(
                    notification_id=notification_id,
                    task_id=task_id,
                    retries=retries,
                    headers=headers,
                )

            except Exception:
                logger.exception(
                    "Failed to process notification DLQ message",
                    extra={
                        "notification_id": notification_id,
                        "task_id": task_id,
                    },
                )

                try:
                    ch.basic_publish(
                        exchange="notification.parking",
                        routing_key="notification.parking",
                        body=body,
                        properties=properties,
                        mandatory=True,
                    )
                except (pika.exceptions.NackError, pika.exceptions.UnroutableError):
                    logger.exception(
                        "Failed to move DLQ message to parking queue",
                        extra={
                            "notification_id": notification_id,
                            "task_id": task_id,
                        },
                    )

                    return

                ch.basic_ack(
                    delivery_tag=method.delivery_tag,
                )
                return

            ch.basic_ack(
                delivery_tag=method.delivery_tag,
            )

        channel.basic_consume(
            queue="notification.dlq",
            on_message_callback=callback,
            auto_ack=False,
        )

        self.stdout.write(self.style.SUCCESS("Waiting for DLQ messages..."))

        try:
            channel.start_consuming()
        except KeyboardInterrupt:
            self.stdout.write("\nStopping DLQ consumer...")
        finally:
            connection.close()
