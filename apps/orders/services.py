from django.db import transaction

from .models import Product


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
