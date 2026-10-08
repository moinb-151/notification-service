import json
import uuid
from unittest.mock import patch

from django.db import transaction
from django.test import TestCase
from django.utils import timezone
from django.http import JsonResponse

from rest_framework import response, status
from rest_framework.test import APIClient

from rest_framework_simplejwt.tokens import AccessToken

from apps.notifications.models import (
    ChannelType,
    Notification,
    NotificationTemplate,
    NotificationEventType,
    NotificationStatus,
)

from ..users.models import NotificationPreference
from .services.notification_service import NotificationService
from .services.notification_template_service import NotificationTemplateService
from .providers.in_app import InAppProvider
from .transport.redis import RedisTransport
from ..users.models import User


class NotificationReplayTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpassword",
        )

        self.notification = Notification.objects.create(
            user=self.user,
            channel=ChannelType.EMAIL,
            event_type=NotificationEventType.TEST_NOTIFICATION,
            status=NotificationStatus.FAILED,
            idempotency_key="test-replay-key",
            payload={"name": "test@example.com"},
            attempts=4,
            scheduled_for="2026-09-03T10:00:00Z",
            error_message="Max retries reached.",
        )

    @patch("apps.notifications.tasks.process_notification.delay")
    def test_replay_failed_notification(self, mock_delay):
        with self.captureOnCommitCallbacks(execute=True):
            notification = NotificationService.replay_notification(self.notification.id)

        self.notification.refresh_from_db()

        self.assertIsNotNone(notification)
        self.assertEqual(
            self.notification.status,
            NotificationStatus.PENDING,
        )
        self.assertIsNone(self.notification.error_message)
        self.assertIsNone(self.notification.scheduled_for)

        self.assertEqual(self.notification.attempts, 4)
        self.assertEqual(
            self.notification.idempotency_key,
            "test-replay-key",
        )

        mock_delay.assert_called_once_with(str(self.notification.id))

    def test_cannot_replay_sent_notification(self):
        self.notification.status = NotificationStatus.SENT
        self.notification.save(update_fields=["status"])

        with self.assertRaisesMessage(
            ValueError,
            "Only notifications with status 'failed' can be replayed.",
        ):
            NotificationService.replay_notification(self.notification.id)

    def test_cannot_replay_deferred_notification(self):
        self.notification.status = NotificationStatus.DEFERRED
        self.notification.save(update_fields=["status"])

        with self.assertRaisesMessage(
            ValueError,
            "Only notifications with status 'failed' can be replayed.",
        ):
            NotificationService.replay_notification(self.notification.id)

    def test_cannot_replay_suppressed_notification(self):
        self.notification.status = NotificationStatus.SUPPRESSED
        self.notification.save(update_fields=["status"])

        with self.assertRaisesMessage(
            ValueError,
            "Only notifications with status 'failed' can be replayed.",
        ):
            NotificationService.replay_notification(self.notification.id)

    def test_replay_notification_not_found(self):
        notification_id = uuid.uuid4()

        result = NotificationService.replay_notification(notification_id)

        self.assertIsNone(result)

    @patch("apps.notifications.tasks.process_notification.delay")
    def test_replay_does_not_dispatch_task_if_transaction_rolls_back(
        self,
        mock_delay,
    ):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                NotificationService.replay_notification(self.notification.id)

                raise RuntimeError("Force transaction rollback")

        self.notification.refresh_from_db()

        self.assertEqual(
            self.notification.status,
            NotificationStatus.FAILED,
        )

        mock_delay.assert_not_called()


class NotificationReplayAPITests(TestCase):

    def setUp(self):
        self.client = APIClient()

        self.user = User.objects.create_user(
            email="user@example.com",
            password="testpassword",
        )

        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="testpassword",
            is_staff=True,
        )

        self.notification = Notification.objects.create(
            user=self.user,
            channel=ChannelType.EMAIL,
            event_type=NotificationEventType.TEST_NOTIFICATION,
            status=NotificationStatus.FAILED,
            idempotency_key="api-replay-test-key",
            payload={"name": "user@example.com"},
            attempts=4,
            error_message="Max retries reached.",
        )

        self.url = f"/notifications/replay/{self.notification.id}/"

    def test_unauthenticated_user_cannot_replay(self):
        response = self.client.post(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_non_staff_user_cannot_replay(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    @patch("apps.notifications.tasks.process_notification.delay")
    def test_staff_user_can_replay_failed_notification(self, mock_delay):
        self.client.force_authenticate(user=self.admin)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_202_ACCEPTED,
        )

        self.assertEqual(
            response.data["notification_id"],
            str(self.notification.id),
        )

        self.assertEqual(
            response.data["detail"],
            "Notification replay queued successfully.",
        )

        mock_delay.assert_called_once_with(str(self.notification.id))

    def test_replay_nonexistent_notification(self):
        self.client.force_authenticate(user=self.admin)

        notification_id = uuid.uuid4()

        response = self.client.post(f"/notifications/replay/{notification_id}/")

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

        self.assertEqual(
            response.data["detail"],
            "Notification not found.",
        )

    def test_cannot_replay_sent_notification(self):
        self.client.force_authenticate(user=self.admin)

        self.notification.status = NotificationStatus.SENT
        self.notification.save(update_fields=["status"])

        response = self.client.post(self.url)

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            response.data["detail"],
            "Only notifications with status 'failed' can be replayed.",
        )


class RedisTransportTests(TestCase):

    def test_publish_message_is_received_by_subscriber(self):
        channel = "test-notification-channel"
        message = {
            "notification_id": "123",
            "event_type": "ORDER_CREATED",
        }

        pubsub = RedisTransport._client.pubsub()
        pubsub.subscribe(channel)

        # The first message is Redis's subscription confirmation.
        pubsub.get_message(timeout=1)

        RedisTransport.publish(
            channel=channel,
            message=json.dumps(message),
        )

        received = pubsub.get_message(timeout=1)

        self.assertIsNotNone(received)
        self.assertEqual(received["type"], "message")
        self.assertEqual(
            json.loads(received["data"]),
            message,
        )

        pubsub.close()


class InAppProviderTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpassword",
        )

        # self.preference = NotificationPreference.objects.create(
        #     user=self.user,
        #     channel=ChannelType.IN_APP,
        #     enabled=True,
        # )

    @patch.object(RedisTransport, "publish")
    def test_in_app_provider_send(self, mock_publish):
        notification = Notification.objects.create(
            user=self.user,
            channel=ChannelType.IN_APP,
            event_type=NotificationEventType.TEST_NOTIFICATION,
            status=NotificationStatus.PENDING,
            idempotency_key="api-replay-test-key",
            payload={"name": "John Doe"},
        )

        result = InAppProvider.send(
            notification,
            title="Test notification",
            body="This is a test notification.",
        )

        expected_channel = f"notification:user:{notification.user_id}"
        # expected_message = json.dumps(
        #     {
        #         "id": str(notification.id),
        #         "event_type": notification.event_type,
        #         "payload": notification.payload,
        #     }
        # )

        mock_publish.assert_called_once()

        actual_message = json.loads(mock_publish.call_args[1]["message"])

        self.assertEqual(
            mock_publish.call_args[1]["channel"],
            expected_channel,
        )

        self.assertEqual(result, str(notification.id))
        self.assertEqual(actual_message["id"], str(notification.id))
        self.assertEqual(actual_message["event_type"], notification.event_type)
        self.assertEqual(actual_message["title"], "Test notification")
        self.assertEqual(actual_message["body"], "This is a test notification.")
        self.assertEqual(actual_message["payload"], notification.payload)

    @patch("apps.notifications.tasks.InAppProvider.send")
    def test_process_notification_in_app_channel(self, mock_send):
        notification = Notification.objects.create(
            user=self.user,
            channel=ChannelType.IN_APP,
            event_type=NotificationEventType.TEST_NOTIFICATION,
            status=NotificationStatus.PENDING,
            idempotency_key="process-in-app-test-key",
            payload={"name": "John Doe"},
        )

        mock_send.return_value = str(notification.id)

        from apps.notifications.tasks import process_notification

        preference = NotificationPreference.objects.get(
            user=self.user,
            channel=ChannelType.IN_APP,
        )

        NotificationTemplate.objects.create(
            event_type=NotificationEventType.TEST_NOTIFICATION,
            channel=ChannelType.IN_APP,
            subject="This is Test Notification",
            body_template=(
                "Hello {{ name }},\n\n"
                "This is a test notification from notification service.\n\n"
                "Your notification system is working correctly.\n\n"
                "Regards,\n"
                "Notification Service"
            ),
        )

        process_notification(str(notification.id))

        mock_send.assert_called_once_with(
            notification,
            title="This is Test Notification",
            body=(
                "Hello John Doe,\n\n"
                "This is a test notification from notification service.\n\n"
                "Your notification system is working correctly.\n\n"
                "Regards,\n"
                "Notification Service"
            ),
        )

        notification.refresh_from_db()

        self.assertEqual(
            notification.status,
            NotificationStatus.SENT,
        )

        self.assertEqual(
            notification.provider_message_id,
            str(notification.id),
        )


class NotificationServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpassword",
        )

        self.other_user = User.objects.create_user(
            email="other@example.com",
            password="testpassword",
        )

    def test_return_notification_after_cursor(self):
        notifications = []
        for i in range(3):
            notifications.append(
                Notification.objects.create(
                    user=self.user,
                    channel=ChannelType.EMAIL,
                    event_type=NotificationEventType.TEST_NOTIFICATION,
                    status=NotificationStatus.PENDING,
                    idempotency_key=f"cursor-test-key-{i}",
                    payload={"name": f"User {i}"},
                )
            )

        cursor = str(notifications[1].id)

        result = NotificationService.get_notifications_after(self.user, cursor, ChannelType.EMAIL)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, notifications[2].id)

    def test_other_user_cannot_access_notifications(self):
        notification = Notification.objects.create(
            user=self.other_user,
            channel=ChannelType.EMAIL,
            event_type=NotificationEventType.TEST_NOTIFICATION,
            status=NotificationStatus.PENDING,
            idempotency_key="access-test-key",
            payload={"name": "User"},
        )

        result = NotificationService.get_notifications_after(
            self.user, str(notification.id), ChannelType.EMAIL
        )

        self.assertEqual(len(result), 0)

    def test_unknown_notification_id_returns_empty(self):
        unknown_id = str(uuid.uuid4())

        result = NotificationService.get_notifications_after(self.user, unknown_id, ChannelType.EMAIL)

        self.assertEqual(len(result), 0)

    def test_chronological_order_of_notifications(self):
        notifications = []
        for i in range(5):
            notifications.append(
                Notification.objects.create(
                    user=self.user,
                    channel=ChannelType.EMAIL,
                    event_type=NotificationEventType.TEST_NOTIFICATION,
                    status=NotificationStatus.PENDING,
                    idempotency_key=f"order-test-key-{i}",
                    payload={"name": f"User {i}"},
                )
            )

        result = NotificationService.get_notifications_after(
            self.user, 
            str(notifications[0].id),
            ChannelType.EMAIL
        )

        self.assertEqual(len(result), 4)
        self.assertEqual(result[0].id, notifications[1].id)
        self.assertEqual(result[1].id, notifications[2].id)
        self.assertEqual(result[2].id, notifications[3].id)
        self.assertEqual(result[3].id, notifications[4].id)

    def test_notifications_with_same_created_at_are_ordered_deterministically(self):
        created_at = timezone.now()

        notifications = []

        for i in range(2):
            notifications.append(
                Notification.objects.create(
                    user=self.user,
                    channel=ChannelType.EMAIL,
                    event_type=NotificationEventType.TEST_NOTIFICATION,
                    status=NotificationStatus.PENDING,
                    idempotency_key=f"same-time-test-key-{i}",
                    payload={"name": f"User {i}"},
                )
            )

        Notification.objects.filter(
            id__in=[notification.id for notification in notifications]
        ).update(created_at=created_at)

        result = NotificationService.get_notifications_after(
            self.user,
            str(notifications[0].id),
            ChannelType.EMAIL
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, notifications[1].id)

class NotificationStreamTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpassword",
        )

        self.url = "/notifications/stream/"

        NotificationTemplate.objects.create(
            event_type=NotificationEventType.TEST_NOTIFICATION,
            channel=ChannelType.IN_APP,
            subject="This is Test Notification",
            body_template=(
                "Hello {{ name }},\n\n"
                "This is a test notification from notification service.\n\n"
                "Your notification system is working correctly.\n\n"
                "Regards,\n"
                "Notification Service"
            ),
        )

    @patch("apps.notifications.views.RedisTransport._client.pubsub")
    def test_replay_missed_notifications(self, mock_pubsub_method):
        notifications = []

        for i in range(3):
            notifications.append(
                Notification.objects.create(
                    user=self.user,
                    channel=ChannelType.IN_APP,
                    event_type=NotificationEventType.TEST_NOTIFICATION,
                    status=NotificationStatus.PENDING,
                    idempotency_key=f"stream-test-key-{i}",
                    payload={"name": f"User {i}"},
                )
            )

        mock_pubsub = mock_pubsub_method.return_value
        mock_pubsub.get_message.side_effect = RuntimeError("Stop SSE test")

        token = AccessToken.for_user(self.user)

        self.client.cookies["access_token"] = str(token)

        last_event_id = str(notifications[0].id)

        response = self.client.get(
            self.url,
            HTTP_LAST_EVENT_ID=last_event_id,
        )

        chunks = []

        try:
            for chunk in response.streaming_content:
                chunks.append(chunk.decode("utf-8"))
        except RuntimeError as exc:
            self.assertEqual(str(exc), "Stop SSE test")

        stream = "".join(chunks)

        self.assertIn(str(notifications[1].id), stream)
        self.assertIn(str(notifications[2].id), stream)
        self.assertNotIn(str(notifications[0].id), stream)

        self.assertLess(
            stream.index(str(notifications[1].id)),
            stream.index(str(notifications[2].id)),
        )

        self.assertIn("event: notification", stream)

    @patch("apps.notifications.views.NotificationService.get_notifications_after")
    @patch("apps.notifications.views.RedisTransport._client.pubsub")
    def test_recovery_deduplicates_live_notification(self, mock_pubsub_method, mock_get_notifications_after):
        notifications = []

        for i in range(2):
            notifications.append(
                Notification.objects.create(
                    user=self.user,
                    channel=ChannelType.IN_APP,
                    event_type=NotificationEventType.TEST_NOTIFICATION,
                    status=NotificationStatus.PENDING,
                    idempotency_key=f"stream-dedup-test-key-{i}",
                    payload={"name": f"User {i}"},
                )
            )

        new_notification = Notification.objects.create(
            user=self.user,
            channel=ChannelType.IN_APP,
            event_type=NotificationEventType.TEST_NOTIFICATION,
            status=NotificationStatus.PENDING,
            idempotency_key="stream-dedup-test-key-2",
            payload={"name": "User 2"},
        )

        mock_pubsub = mock_pubsub_method.return_value
        mock_get_notifications_after.return_value = [notifications[1]]

        duplicate_message = {
            "type": "message",
            "data": json.dumps(
                {
                    "id": str(notifications[1].id),
                    "event_type": notifications[1].event_type,
                    "title": "This is Test Notification",
                    "body": "Recovered notification",
                    "payload": notifications[1].payload,
                }
            ),
        }

        new_message = {
            "type": "message",
            "data": json.dumps(
                {
                    "id": str(new_notification.id),
                    "event_type": new_notification.event_type,
                    "title": "This is Test Notification",
                    "body": "New notification",
                    "payload": new_notification.payload,
                }
            ),
        }

        mock_pubsub.get_message.side_effect = [
            duplicate_message,
            new_message,
            RuntimeError("Stop SSE test"),
        ]

        token = AccessToken.for_user(self.user)

        self.client.cookies["access_token"] = str(token)

        last_event_id = str(notifications[0].id)

        response = self.client.get(
            self.url,
            HTTP_LAST_EVENT_ID=last_event_id,
        )

        chunks = []

        try:
            for chunk in response.streaming_content:
                chunks.append(chunk.decode("utf-8"))
        except RuntimeError as exc:
            self.assertEqual(str(exc), "Stop SSE test")

        stream = "".join(chunks)

        self.assertNotIn(str(notifications[0].id), stream)
        self.assertEqual(
            stream.count(f"id: {notifications[1].id}\n"),
            1,
        )

        self.assertEqual(
            stream.count(f"id: {new_notification.id}\n"),
            1,
        )

    @patch("apps.notifications.views.RedisTransport._client.pubsub")
    def test_stream_channel_filtering(self, mock_pubsub_method):

        notifications = []

        for i in range(3):
            notifications.append(
                Notification.objects.create(
                    user=self.user,
                    channel=ChannelType.EMAIL if i == 1 else ChannelType.IN_APP,
                    event_type=NotificationEventType.TEST_NOTIFICATION,
                    status=NotificationStatus.PENDING,
                    idempotency_key=f"stream-filter-test-key-{i}",
                    payload={"name": f"User {i}"},
                )
            )

        mock_pubsub = mock_pubsub_method.return_value
        mock_pubsub.get_message.side_effect = RuntimeError("Stop SSE test")

        token = AccessToken.for_user(self.user)

        self.client.cookies["access_token"] = str(token)

        last_event_id = str(notifications[0].id)

        response = self.client.get(
            self.url,
            HTTP_LAST_EVENT_ID=last_event_id,
        )

        chunks = []

        try:
            for chunk in response.streaming_content:
                chunks.append(chunk.decode("utf-8"))
        except RuntimeError as exc:
            self.assertEqual(str(exc), "Stop SSE test")

        stream = "".join(chunks)

        self.assertNotIn(str(notifications[0].id), stream)
        self.assertNotIn(str(notifications[1].id), stream)
        self.assertIn(str(notifications[2].id), stream)

    @patch("apps.notifications.views.NotificationService.get_notifications_after")
    @patch("apps.notifications.views.RedisTransport._client.pubsub")
    def test_stream_with_no_last_event_id(self, mock_pubsub_method, mock_get_notifications_after):
        mock_pubsub = mock_pubsub_method.return_value
        mock_pubsub.get_message.side_effect = RuntimeError("Stop SSE test")

        token = AccessToken.for_user(self.user)

        self.client.cookies["access_token"] = str(token)

        response = self.client.get(self.url)

        chunks = []

        try:
            for chunk in response.streaming_content:
                chunks.append(chunk.decode("utf-8"))
        except RuntimeError as exc:
            self.assertEqual(str(exc), "Stop SSE test")

        stream = "".join(chunks)

        self.assertNotIn("event: notification", stream)
        mock_get_notifications_after.assert_not_called()

    def test_stream_with_unauthenticated_user(self):
        response = self.client.get(self.url)

        self.assertEqual(
            response.status_code,
            401,
        )

        self.assertIsInstance(response, JsonResponse)
        self.assertEqual(
            response.json(),
            {"detail": "Authentication credentials were not provided."},
        )

class NotificationTemplateServiceTests(TestCase):

    def test_order_templates_exist_for_all_channels(self):
        event_types = [
            NotificationEventType.ORDER_CREATED,
            NotificationEventType.ORDER_CANCELLED,
            NotificationEventType.ORDER_SHIPPED,
            NotificationEventType.ORDER_DELIVERED,
        ]

        channels = [
            ChannelType.EMAIL,
            ChannelType.SMS,
            ChannelType.IN_APP,
        ]

        for event_type in event_types:
            for channel in channels:
                template = NotificationTemplateService.get_template(
                    event_type=event_type,
                    channel=channel,
                )

                self.assertIsNotNone(
                    template,
                    f"Missing template: {event_type} / {channel}",
                )

    def test_get_template_returns_none_when_template_does_not_exist(self):
        template = NotificationTemplateService.get_template(
            event_type=NotificationEventType.ORDER_CREATED,
            channel="nonexistent",
        )

        self.assertIsNone(template)

    def test_order_templates_render_successfully(self):
        context = {
            "order_id": "019ed145-6499-7121-9cdc-8715a96d9a62",
            "order_status": "PENDING",
            "total_amount": "1500.00",
            "metadata": {
                "shipping_address": {
                    "name": "Moin Bagban",
                    "line1": "123 MG Road",
                    "line2": "Near City Mall",
                    "city": "Pune",
                    "state": "Maharashtra",
                    "country": "India",
                    "postal_code": "411001",
                },
                "notes": "Please deliver between 10 AM and 1 PM.",
                "gift": False,
            },
        }

        event_types = [
            NotificationEventType.ORDER_CREATED,
            NotificationEventType.ORDER_CANCELLED,
            NotificationEventType.ORDER_SHIPPED,
            NotificationEventType.ORDER_DELIVERED,
        ]

        channels = [
            ChannelType.EMAIL,
            ChannelType.SMS,
            ChannelType.IN_APP,
        ]

        for event_type in event_types:
            for channel in channels:
                template = NotificationTemplateService.get_template(
                    event_type=event_type,
                    channel=channel,
                )

                self.assertIsNotNone(template)

                subject, body = NotificationTemplateService.render_template(
                    template=template,
                    context=context,
                )

                self.assertIsInstance(subject, str)
                self.assertIsInstance(body, str)
                self.assertIn(context["order_id"], subject + body)

    