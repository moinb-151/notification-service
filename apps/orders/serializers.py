from rest_framework import serializers

from ..users.serializers import UserRegistrationSerializer
from .models import Order, OrderItem, OrderStatus, Product
from .services import OrderService, ProductService


class ProductSerializer(serializers.ModelSerializer):
    stock_quantity = serializers.IntegerField(required=True)

    class Meta:
        model = Product
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]


class OrderItemCreateSerializer(serializers.Serializer):
    product_id = serializers.UUIDField(required=True)
    quantity = serializers.IntegerField(required=True)

    def validate_product_id(self, value):
        if value.version != 7:
            raise serializers.ValidationError("product_id must be a UUIDv7.")
        return value

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero")
        return value


class OrderItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer()

    class Meta:
        model = OrderItem
        fields = ["id", "product", "quantity", "unit_price"]
        read_only_fields = ["id"]


class OrderCreateSerializer(serializers.Serializer):
    items = OrderItemCreateSerializer(many=True)
    metadata = serializers.JSONField(required=True)


class OrderSerializer(serializers.ModelSerializer):
    user = UserRegistrationSerializer()
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "user",
            "status",
            "total_amount",
            "items",
            "metadata",
            "placed_at",
            "updated_at",
        ]
        read_only_fields = ["id", "placed_at", "updated_at"]


class OrderUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=OrderStatus.choices, required=False)
    metadata = serializers.JSONField(required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("At least one field must be provided.")

        return attrs
