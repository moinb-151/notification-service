import hashlib
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.db import transaction

from rest_framework.exceptions import ValidationError

from ..notifications.models import Notification
from ..notifications.models import NotificationEventType, NotificationStatus
from .models import Order, OrderItem, OrderStatus, Product
from .services.order_service import OrderService
from ..notifications.services.notification_service import NotificationService
from ..users.models import User
from common.choices import ChannelType


class OrderNotificationIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            email="test@example.com",
            phone="9876543210",
        )

        self.product = Product.objects.create(
            sku="TEST-001",
            name="Test Product",
            price=Decimal("100.00"),
            stock_quantity=10,
            is_active=True,
        )

        self.idempotency_key = "11111111-1111-1111-1111-111111111111"

        self.validated_data = {
            "items": [
                {
                    "product_id": self.product.id,
                    "quantity": 2,
                }
            ],
            "metadata": {},
        }

        self.context = {
            "user": self.user,
            "key": self.idempotency_key,
        }

    @patch("apps.notifications.tasks.process_notification.delay")
    def test_creating_order_creates_email_and_sms_notifications(
        self,
        mock_process_notification,
    ):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            result = OrderService.create_order(
                validated_data=self.validated_data.copy(),
                context=self.context,
            )

        self.assertTrue(result.created)

        order = result.order

        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderItem.objects.count(), 1)

        notifications = Notification.objects.filter(order=order)

        self.assertEqual(notifications.count(), 2)

        channels = set(notifications.values_list("channel", flat=True))

        self.assertEqual(
            channels,
            {
                ChannelType.EMAIL,
                ChannelType.SMS,
            },
        )

        for notification in notifications:
            self.assertEqual(
                notification.event_type,
                NotificationEventType.ORDER_CREATED,
            )

            self.assertEqual(
                notification.status,
                NotificationStatus.PENDING,
            )

            self.assertEqual(
                notification.user,
                self.user,
            )

            self.assertEqual(
                notification.order,
                order,
            )

            self.assertEqual(
                notification.payload["order_id"],
                str(order.id),
            )

            self.assertEqual(
                notification.payload["order_status"],
                order.status,
            )

            self.assertEqual(
                notification.payload["total_amount"],
                str(order.total_amount),
            )

        self.assertEqual(len(callbacks), 2)
        self.assertEqual(
            mock_process_notification.call_count,
            2,
        )

        notification_ids = {str(notification.id) for notification in notifications}

        dispatched_ids = {
            call.args[0] for call in mock_process_notification.call_args_list
        }

        self.assertEqual(dispatched_ids, notification_ids)

    @patch("apps.notifications.tasks.process_notification.delay")
    def test_repeated_idempotency_key_does_not_create_duplicate_notifications(
        self,
        mock_process_notification,
    ):
        with self.captureOnCommitCallbacks(execute=True):
            first_result = OrderService.create_order(
                validated_data=self.validated_data.copy(),
                context=self.context,
            )

        with self.captureOnCommitCallbacks(execute=True):
            second_result = OrderService.create_order(
                validated_data=self.validated_data.copy(),
                context=self.context,
            )

        self.assertTrue(first_result.created)
        self.assertFalse(second_result.created)

        self.assertEqual(
            first_result.order.id,
            second_result.order.id,
        )

        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderItem.objects.count(), 1)

        notifications = Notification.objects.filter(order=first_result.order)

        self.assertEqual(notifications.count(), 2)

        self.assertEqual(
            mock_process_notification.call_count,
            2,
        )

    @patch("apps.notifications.tasks.process_notification.delay")
    @patch(
        "apps.notifications.services.notification_service.NotificationService.create_order_created_notification",
        side_effect=Exception("Notification creation failed"),
    )
    def test_notification_failure_rolls_back_order(
        self,
        mock_create_notification,
        mock_process_notification,
    ):
        with self.assertRaises(Exception):
            with self.captureOnCommitCallbacks(execute=True):
                OrderService.create_order(
                    validated_data=self.validated_data.copy(),
                    context=self.context,
                )

        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)

        self.product.refresh_from_db()

        self.assertEqual(
            self.product.stock_quantity,
            10,
        )

        self.assertEqual(
            Notification.objects.count(),
            0,
        )

        mock_process_notification.assert_not_called()

    def test_notification_idempotency_keys_are_deterministic_and_channel_specific(self):
        with self.captureOnCommitCallbacks(execute=True):
            result = OrderService.create_order(
                validated_data=self.validated_data.copy(),
                context=self.context,
            )

        notifications = list(
            Notification.objects.filter(order=result.order).order_by("channel")
        )

        self.assertEqual(len(notifications), 2)

        email_notification = next(
            notification
            for notification in notifications
            if notification.channel == ChannelType.EMAIL
        )

        sms_notification = next(
            notification
            for notification in notifications
            if notification.channel == ChannelType.SMS
        )

        self.assertNotEqual(
            email_notification.idempotency_key,
            sms_notification.idempotency_key,
        )

        expected_email_key = hashlib.sha256(
            f"{self.user.id}:{result.order.id}:"
            f"{NotificationEventType.ORDER_CREATED}:{ChannelType.EMAIL}".encode()
        ).hexdigest()

        expected_sms_key = hashlib.sha256(
            f"{self.user.id}:{result.order.id}:"
            f"{NotificationEventType.ORDER_CREATED}:{ChannelType.SMS}".encode()
        ).hexdigest()

        self.assertEqual(
            email_notification.idempotency_key,
            expected_email_key,
        )

        self.assertEqual(
            sms_notification.idempotency_key,
            expected_sms_key,
        )

    @patch("apps.notifications.tasks.process_notification.delay")
    def test_notifications_are_not_dispatched_when_order_transaction_rolls_back(
        self,
        mock_process_notification,
    ):
        with self.assertRaises(RuntimeError):
            with self.captureOnCommitCallbacks(execute=True):
                with transaction.atomic():
                    result = OrderService.create_order(
                        validated_data=self.validated_data.copy(),
                        context=self.context,
                    )

                    self.assertTrue(result.created)

                    raise RuntimeError("Force transaction rollback")

        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)

        mock_process_notification.assert_not_called()

    @patch("apps.notifications.tasks.process_notification.delay")
    def test_cancelling_order_creates_email_and_sms_notifications(
        self,
        mock_process_notification,
    ):
        with self.captureOnCommitCallbacks(execute=True):
            order_result = OrderService.create_order(
                validated_data=self.validated_data.copy(),
                context=self.context,
            )

        order = order_result.order

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 8)

        mock_process_notification.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            cancelled_order = OrderService.cancel_order(
                order_id=order.id,
                user=self.user,
            )

        self.assertIsNotNone(cancelled_order)
        self.assertEqual(
            cancelled_order.status,
            OrderStatus.CANCELLED,
        )

        self.product.refresh_from_db()

        self.assertEqual(
            self.product.stock_quantity,
            10,
        )

        notifications = Notification.objects.filter(
            order=order,
            event_type=NotificationEventType.ORDER_CANCELLED,
        )

        self.assertEqual(notifications.count(), 2)

        channels = set(notifications.values_list("channel", flat=True))

        self.assertEqual(
            channels,
            {
                ChannelType.EMAIL,
                ChannelType.SMS,
            },
        )

        for notification in notifications:
            self.assertEqual(
                notification.user,
                self.user,
            )

            self.assertEqual(
                notification.order,
                order,
            )

            self.assertEqual(
                notification.status,
                NotificationStatus.PENDING,
            )

            self.assertEqual(
                notification.payload["order_id"],
                str(order.id),
            )

            self.assertEqual(
                notification.payload["order_status"],
                OrderStatus.CANCELLED,
            )

            self.assertEqual(
                notification.payload["total_amount"],
                str(order.total_amount),
            )

        self.assertEqual(
            mock_process_notification.call_count,
            2,
        )

        notification_ids = {str(notification.id) for notification in notifications}

        dispatched_ids = {
            call.args[0] for call in mock_process_notification.call_args_list
        }

        self.assertEqual(
            dispatched_ids,
            notification_ids,
        )

    @patch("apps.notifications.tasks.process_notification.delay")
    @patch(
        "apps.notifications.services.notification_service.NotificationService.create_order_cancelled_notification",
        side_effect=Exception("Notification creation failed"),
    )
    def test_cancellation_notification_failure_rolls_back_cancellation(
        self,
        mock_create_notification,
        mock_process_notification,
    ):
        with self.captureOnCommitCallbacks(execute=True):
            order_result = OrderService.create_order(
                validated_data=self.validated_data.copy(),
                context=self.context,
            )

        order = order_result.order

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 8)

        mock_process_notification.reset_mock()

        with self.assertRaises(Exception):
            with self.captureOnCommitCallbacks(execute=True):
                OrderService.cancel_order(
                    order_id=order.id,
                    user=self.user,
                )

        order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(
            order.status,
            OrderStatus.PENDING,
        )

        self.assertEqual(
            self.product.stock_quantity,
            8,
        )

        self.assertEqual(
            Notification.objects.filter(
                order=order,
                event_type=NotificationEventType.ORDER_CANCELLED,
            ).count(),
            0,
        )

        mock_process_notification.assert_not_called()

    @patch("apps.notifications.tasks.process_notification.delay")
    def test_invalid_cancellation_does_not_create_notification(
        self,
        mock_process_notification,
    ):
        with self.captureOnCommitCallbacks(execute=True):
            order_result = OrderService.create_order(
                validated_data=self.validated_data.copy(),
                context=self.context,
            )

        order = order_result.order

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 8)

        mock_process_notification.reset_mock()

        order.status = OrderStatus.SHIPPED
        order.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            with self.captureOnCommitCallbacks(execute=True):
                OrderService.cancel_order(
                    order_id=order.id,
                    user=self.user,
                )

        order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(
            order.status,
            OrderStatus.SHIPPED,
        )

        self.assertEqual(
            self.product.stock_quantity,
            8,
        )

        self.assertEqual(
            Notification.objects.filter(
                order=order,
                event_type=NotificationEventType.ORDER_CANCELLED,
            ).count(),
            0,
        )

        mock_process_notification.assert_not_called()

    @patch("apps.notifications.tasks.process_notification.delay")
    def test_shipping_order_creates_notifications(
        self,
        mock_process_notification,
    ):
        with self.captureOnCommitCallbacks(execute=True):
            order_result = OrderService.create_order(
                validated_data=self.validated_data.copy(),
                context=self.context,
            )

        order = order_result.order

        # Move order to CONFIRMED first.
        order = OrderService.update_order(
            order_id=order.id,
            user=self.user,
            status=OrderStatus.CONFIRMED,
        )

        mock_process_notification.reset_mock()

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            order = OrderService.update_order(
                order_id=order.id,
                user=self.user,
                status=OrderStatus.SHIPPED,
            )

        order.refresh_from_db()

        self.assertEqual(
            order.status,
            OrderStatus.SHIPPED,
        )

        notifications = Notification.objects.filter(
            order=order,
            event_type=NotificationEventType.ORDER_SHIPPED,
        )

        self.assertEqual(
            notifications.count(),
            2,
        )

        self.assertSetEqual(
            set(notifications.values_list("channel", flat=True)),
            {
                ChannelType.EMAIL,
                ChannelType.SMS,
            },
        )

        for notification in notifications:
            self.assertEqual(
                notification.user,
                self.user,
            )

            self.assertEqual(
                notification.order,
                order,
            )

            self.assertEqual(
                notification.status,
                NotificationStatus.PENDING,
            )

            self.assertEqual(
                notification.payload["order_id"],
                str(order.id),
            )

            self.assertEqual(
                notification.payload["order_status"],
                OrderStatus.SHIPPED,
            )

            self.assertEqual(
                notification.payload["total_amount"],
                str(order.total_amount),
            )

        self.assertEqual(
            len(callbacks),
            2,
        )

        self.assertEqual(
            mock_process_notification.call_count,
            2,
        )

        dispatched_ids = {
            call.args[0] for call in mock_process_notification.call_args_list
        }

        notification_ids = {str(notification.id) for notification in notifications}

        self.assertSetEqual(
            dispatched_ids,
            notification_ids,
        )

    @patch("apps.notifications.tasks.process_notification.delay")
    @patch(
        "apps.notifications.services.notification_service."
        "NotificationService.create_order_shipped_notification"
    )
    def test_shipping_notification_failure_rolls_back_status(
        self,
        mock_create_notification,
        mock_process_notification,
    ):
        with self.captureOnCommitCallbacks(execute=True):
            order_result = OrderService.create_order(
                validated_data=self.validated_data.copy(),
                context=self.context,
            )

        order = order_result.order

        OrderService.update_order(
            order_id=order.id,
            user=self.user,
            status=OrderStatus.CONFIRMED,
        )

        mock_process_notification.reset_mock()

        mock_create_notification.side_effect = Exception("Notification creation failed")

        with self.assertRaises(Exception):
            with self.captureOnCommitCallbacks(execute=True):
                OrderService.update_order(
                    order_id=order.id,
                    user=self.user,
                    status=OrderStatus.SHIPPED,
                )

        order.refresh_from_db()

        self.assertEqual(
            order.status,
            OrderStatus.CONFIRMED,
        )

        self.assertEqual(
            Notification.objects.filter(
                order=order,
                event_type=NotificationEventType.ORDER_SHIPPED,
            ).count(),
            0,
        )

        mock_process_notification.assert_not_called()

    @patch("apps.notifications.tasks.process_notification.delay")
    def test_invalid_shipping_transition_does_not_create_notification(
        self,
        mock_process_notification,
    ):
        with self.captureOnCommitCallbacks(execute=True):
            order_result = OrderService.create_order(
                validated_data=self.validated_data.copy(),
                context=self.context,
            )

        order = order_result.order

        self.product.refresh_from_db()
        self.assertEqual(
            self.product.stock_quantity,
            8,
        )

        mock_process_notification.reset_mock()

        with self.assertRaises(ValidationError):
            with self.captureOnCommitCallbacks(execute=True):
                OrderService.update_order(
                    order_id=order.id,
                    user=self.user,
                    status=OrderStatus.SHIPPED,
                )

        order.refresh_from_db()

        self.assertEqual(
            order.status,
            OrderStatus.PENDING,
        )

        self.assertEqual(
            Notification.objects.filter(
                order=order,
                event_type=NotificationEventType.ORDER_SHIPPED,
            ).count(),
            0,
        )

        mock_process_notification.assert_not_called()

    @patch("apps.notifications.tasks.process_notification.delay")
    def test_non_status_update_does_not_create_shipping_notification(
        self,
        mock_process_notification,
    ):
        with self.captureOnCommitCallbacks(execute=True):
            order_result = OrderService.create_order(
                validated_data=self.validated_data.copy(),
                context=self.context,
            )

        order = order_result.order

        OrderService.update_order(
            order_id=order.id,
            user=self.user,
            status=OrderStatus.CONFIRMED,
        )

        with self.captureOnCommitCallbacks(execute=True):
            order = OrderService.update_order(
                order_id=order.id,
                user=self.user,
                status=OrderStatus.SHIPPED,
            )

        mock_process_notification.reset_mock()

        shipping_notification_count = Notification.objects.filter(
            order=order,
            event_type=NotificationEventType.ORDER_SHIPPED,
        ).count()

        self.assertEqual(
            shipping_notification_count,
            2,
        )

        with self.captureOnCommitCallbacks(execute=True):
            OrderService.update_order(
                order_id=order.id,
                user=self.user,
                metadata={"updated": True},
            )

        self.assertEqual(
            Notification.objects.filter(
                order=order,
                event_type=NotificationEventType.ORDER_SHIPPED,
            ).count(),
            2,
        )

        mock_process_notification.assert_not_called()

    @patch("apps.notifications.tasks.process_notification.delay")
    def test_delivery_order_creates_notifications(
        self,
        mock_process_notification,
    ):
        with self.captureOnCommitCallbacks(execute=True):
            order_result = OrderService.create_order(
                validated_data=self.validated_data.copy(),
                context=self.context,
            )

        order = order_result.order

        OrderService.update_order(
            order_id=order.id,
            user=self.user,
            status=OrderStatus.CONFIRMED,
        )

        OrderService.update_order(
            order_id=order.id,
            user=self.user,
            status=OrderStatus.SHIPPED,
        )

        mock_process_notification.reset_mock()

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            order = OrderService.update_order(
                order_id=order.id,
                user=self.user,
                status=OrderStatus.DELIVERED,
            )

        order.refresh_from_db()

        self.assertEqual(
            order.status,
            OrderStatus.DELIVERED,
        )

        notifications = Notification.objects.filter(
            order=order,
            event_type=NotificationEventType.ORDER_DELIVERED,
        )

        self.assertEqual(
            notifications.count(),
            2,
        )

        self.assertSetEqual(
            set(notifications.values_list("channel", flat=True)),
            {
                ChannelType.EMAIL,
                ChannelType.SMS,
            },
        )

        for notification in notifications:
            self.assertEqual(
                notification.user,
                self.user,
            )

            self.assertEqual(
                notification.order,
                order,
            )

            self.assertEqual(
                notification.status,
                NotificationStatus.PENDING,
            )

            self.assertEqual(
                notification.payload["order_id"],
                str(order.id),
            )

            self.assertEqual(
                notification.payload["order_status"],
                OrderStatus.DELIVERED,
            )

            self.assertEqual(
                notification.payload["total_amount"],
                str(order.total_amount),
            )

        self.assertEqual(
            len(callbacks),
            2,
        )

        self.assertEqual(
            mock_process_notification.call_count,
            2,
        )

        dispatched_ids = {
            call.args[0] for call in mock_process_notification.call_args_list
        }

        notification_ids = {str(notification.id) for notification in notifications}

        self.assertSetEqual(
            dispatched_ids,
            notification_ids,
        )

    @patch(
        "apps.notifications.services.notification_service.NotificationService"
        ".create_order_delivered_notification"
    )
    def test_delivery_notification_failure_rolls_back_delivery(
        self,
        mock_create_notification,
    ):
        with self.captureOnCommitCallbacks(execute=True):
            order_result = OrderService.create_order(
                validated_data=self.validated_data.copy(),
                context=self.context,
            )

        order = order_result.order

        # Move order to SHIPPED first.
        OrderService.update_order(
            order_id=order.id,
            user=self.user,
            status=OrderStatus.CONFIRMED,
        )

        OrderService.update_order(
            order_id=order.id,
            user=self.user,
            status=OrderStatus.SHIPPED,
        )

        mock_create_notification.side_effect = Exception("Notification creation failed")

        with self.assertRaises(Exception):
            OrderService.update_order(
                order_id=order.id,
                user=self.user,
                status=OrderStatus.DELIVERED,
            )

        order.refresh_from_db()

        # Delivery must be rolled back.
        self.assertEqual(order.status, OrderStatus.SHIPPED)

        # No delivered notifications should exist.
        self.assertFalse(
            Notification.objects.filter(
                order=order,
                event_type=NotificationEventType.ORDER_DELIVERED,
            ).exists()
        )

    def test_invalid_delivery_transition_creates_no_notifications(self):
        with self.captureOnCommitCallbacks(execute=True):
            order_result = OrderService.create_order(
                validated_data=self.validated_data.copy(),
                context=self.context,
            )

        order = order_result.order

        with self.assertRaises(ValidationError):
            OrderService.update_order(
                order_id=order.id,
                user=self.user,
                status=OrderStatus.DELIVERED,
            )

        order.refresh_from_db()

        self.assertEqual(order.status, OrderStatus.PENDING)

        self.assertFalse(
            Notification.objects.filter(
                order=order,
                event_type=NotificationEventType.ORDER_DELIVERED,
            ).exists()
        )

    @patch("apps.notifications.tasks.process_notification.delay")
    def test_delivered_order_non_status_update_creates_no_duplicate_notification(
        self,
        mock_process_notification,
    ):
        with self.captureOnCommitCallbacks(execute=True):
            order_result = OrderService.create_order(
                validated_data=self.validated_data.copy(),
                context=self.context,
            )

        order = order_result.order

        # Move order through the lifecycle to DELIVERED.
        OrderService.update_order(
            order_id=order.id,
            user=self.user,
            status=OrderStatus.CONFIRMED,
        )

        OrderService.update_order(
            order_id=order.id,
            user=self.user,
            status=OrderStatus.SHIPPED,
        )

        mock_process_notification.reset_mock()

        with self.captureOnCommitCallbacks(execute=True):
            OrderService.update_order(
                order_id=order.id,
                user=self.user,
                status=OrderStatus.DELIVERED,
            )

        delivered_notifications = Notification.objects.filter(
            order=order,
            event_type=NotificationEventType.ORDER_DELIVERED,
        )

        self.assertEqual(delivered_notifications.count(), 2)
        self.assertEqual(mock_process_notification.call_count, 2)

        mock_process_notification.reset_mock()

        # Update a non-status field after delivery.
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            OrderService.update_order(
                order_id=order.id,
                user=self.user,
                metadata={"updated": True},
            )

        order.refresh_from_db()

        self.assertEqual(order.status, OrderStatus.DELIVERED)
        self.assertEqual(order.metadata, {"updated": True})

        # No new delivery notifications or Celery tasks.
        self.assertEqual(
            Notification.objects.filter(
                order=order,
                event_type=NotificationEventType.ORDER_DELIVERED,
            ).count(),
            2,
        )
        self.assertEqual(len(callbacks), 0)
        mock_process_notification.assert_not_called()