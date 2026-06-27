from dataclasses import dataclass

from django.db import transaction
from django.db.models import F
from rest_framework.exceptions import ValidationError

from .models import Order, OrderItem, OrderStatus, Product


class ProductService:
    @staticmethod
    @transaction.atomic
    def create_product(validated_data):
        return Product.objects.create(**validated_data)

    @staticmethod
    @transaction.atomic
    def get_product(id):
        try:
            return Product.objects.get(id=id)
        except Product.DoesNotExist:
            return None

    @staticmethod
    @transaction.atomic
    def update_product(id, **validated_data):
        try:
            product = Product.objects.select_for_update().get(id=id)

            for field, value in validated_data.items():
                if hasattr(product, field):
                    setattr(product, field, value)

            product.save()
            return product
        except Product.DoesNotExist:
            return None

    @staticmethod
    @transaction.atomic
    def delete_product(id):
        try:
            product = Product.objects.select_for_update().get(id=id)
            product.is_active = False
            product.save(update_fields=["is_active"])
            return True
        except Product.DoesNotExist:
            return False


@dataclass(frozen=True)
class CreateOrderResult:
    order: Order
    created: bool


class OrderService:
    ALLOWED_TRANSITIONS = {
        OrderStatus.PENDING: [OrderStatus.CONFIRMED, OrderStatus.CANCELLED],
        OrderStatus.CONFIRMED: [
            OrderStatus.SHIPPED,
            OrderStatus.CANCELLED,
        ],
        OrderStatus.SHIPPED: [OrderStatus.DELIVERED],
        OrderStatus.DELIVERED: [],
        OrderStatus.CANCELLED: [],
    }

    @staticmethod
    def fetch_products(items):
        item_ids = [item["product_id"] for item in items]
        products_qs = Product.objects.select_for_update().filter(id__in=item_ids)

        products = list(products_qs)

        if len(products) != len(item_ids):
            raise ValidationError("One or more product is missing")

        return products

    @staticmethod
    def check_availability(items, products_map):
        for item in items:
            product = products_map[item["product_id"]]

            if not product.is_active:
                raise ValidationError(f"Product '{product.name}' is inactive.")

    @staticmethod
    def check_quantity(items, products_map):
        for item in items:
            product = products_map[item["product_id"]]
            quantity = item["quantity"]

            if product.stock_quantity < quantity:
                raise ValidationError(
                    f"Only {product.stock_quantity} units of '{product.name}' are available."
                )

    @staticmethod
    def calculate_total(items, products_map):
        total = 0

        for item in items:
            product = products_map[item["product_id"]]
            total += product.price * item["quantity"]

        return total

    @staticmethod
    def create_order_record(validated_data):
        order = None
        existing_order = Order.objects.filter(
            idempotency_key=validated_data["idempotency_key"]
        ).first()

        if existing_order:
            order = CreateOrderResult(order=existing_order, created=False)
        else:
            new_order = Order.objects.create(**validated_data)
            order = CreateOrderResult(order=new_order, created=True)

        return order

    @staticmethod
    def create_order_items(order, items, products_map):
        order_items = []

        for item in items:
            product = products_map[item["product_id"]]

            order_items.append(
                OrderItem(
                    order=order,
                    product=product,
                    quantity=item["quantity"],
                    unit_price=product.price,
                )
            )

        OrderItem.objects.bulk_create(order_items)

    @staticmethod
    def deduct_quantity(items, products_map):
        modified_products = []
        for item in items:
            product = products_map[item["product_id"]]
            product.stock_quantity -= item["quantity"]
            modified_products.append(product)

        if modified_products:
            Product.objects.bulk_update(modified_products, ["stock_quantity"])

    @staticmethod
    def restore_quantity(order):
        modified_products = []

        for item in order.items.all():
            product = item.product
            product.stock_quantity += item.quantity
            modified_products.append(product)

        if modified_products:
            Product.objects.bulk_update(modified_products, ["stock_quantity"])

    @staticmethod
    @transaction.atomic
    def create_order(validated_data, context):
        items = validated_data.pop("items")
        print(items)
        products = OrderService.fetch_products(items)
        products_map = {product.id: product for product in products}

        OrderService.check_availability(items, products_map)
        OrderService.check_quantity(items, products_map)

        total_amount = OrderService.calculate_total(items, products_map)

        validated_data["idempotency_key"] = context.get("key")
        validated_data["user"] = context.get("user")
        validated_data["total_amount"] = total_amount

        order_record = OrderService.create_order_record(validated_data)
        if not order_record.created:
            return order_record

        OrderService.create_order_items(order_record.order, items, products_map)
        OrderService.deduct_quantity(items, products_map)

        return order_record

    @staticmethod
    def get_orders(user):
        orders = (
            Order.objects.filter(user=user)
            .select_related("user")
            .prefetch_related("items__product")
        )
        return orders

    @staticmethod
    def get_order(id, user):
        try:
            return (
                Order.objects.select_related("user")
                .prefetch_related("items__product")
                .filter(id=id, user=user)
                .first()
            )
        except Order.DoesNotExist:
            return None

    @staticmethod
    def _valid_status_transition(current_status, new_status):
        allowed = OrderService.ALLOWED_TRANSITIONS.get(current_status, [])
        if new_status not in allowed:
            raise ValidationError(
                f"Cannot transition from '{current_status}' to '{new_status}'."
            )

    @staticmethod
    @transaction.atomic
    def update_order(order_id, user, **validated_data):
        try:
            order = (
                Order.objects.select_for_update()
                .select_related("user")
                .prefetch_related("items__product")
                .get(id=order_id, user=user)
            )
            new_status = validated_data.get("status", "")
            if new_status:
                OrderService._valid_status_transition(order.status, new_status)

            for field, value in validated_data.items():
                setattr(order, field, value)

            order.save(update_fields=[key for key in validated_data.keys()])

            return order
        except Order.DoesNotExist:
            return None

    @staticmethod
    @transaction.atomic
    def cancel_order(order_id, user):
        try:
            order = (
                Order.objects.select_for_update()
                .select_related("user")
                .prefetch_related("items__product")
                .get(id=order_id, user=user)
            )

            cancel_status = OrderStatus.CANCELLED

            OrderService._valid_status_transition(order.status, cancel_status)

            OrderService.restore_quantity(order)

            order.status = cancel_status

            order.save(update_fields=["status"])

            return order
        except Order.DoesNotExist:
            return None
