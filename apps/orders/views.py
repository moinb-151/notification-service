from rest_framework import generics, permissions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Product
from .serializers import (
    OrderCreateSerializer,
    OrderSerializer,
    OrderUpdateSerializer,
    ProductSerializer,
)
from .services import OrderService, ProductService


class ProductListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProductSerializer
    queryset = Product.objects.filter(is_active=True)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product = ProductService.create_product(serializer.validated_data)

        return Response(
            ProductSerializer(product).data,
            status=status.HTTP_201_CREATED,
        )


class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProductSerializer
    queryset = Product.objects.filter(is_active=True)
    lookup_field = "id"
    lookup_url_kwarg = "product_id"

    def update(self, request, *args, **kwargs):
        product_id = kwargs["product_id"]

        serializer = self.get_serializer(
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)

        product = ProductService.update_product(
            product_id,
            **serializer.validated_data,
        )

        if product is None:
            return Response(
                {"detail": "Product not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            ProductSerializer(product).data,
            status=status.HTTP_200_OK,
        )

    def destroy(self, request, *args, **kwargs):
        product_id = kwargs["product_id"]

        is_deleted = ProductService.delete_product(product_id)

        if not is_deleted:
            return Response(
                {"detail": "Product not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


class OrderListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        idempotency_key = request.headers.get("Idempotency-Key")

        if not idempotency_key:
            return Response(
                {"detail": "Idempotency-Key should be provided in headers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        context = {"key": idempotency_key, "user": request.user}

        order_result = OrderService.create_order(serializer.validated_data, context)

        order_data = OrderSerializer(order_result.order).data

        return_status = (
            status.HTTP_201_CREATED if order_result.created else status.HTTP_200_OK
        )

        return Response(order_data, status=return_status)

    def get(self, request):
        orders = OrderService.get_orders(request.user)
        paginator = PageNumberPagination()

        paginated_orders = paginator.paginate_queryset(orders, request)
        serializer = OrderSerializer(paginated_orders, many=True)

        return paginator.get_paginated_response(serializer.data)


class OrderDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, order_id):
        order = OrderService.get_order(order_id, request.user)

        if not order:
            return Response(
                {"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND
            )

        order_data = OrderSerializer(order).data

        return Response(order_data, status=status.HTTP_200_OK)

    def patch(self, request, order_id):
        serializer = OrderUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        order = OrderService.update_order(
            order_id, request.user, **serializer.validated_data
        )

        if not order:
            return Response(
                {"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND
            )

        order_data = OrderSerializer(order).data

        return Response(order_data, status=status.HTTP_200_OK)


class OrderCancelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, order_id):
        order = OrderService.cancel_order(order_id, request.user)

        if not order:
            return Response(
                {"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND
            )

        order_data = OrderSerializer(order).data

        return Response(order_data, status=status.HTTP_200_OK)
