from django.urls import path

from .views import NotificationListView, NotificationView

urlpatterns = [
    path("", NotificationListView.as_view(), name="list-notifications"),
    path(
        "<uuid:notification_id>/",
        NotificationView.as_view(),
        name="notification-detail",
    ),
]
