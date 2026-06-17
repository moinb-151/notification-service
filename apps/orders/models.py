import uuid_utils.compat as uuid
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q

User = get_user_model()


def generate_uuid7():
    return uuid.uuid7()


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    sku = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    stock_quantity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(price__gt=0), name="product_price_gt_zero"
            ),
            models.CheckConstraint(
                condition=Q(stock_quantity__gte=0),
                name="product_stock_gte_zero",
            ),
        ]

    def __str__(self):
        return f"{self.sku} - {self.name}"


class OrderStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CONFIRMED = "confirmed", "Confirmed"
    SHIPPED = "shipped", "Shipped"
    DELIVERED = "delivered", "Delivered"
    CANCELLED = "cancelled", "Cancelled"


class Order(models.Model):
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="orders")
    status = models.CharField(
        max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    idempotency_key = models.UUIDField(unique=True)
    metadata = models.JSONField(default=dict)
    placed_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["user", "-placed_at"],
                name="order_user_placed_idx",
            ),
            models.Index(
                fields=["status", "placed_at"],
                name="order_status_placed_idx",
            ),
        ]


class OrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=generate_uuid7, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.RESTRICT)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        indexes = [models.Index(fields=["order", "product"], name="order_product_idx")]
