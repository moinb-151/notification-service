import uuid
from unittest.mock import patch

from django.db import transaction
from django.test import TestCase

from rest_framework import status
from rest_framework.test import APIClient

from apps.notifications.models import (
    ChannelType,
    Notification,
    NotificationEventType,
    NotificationStatus,
)
from apps.notifications.services.notification_service import NotificationService
from apps.users.models import User


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

        mock_delay.assert_called_once_with(
            str(self.notification.id)
        )

    def test_replay_nonexistent_notification(self):
        self.client.force_authenticate(user=self.admin)

        notification_id = uuid.uuid4()

        response = self.client.post(
            f"/notifications/replay/{notification_id}/"
        )

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