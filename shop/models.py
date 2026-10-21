import hashlib
import uuid
from decimal import Decimal

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class AcademyIdentity(models.Model):
    """Immutable Supabase identity binding, independent of email and staff roles."""
    subject = models.UUIDField(unique=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, verbose_name="用户", on_delete=models.PROTECT, related_name="academy_identity")


class Product(models.Model):
    name = models.CharField(verbose_name="套餐名称", max_length=120)
    description = models.TextField(verbose_name="套餐说明", blank=True)
    price_sen = models.PositiveIntegerField(
        verbose_name="售价（马币分）",
        validators=[MinValueValidator(100)],
        help_text="以马币分填写：1000 表示 10.00 马币，最低为 100（1.00 马币）。",
    )
    active = models.BooleanField(verbose_name="已上架", default=True)

    class Meta:
        verbose_name = "额度套餐"
        verbose_name_plural = "额度套餐"

    @property
    def price(self):
        return Decimal(self.price_sen) / 100

    def __str__(self):
        return self.name


class TokenCode(models.Model):
    product = models.ForeignKey(Product, verbose_name="所属套餐", on_delete=models.PROTECT, related_name="codes")
    label = models.CharField(verbose_name="内部备注", max_length=100, blank=True, help_text="仅用于内部记录，请勿在此填写兑换码。")
    encrypted_code = models.TextField(verbose_name="加密兑换码", editable=False)
    fingerprint = models.CharField(verbose_name="兑换码指纹", max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(verbose_name="创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "兑换码"
        verbose_name_plural = "兑换码库存"

    def set_code(self, value):
        value = value.strip()
        self.encrypted_code = Fernet(settings.TOKEN_ENCRYPTION_KEY.encode()).encrypt(value.encode()).decode()
        self.fingerprint = hashlib.sha256(value.encode()).hexdigest()

    @property
    def code(self):
        return Fernet(settings.TOKEN_ENCRYPTION_KEY.encode()).decrypt(self.encrypted_code.encode()).decode()

    def __str__(self):
        return f"{self.product.name} · {self.label or f'兑换码 #{self.pk}'}"


class Order(models.Model):
    class Status(models.TextChoices):
        CREATING = "creating", "准备支付"
        PENDING = "pending", "等待付款"
        REVIEW = "review", "待核对"
        PAID = "paid", "已交付"

    id = models.UUIDField(verbose_name="订单编号", primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name="用户", on_delete=models.PROTECT)
    product = models.ForeignKey(Product, verbose_name="所属套餐", on_delete=models.PROTECT)
    product_name = models.CharField(verbose_name="购买时套餐名称", max_length=120)
    token = models.OneToOneField(TokenCode, verbose_name="兑换码", on_delete=models.PROTECT, related_name="order")
    amount = models.PositiveIntegerField(verbose_name="金额（马币分）")
    currency = models.CharField(verbose_name="币种", max_length=3, default="MYR")
    status = models.CharField(verbose_name="订单状态", max_length=12, choices=Status.choices, default=Status.CREATING)
    provider_order_id = models.CharField(verbose_name="支付平台订单编号", max_length=100, unique=True, null=True, blank=True)
    payment_id = models.CharField(verbose_name="支付编号", max_length=100, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(verbose_name="创建时间", auto_now_add=True)
    paid_at = models.DateTimeField(verbose_name="支付时间", null=True, blank=True)

    class Meta:
        verbose_name = "订单"
        verbose_name_plural = "订单记录"
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
