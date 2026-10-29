import json
from django.http import StreamingHttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    NotificationPreferenceBulkUpdateSerializer,
    NotificationPreferenceSerializer,
    NotificationPreferenceUpdateSerializer,
    NotificationReplayResponseSerializer,
    NotificationSerializer,
)
from .services.notification_preference_service import NotificationPreferenceService
from .services.notification_service import NotificationService
from .services.notification_template_service import NotificationTemplateService

from common.choices import ChannelType
from common.serializers import ErrorDetailSerializer

from .transport.redis import RedisTransport

from ..users.authentication import CustomJWTAuthentication
from .models import NotificationEventType, NotificationStatus


@extend_schema_view(
    get=extend_schema(
        operation_id="notifications_list",
        parameters=[
            OpenApiParameter(
                name="channel",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                enum=[choice.value for choice in ChannelType],
                required=False,
            ),
            OpenApiParameter(
                name="is_read",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                required=False,
            ),
            OpenApiParameter(
                name="status",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                enum=[choice.value for choice in NotificationStatus],
                required=False,
            ),
            OpenApiParameter(
                name="event_type",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                enum=[choice.value for choice in NotificationEventType],
                required=False,
            ),
        ],
        responses={
            200: NotificationSerializer(many=True),
            401: ErrorDetailSerializer,
        },
    )
)
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

    @extend_schema(
        operation_id="notification_retrieve",
        request=None,
        responses={
            200: NotificationSerializer,
            404: ErrorDetailSerializer,
            401: ErrorDetailSerializer,
        },
    )
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

    @extend_schema(
        operation_id="notification_mark_read",
        request=None,
        responses={
            200: NotificationSerializer,
            404: ErrorDetailSerializer,
            401: ErrorDetailSerializer,
        },
    )
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

    @extend_schema(
        operation_id="notification_preferences_list",
        request=None,
        responses={
            200: NotificationPreferenceSerializer(many=True),
            401: ErrorDetailSerializer,
        },
    )
    def get(self, request):
        preferences = NotificationPreferenceService.get_preferences(request.user)
        preferences_data = NotificationPreferenceSerializer(preferences, many=True).data
        return Response(preferences_data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="notification_preferences_replace",
        request=NotificationPreferenceBulkUpdateSerializer,
        responses={
            200: NotificationPreferenceSerializer(many=True),
            400: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Field-keyed validation errors.",
            ),
            401: ErrorDetailSerializer,
        },
    )
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

    @extend_schema(
        operation_id="notification_preference_update",
        request=NotificationPreferenceUpdateSerializer(partial=True),
        responses={
            200: NotificationPreferenceSerializer,
            400: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Field-keyed validation errors.",
            ),
            404: ErrorDetailSerializer,
            401: ErrorDetailSerializer,
        },
    )
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


def notification_stream(request):
    authentication = CustomJWTAuthentication()
    last_event_id = request.headers.get("Last-Event-ID")

    try:
        result = authentication.authenticate(request)
    except (AuthenticationFailed, InvalidToken):
        return JsonResponse(
            {"detail": "Authentication credentials were not provided or are invalid."},
            status=401,
        )

    if result is None:
        return JsonResponse(
            {"detail": "Authentication credentials were not provided."},
            status=401,
        )

    user, _ = result
    user_id = user.id
    channel = f"notification:user:{user_id}"

    def event_stream():
        pubsub = RedisTransport._client.pubsub()
        recovered_ids = set()

        try:
            pubsub.subscribe(channel)

            if last_event_id:
                missed_notifications = NotificationService.get_notifications_after(
                    user=user,
                    last_event_id=last_event_id,
                    channel=ChannelType.IN_APP,
                )

                for missed_notification in missed_notifications:
                    template = NotificationTemplateService.get_template(
                        event_type=missed_notification.event_type,
                        channel=missed_notification.channel,
                    )

                    if template is None:
                        continue

                    subject, body, _ = NotificationTemplateService.render_template(
                        template=template, context=missed_notification.payload
                    )

                    sse_message = json.dumps(
                        {
                            "id": str(missed_notification.id),
                            "event_type": missed_notification.event_type,
                            "title": subject,
                            "body": body,
                            "payload": missed_notification.payload,
                        }
                    )

                    recovered_ids.add(str(missed_notification.id))

                    yield (
                        f"id: {str(missed_notification.id)}\n"
                        "event: notification\n"
                        f"data: {sse_message}\n\n"
                    )

            while True:
                message = pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=15,
                )

                if message is None:
                    yield ": heartbeat\n\n"
                    continue

                data = json.loads(message["data"])

                if str(data["id"]) in recovered_ids:
                    continue

                yield (
                    f"id: {data['id']}\n"
                    "event: notification\n"
                    f"data: {message['data']}\n\n"
                )

        finally:
            pubsub.close()

    response = StreamingHttpResponse(
        event_stream(),
        content_type="text/event-stream",
    )

    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"

    return response


@method_decorator(csrf_protect, name="dispatch")
class NotificationStreamView(APIView):
    @extend_schema(
        operation_id="notification_stream_connect",
        auth=[{"BearerAuth": []}, {"CookieAuth": []}],
        request=None,
        parameters=[
            OpenApiParameter(
                name="Last-Event-ID",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.HEADER,
                required=False,
                description="Resume the event stream after this notification ID.",
            )
        ],
        responses={
            (200, "text/event-stream"): OpenApiResponse(
                response=OpenApiTypes.STR,
                description=(
                    "Server-Sent Events stream. Each notification is sent as an "
                    "`id`, `event: notification`, and JSON `data` field; heartbeat "
                    "comments are sent while idle."
                )
            ),
            (401, "application/json"): ErrorDetailSerializer,
        },
    )
    def get(self, request):
        return notification_stream(request)

    def dispatch(self, request, *args, **kwargs):
        return notification_stream(request, *args, **kwargs)


# Admin


class NotificationReplayView(APIView):
    permission_classes = [permissions.IsAdminUser]

    @extend_schema(
        operation_id="notification_replay_create",
        request=None,
        responses={
            202: NotificationReplayResponseSerializer,
            400: ErrorDetailSerializer,
            404: ErrorDetailSerializer,
            401: ErrorDetailSerializer,
            403: ErrorDetailSerializer,
        },
    )
    def post(self, request, notification_id):
        try:
            notification = NotificationService.replay_notification(
                notification_id=notification_id
            )
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=400,
            )

        if notification is None:
            return Response(
                {"detail": "Notification not found."},
                status=404,
            )

        return Response(
            {
                "detail": "Notification replay queued successfully.",
                "notification_id": str(notification.id),
            },
            status=202,
        )
