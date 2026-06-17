from rest_framework import serializers

from .models import Product


class ProductSerializer(serializers.ModelSerializer):
    stock_quantity = serializers.IntegerField(required=True)

    class Meta:
        model = Product
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]
