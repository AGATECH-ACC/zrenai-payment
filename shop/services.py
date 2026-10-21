from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from . import curlec
from .models import Order, Product, TokenCode


class InventoryError(Exception):
    pass


def validate_provider_order(order, remote):
    if (
        remote.get("receipt") != str(order.pk)
        or remote.get("amount") != order.amount
        or remote.get("currency") != order.currency
        or not isinstance(remote.get("id"), str)
        or not remote["id"].startswith("order_")
        or (order.provider_order_id and order.provider_order_id != remote["id"])
    ):
        raise curlec.PaymentError("支付平台订单与当前订单不一致。")


def start_checkout(user, product_id):
    curlec.require_keys()
    # PostgreSQL row locks serialize each user's outstanding-order check and
    # each product's stock allocation. SQLite uses BEGIN IMMEDIATE locally.
    # All reservation paths acquire locks in user -> product -> token order.
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=user.pk)
        product = Product.objects.select_for_update().get(pk=product_id, active=True)
        existing = Order.objects.filter(user=user, product=product).exclude(status=Order.Status.PAID).first()
        if existing:
            if existing.provider_order_id and existing.status == Order.Status.PENDING:
                return existing
            raise InventoryError("上一笔支付正在核对中，请查看购买记录或联系店主。")
        if Order.objects.filter(user=user).exclude(status=Order.Status.PAID).count() >= 3:
            raise InventoryError("请先完成已有订单，再发起新的购买。")
        token = TokenCode.objects.filter(product=product, order__isnull=True).select_for_update(
            of=("self",),
        ).order_by("pk").first()
        if token is None:
            raise InventoryError("此套餐已售罄。")
        order = Order.objects.create(
            user=user, product=product, product_name=product.name,
            token=token, amount=product.price_sen,
        )
    try:
        remote = curlec.create_order(order)
        validate_provider_order(order, remote)
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order.pk)
            validate_provider_order(order, remote)
            order.provider_order_id = remote["id"]
            # A webhook may have delivered the token before the create response arrived.
            if order.status != Order.Status.PAID:
                order.status = Order.Status.PENDING
            order.save(update_fields=["provider_order_id", "status"])
        return order
    except curlec.PaymentError:
        # Timeouts can mean an order was created remotely. Never recycle its code
        # or create another payable order until it has been reconciled.
        Order.objects.filter(pk=order.pk, status=Order.Status.CREATING).update(status=Order.Status.REVIEW)
        raise


def fulfill_payment(payment_id, expected_order=None):
    payment = curlec.fetch_payment(payment_id)
    if payment.get("id") != payment_id:
        raise curlec.PaymentError("支付编号不一致。")
    provider_order_id = payment.get("order_id")
    remote = curlec.fetch_order(provider_order_id)
    try:
        order = Order.objects.get(pk=remote.get("receipt"))
    except (Order.DoesNotExist, ValidationError, ValueError, TypeError):
        raise curlec.PaymentError("找不到该订单。")
    if remote.get("id") != provider_order_id:
        raise curlec.PaymentError("支付平台订单编号不一致。")
    if expected_order and order.pk != expected_order.pk:
        raise curlec.PaymentError("该支付属于其他订单。")
    validate_provider_order(order, remote)
    if (
        payment.get("amount") != order.amount
        or payment.get("currency") != order.currency
        or payment.get("amount_refunded", 0) != 0
    ):
        raise curlec.PaymentError("支付金额或币种与订单不一致。")
    if payment.get("status") != "captured" or payment.get("captured") is not True:
        return order  # Authorization alone must never release a token.
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        validate_provider_order(order, remote)
        if order.status == Order.Status.PAID:
            if order.payment_id != payment_id:
                raise curlec.PaymentError("此订单已关联另一笔支付。")
            return order
        order.provider_order_id = provider_order_id
        order.payment_id = payment_id
        order.status = Order.Status.PAID
        order.paid_at = timezone.now()
        order.save(update_fields=["provider_order_id", "payment_id", "status", "paid_at"])
    return order


def verify_callback(order, payment_id, signature):
    if not order.provider_order_id:
        raise curlec.PaymentError("此订单需要核对支付。")
    message = f"{order.provider_order_id}|{payment_id}".encode()
    if not curlec.valid_signature(message, signature, settings.CURLEC_KEY_SECRET):
        raise curlec.PaymentError("支付签名无效。")
    return fulfill_payment(payment_id, expected_order=order)
