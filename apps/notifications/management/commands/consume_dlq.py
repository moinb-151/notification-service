import json

import pika
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Consume messages from the notification DLQ"

    def handle(self, *args, **options):
        connection = pika.BlockingConnection(
            pika.URLParameters(settings.CELERY_BROKER_URL)
        )

        channel = connection.channel()

        channel.queue_declare(
            queue="notification.dlq",
            durable=True,
        )

        def callback(ch, method, properties, body):
            message = json.loads(body)

            notification_id = message[1]["notification_id"]["__value__"]["hex"]

            self.stdout.write("\n=== DLQ MESSAGE ===")
            self.stdout.write(f"Notification ID: {notification_id}")

            self.stdout.write("\n=== HEADERS ===")
            self.stdout.write(str(properties.headers))

            ch.basic_ack(
                delivery_tag=method.delivery_tag,
            )

        channel.basic_consume(
            queue="notification.dlq",
            on_message_callback=callback,
            auto_ack=False,
        )

        self.stdout.write(
            self.style.SUCCESS("Waiting for DLQ messages...")
        )

        try:
            channel.start_consuming()
        except KeyboardInterrupt:
            self.stdout.write("\nStopping DLQ consumer...")
        finally:
            connection.close()