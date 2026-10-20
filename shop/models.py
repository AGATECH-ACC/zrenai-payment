import hashlib
import uuid
from decimal import Decimal

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Product(models.Model):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    price_sen = models.PositiveIntegerField(
        validators=[MinValueValidator(100)],
        help_text="MYR in sen: 1000 = RM 10.00. Minimum RM 1.00.",
    )
    active = models.BooleanField(default=True)

    @property
    def price(self):
        return Decimal(self.price_sen) / 100

    def __str__(self):
        return self.name


class TokenCode(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="codes")
    label = models.CharField(max_length=100, blank=True, help_text="Internal reference; do not put the token key here.")
    encrypted_code = models.TextField(editable=False)
    fingerprint = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def set_code(self, value):
        value = value.strip()
        self.encrypted_code = Fernet(settings.TOKEN_ENCRYPTION_KEY.encode()).encrypt(value.encode()).decode()
        self.fingerprint = hashlib.sha256(value.encode()).hexdigest()

    @property
    def code(self):
        return Fernet(settings.TOKEN_ENCRYPTION_KEY.encode()).decrypt(self.encrypted_code.encode()).decode()

    def __str__(self):
        return f"{self.product.name} · {self.label or f'Code #{self.pk}'}"


class Order(models.Model):
    class Status(models.TextChoices):
        CREATING = "creating", "Preparing checkout"
        PENDING = "pending", "Awaiting payment"
        REVIEW = "review", "Needs reconciliation"
        PAID = "paid", "Delivered"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    product_name = models.CharField(max_length=120)
    token = models.OneToOneField(TokenCode, on_delete=models.PROTECT, related_name="order")
    amount = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, default="MYR")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.CREATING)
    provider_order_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    payment_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"],
                condition=~models.Q(status="paid"),
                name="one_unpaid_checkout_per_product",
            ),
        ]
        ordering = ["-created_at"]

    @property
    def price(self):
        return Decimal(self.amount) / 100

    def __str__(self):
        return str(self.id)
