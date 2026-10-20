import hashlib
import hmac
import json
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from . import curlec
from .forms import TokenCodeForm
from .models import Order, Product, TokenCode
from .services import InventoryError, fulfill_payment, start_checkout, verify_callback


@override_settings(
    CURLEC_KEY_ID="test_key", CURLEC_KEY_SECRET="test_secret",
    CURLEC_WEBHOOK_SECRET="test_webhook", TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode(),
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    AXES_ENABLED=False,
)
class GatewayTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("buyer", "buyer@example.com", "test-password")
        self.other = User.objects.create_user("other", "other@example.com", "test-password")
        self.product = Product.objects.create(name="Test token", price_sen=1500)
        self.token = self.make_token("PRIVATE-KEY-ONE")
        self.client.force_login(self.user)

    def make_token(self, code):
        token = TokenCode(product=self.product)
        token.set_code(code)
        token.save()
        return token

    def make_order(self, **kwargs):
        return Order.objects.create(
            user=self.user, product=self.product, product_name=self.product.name,
            amount=1500, token=self.token, provider_order_id="order_test",
            status=Order.Status.PENDING, **kwargs,
        )

    def remote(self, order):
        return {"id": "order_test", "receipt": str(order.pk), "amount": 1500, "currency": "MYR"}

    def payment(self, **kwargs):
        return {
            "id": "pay_test", "order_id": "order_test", "amount": 1500,
            "currency": "MYR", "status": "captured", "captured": True,
            "amount_refunded": 0, **kwargs,
        }

    def test_token_encrypted_and_duplicate_rejected(self):
        self.assertNotIn("PRIVATE-KEY-ONE", self.token.encrypted_code)
        self.assertEqual(self.token.code, "PRIVATE-KEY-ONE")
        form = TokenCodeForm(data={"product": self.product.pk, "token_key": " PRIVATE-KEY-ONE "})
        self.assertFalse(form.is_valid())
        self.assertIn("token_key", form.errors)

    def test_checkout_uses_server_price_and_reuses_reserved_order(self):
        def create(order):
            return self.remote(order)
        with patch("shop.curlec.create_order", side_effect=create) as api:
            first = self.client.post("/api/checkout/", json.dumps({
                "product_id": self.product.pk, "amount": 1, "user_id": self.other.pk,
            }), content_type="application/json")
            second = self.client.post("/api/checkout/", json.dumps({
                "product_id": self.product.pk,
            }), content_type="application/json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["checkout"]["amount"], 1500)
        self.assertTrue(first.json()["checkout"]["redirect"])
        self.assertEqual(first.json(), second.json())
        self.assertEqual(api.call_count, 1)
        self.assertEqual(Order.objects.get().user, self.user)
        self.assertNotIn("test_secret", first.content.decode())

    def test_reserved_token_cannot_be_sold_twice(self):
        self.make_order()
        with self.assertRaises(InventoryError):
            start_checkout(self.other, self.product.pk)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Order.objects.create(user=self.other, product=self.product, product_name="Other", token=self.token, amount=1500)

    def test_timeout_reserves_code_and_prevents_duplicate_provider_orders(self):
        with patch("shop.curlec.create_order", side_effect=curlec.PaymentError("Timeout")) as api:
            with self.assertRaises(curlec.PaymentError):
                start_checkout(self.user, self.product.pk)
            with self.assertRaises(InventoryError):
                start_checkout(self.user, self.product.pk)
        self.assertEqual(api.call_count, 1)
        self.assertEqual(Order.objects.get().status, Order.Status.REVIEW)
        self.assertEqual(Order.objects.get().token, self.token)

    def test_paid_confirmation_is_idempotent(self):
        order = self.make_order()
        with patch("shop.curlec.fetch_payment", return_value=self.payment()), patch("shop.curlec.fetch_order", return_value=self.remote(order)):
            first = fulfill_payment("pay_test")
            again = fulfill_payment("pay_test")
        self.assertEqual(first.paid_at, again.paid_at)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(again.status, Order.Status.PAID)
        status = self.client.get(reverse("order-status", args=[order.pk]))
        self.assertEqual(status.json()["token_code"], "PRIVATE-KEY-ONE")
        self.assertIn("no-store", status["Cache-Control"])

    def test_authorized_payment_does_not_deliver(self):
        order = self.make_order()
        with patch("shop.curlec.fetch_payment", return_value=self.payment(status="authorized", captured=False)), patch("shop.curlec.fetch_order", return_value=self.remote(order)):
            result = fulfill_payment("pay_test")
        self.assertEqual(result.status, Order.Status.PENDING)
        self.assertNotIn("token_code", self.client.get(reverse("order-status", args=[order.pk])).json())

    def test_wrong_amount_currency_and_refund_rejected(self):
        order = self.make_order()
        for change in ({"amount": 1}, {"currency": "USD"}, {"amount_refunded": 1500}):
            with self.subTest(change=change), patch("shop.curlec.fetch_payment", return_value=self.payment(**change)), patch("shop.curlec.fetch_order", return_value=self.remote(order)):
                with self.assertRaises(curlec.PaymentError):
                    fulfill_payment("pay_test")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)

    def test_callback_signature_and_owner_protection(self):
        order = self.make_order()
        with patch("shop.curlec.fetch_payment") as fetch:
            bad = self.client.post(reverse("callback", args=[order.pk]), {
                "razorpay_payment_id": "pay_test", "razorpay_signature": "0" * 64,
            })
        self.assertEqual(bad.status_code, 400)
        fetch.assert_not_called()
        signature = hmac.new(b"test_secret", b"order_test|pay_test", hashlib.sha256).hexdigest()
        # Public callback accepts a provider-authenticated POST without a session or CSRF.
        with patch("shop.curlec.fetch_payment", return_value=self.payment()), patch("shop.curlec.fetch_order", return_value=self.remote(order)):
            good = Client(enforce_csrf_checks=True).post(reverse("callback", args=[order.pk]), {
                "razorpay_payment_id": "pay_test", "razorpay_signature": signature,
            })
        self.assertEqual(good.status_code, 302)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("purchase", args=[order.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("order-status", args=[order.pk])).status_code, 404)

    def test_cannot_verify_another_orders_payment(self):
        order = self.make_order()
        other_token = self.make_token("PRIVATE-KEY-TWO")
        other_order = Order.objects.create(
            user=self.other, product=self.product, product_name="Other",
            amount=1500, token=other_token, provider_order_id="order_other",
        )
        signature = hmac.new(b"test_secret", b"order_other|pay_test", hashlib.sha256).hexdigest()
        with patch("shop.curlec.fetch_payment", return_value=self.payment()), patch("shop.curlec.fetch_order", return_value=self.remote(order)):
            with self.assertRaises(curlec.PaymentError):
                verify_callback(other_order, "pay_test", signature)

    def test_webhook_validates_raw_bytes_and_duplicates_are_safe(self):
        order = self.make_order()
        payload = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_test"}}}})
        signature = hmac.new(b"test_webhook", payload.encode(), hashlib.sha256).hexdigest()
        with patch("shop.curlec.fetch_payment", return_value=self.payment()) as api, patch("shop.curlec.fetch_order", return_value=self.remote(order)):
            bad = self.client.post("/api/curlec/webhook/", payload, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE="0" * 64)
            api.assert_not_called()
            first = self.client.post("/api/curlec/webhook/", payload, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=signature)
            again = self.client.post("/api/curlec/webhook/", payload, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=signature)
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(Order.objects.get().status, Order.Status.PAID)

    def test_webhook_retries_provider_failure(self):
        self.make_order()
        raw = json.dumps({"event": "order.paid", "payload": {"payment": {"entity": {"id": "pay_test"}}}})
        signature = hmac.new(b"test_webhook", raw.encode(), hashlib.sha256).hexdigest()
        with patch("shop.curlec.fetch_payment", side_effect=curlec.PaymentError("Unavailable")):
            response = self.client.post("/api/curlec/webhook/", raw, content_type="application/json", HTTP_X_RAZORPAY_SIGNATURE=signature)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(Order.objects.get().status, Order.Status.PENDING)

    def test_webhook_recovers_ambiguous_create_via_receipt(self):
        order = self.make_order()
        order.provider_order_id = None
        order.status = Order.Status.REVIEW
        order.save()
        with patch("shop.curlec.fetch_payment", return_value=self.payment()), patch("shop.curlec.fetch_order", return_value=self.remote(order)):
            delivered = fulfill_payment("pay_test")
        self.assertEqual(delivered.provider_order_id, "order_test")
        self.assertEqual(delivered.status, Order.Status.PAID)

    def test_webhook_before_create_response_does_not_downgrade_paid_order(self):
        def create(order):
            remote = self.remote(order)
            with patch("shop.curlec.fetch_payment", return_value=self.payment()), patch("shop.curlec.fetch_order", return_value=remote):
                fulfill_payment("pay_test")
            return remote
        with patch("shop.curlec.create_order", side_effect=create):
            order = start_checkout(self.user, self.product.pk)
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.token.code, "PRIVATE-KEY-ONE")

    def test_resume_after_last_code_reserved_or_product_disabled(self):
        order = self.make_order()
        self.product.active = False
        self.product.save()
        response = self.client.post(reverse("resume-checkout", args=[order.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["checkout"]["order_id"], "order_test")
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse("resume-checkout", args=[order.pk])).status_code, 404)

    def test_checkout_requires_login_csrf_and_configuration(self):
        anonymous = Client()
        self.assertEqual(anonymous.post("/api/checkout/").status_code, 401)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.user)
        self.assertEqual(csrf.post("/api/checkout/", "{}" , content_type="application/json").status_code, 403)
        with override_settings(CURLEC_KEY_SECRET=""):
            response = self.client.post("/api/checkout/", json.dumps({"product_id": self.product.pk}), content_type="application/json")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(Order.objects.count(), 0)

    def test_malformed_checkout_and_untrusted_receipt(self):
        for payload in ("[]", "null", "not json", '{"product_id":true}'):
            self.assertEqual(self.client.post("/api/checkout/", payload, content_type="application/json").status_code, 400)
        with patch("shop.curlec.fetch_payment", return_value=self.payment()), patch("shop.curlec.fetch_order", return_value={"id": "order_test", "receipt": "not-a-uuid"}):
            with self.assertRaises(curlec.PaymentError):
                fulfill_payment("pay_test")

    def test_admin_inventory_add_and_reveal_requires_staff(self):
        self.assertEqual(self.client.get("/admin/shop/tokencode/add/").status_code, 302)
        staff = User.objects.create_superuser("owner", "owner@example.com", "test-password")
        self.client.force_login(staff)
        response = self.client.post("/admin/shop/tokencode/add/", {
            "product": self.product.pk, "label": "Batch 1", "token_key": "ADMIN-UPLOADED-KEY",
        })
        self.assertEqual(response.status_code, 302)
        token = TokenCode.objects.get(label="Batch 1")
        self.assertNotIn("ADMIN-UPLOADED-KEY", token.encrypted_code)
        page = self.client.get(f"/admin/shop/tokencode/{token.pk}/change/")
        self.assertContains(page, "ADMIN-UPLOADED-KEY")

    def test_paid_and_pending_pages_never_leak_other_codes(self):
        order = self.make_order()
        self.assertNotContains(self.client.get(reverse("purchase", args=[order.pk])), "PRIVATE-KEY-ONE")
        self.assertNotContains(self.client.get("/"), "PRIVATE-KEY-ONE")
        order.status = Order.Status.PAID
        order.payment_id = "pay_test"
        order.save()
        self.assertContains(self.client.get(reverse("purchase", args=[order.pk])), "PRIVATE-KEY-ONE")

    @override_settings(AXES_ENABLED=True)
    def test_registration_login_logout_and_staff_escalation_rejected(self):
        browser = Client()
        response = browser.post("/accounts/signup/", {
            "username": "newbuyer", "email": "newbuyer@example.com",
            "password1": "Long-test-only-password!731",
            "password2": "Long-test-only-password!731",
            "is_staff": "true", "is_superuser": "true",
        })
        self.assertRedirects(response, "/accounts/login/")
        user = User.objects.get(username="newbuyer")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        logged_in = browser.post("/accounts/login/", {
            "username": "newbuyer", "password": "Long-test-only-password!731",
        })
        self.assertEqual(logged_in.status_code, 302)
        self.assertEqual(browser.get("/purchases/").status_code, 200)
        self.assertEqual(browser.get("/admin/").status_code, 302)
        browser.post("/accounts/logout/")
        self.assertEqual(browser.get("/purchases/").status_code, 302)
