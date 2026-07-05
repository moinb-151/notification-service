from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from .serializers import NotificationPreferenceSerializer, NotificationSerializer
from .services import NotificationService


class NotificationListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return NotificationService.list_notifications(
            user=self.request.user,
            channel=self.request.query_params.get("channel"),
            is_read=self.request.query_params.get("is_read"),
            status=self.request.query_params.get("status"),
            event_type=self.request.query_params.get("event_type"),
        )


class NotificationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, notification_id):
        notification = NotificationService.get_notification(
            notification_id=notification_id,
            user=request.user,
        )

        if notification is None:
            return Response(
                {"detail": "Notification not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        notification_data = NotificationSerializer(notification).data

        return Response(notification_data, status=status.HTTP_200_OK)

    def patch(self, request, notification_id):
        notification = NotificationService.mark_as_read(
            notification_id=notification_id,
            user=request.user,
        )

        if notification is None:
            return Response(
                {"detail": "Notification not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        notification_data = NotificationSerializer(notification).data

        return Response(
            notification_data,
            status=status.HTTP_200_OK,
        )
