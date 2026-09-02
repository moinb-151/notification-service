from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    NotificationPreferenceBulkUpdateSerializer,
    NotificationPreferenceSerializer,
    NotificationPreferenceUpdateSerializer,
    NotificationSerializer,
)
from .services.notification_preference_service import NotificationPreferenceService
from .services.notification_service import NotificationService


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


class NotificationPreferenceListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        preferences = NotificationPreferenceService.get_preferences(request.user)
        preferences_data = NotificationPreferenceSerializer(preferences, many=True).data
        return Response(preferences_data, status=status.HTTP_200_OK)

    def put(self, request):
        serializer = NotificationPreferenceBulkUpdateSerializer(
            data=request.data,
        )

        serializer.is_valid(raise_exception=True)

        preferences = NotificationPreferenceService.replace_preferences(
            user=request.user,
            preferences_data=serializer.validated_data["preferences"],
        )

        response_serializer = NotificationPreferenceSerializer(
            preferences,
            many=True,
        )

        return Response(
            response_serializer.data,
            status=status.HTTP_200_OK,
        )


class NotificationPreferenceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, channel):
        serializer = NotificationPreferenceUpdateSerializer(
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)

        preference = NotificationPreferenceService.update_preference(
            user=request.user,
            channel=channel,
            validated_data=serializer.validated_data,
        )

        if preference is None:
            return Response(
                {"detail": "Notification preference not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        response_serializer = NotificationPreferenceSerializer(preference)

        return Response(
            response_serializer.data,
            status=status.HTTP_200_OK,
        )
