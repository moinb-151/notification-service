from django.urls import path

from .views import (
    OrderCancelView,
    OrderDetailView,
    OrderListCreateView,
    ProductDetailView,
    ProductListCreateView,
)

urlpatterns = [
    path("products/", ProductListCreateView.as_view(), name="list-create-product"),
    path(
        "products/<uuid:product_id>/",
        ProductDetailView.as_view(),
        name="product-details",
    ),
    path("", OrderListCreateView.as_view(), name="list-create-order"),
    path("<uuid:order_id>/", OrderDetailView.as_view(), name="order-details"),
    path("<uuid:order_id>/cancel/", OrderCancelView.as_view(), name="cancel-order"),
]
