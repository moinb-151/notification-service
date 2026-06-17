from django.urls import path

from .views import ProductListCreateView, ProductRetrieveUpdateDestroyView

urlpatterns = [
    path("products/", ProductListCreateView.as_view(), name="list-create-product"),
    path(
        "products/<uuid:product_id>/",
        ProductRetrieveUpdateDestroyView.as_view(),
        name="product-detail-view",
    ),
    # path("products/list/", ProductListView.as_view(), name="list-product"),
]
