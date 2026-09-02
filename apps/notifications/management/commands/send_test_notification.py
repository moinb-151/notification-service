from django.core.management.base import BaseCommand

from ....notifications.services.notification_service import NotificationService
from ....users.models import User
from ...tasks import process_notification
import uuid_utils.compat as uuid


class Command(BaseCommand):
    help = "Send a test notification"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            required=True,
        )
        parser.add_argument(
            "--channel",
            required=True,
            choices=["email", "sms", "in_app"],
        )

    def handle(self, *args, **options):
        user_id = options["user"]
        channel = options["channel"]

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f"User with id {user_id} does not exist.")
            )
            return

        result = NotificationService.create_notification(
            validated_data={
                "user": user,
                "channel": channel,
                "event_type": "TEST_NOTIFICATION",
                "idempotency_key": f"test-{uuid.uuid7()}",
                "payload": {
                    "name": user.email,
                },
            },
        )

        notification = result.notification

        process_notification.delay(
            notification_id=notification.id,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Test notification queued for {user.email} via {channel}."
            )
        )
