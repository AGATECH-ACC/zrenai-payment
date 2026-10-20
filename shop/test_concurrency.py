from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.db import connection, connections
from django.test import TransactionTestCase, override_settings

from .models import Order, Product, TokenCode
from .services import InventoryError, fulfill_payment, start_checkout


@skipUnless(connection.vendor == "postgresql", "Requires a PostgreSQL test database")
@override_settings(
    CURLEC_KEY_ID="test", CURLEC_KEY_SECRET="test",
    TOKEN_ENCRYPTION_KEY=Fernet.generate_key().decode(),
)
class PostgreSQLConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.product = Product.objects.create(name="Concurrent token", price_sen=100)
        self.token = TokenCode(product=self.product)
        self.token.set_code("DISPOSABLE-POSTGRES-TEST-CODE")
        self.token.save()
        self.buyers = [User.objects.create_user(username=f"buyer-{i}") for i in range(2)]

    def remote(self, order):
        return {
            "id": "order_" + order.pk.hex, "receipt": str(order.pk),
            "amount": order.amount, "currency": order.currency,
        }

    def run_parallel(self, operation, values):
        barrier = Barrier(len(values))

        def worker(value):
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                return operation(value)
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=len(values)) as executor:
            return list(executor.map(worker, values))

    def buy(self, user_id):
        try:
            return start_checkout(User.objects.get(pk=user_id), self.product.pk)
        except InventoryError:
            return None

    def test_two_buyers_competing_for_last_code(self):
        with patch("shop.curlec.create_order", side_effect=self.remote) as api:
            results = self.run_parallel(self.buy, [user.pk for user in self.buyers])
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(api.call_count, 1)

    def test_same_buyer_cannot_create_two_remote_orders(self):
        with patch("shop.curlec.create_order", side_effect=self.remote) as api:
            self.run_parallel(self.buy, [self.buyers[0].pk, self.buyers[0].pk])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(api.call_count, 1)

    def test_simultaneous_webhooks_preserve_one_delivery_timestamp(self):
        order = Order.objects.create(
            user=self.buyers[0], product=self.product, product_name=self.product.name,
            token=self.token, amount=100, status=Order.Status.PENDING,
        )
        remote = self.remote(order)
        order.provider_order_id = remote["id"]
        order.save()
        payment = {
            "id": "pay_parallel", "order_id": remote["id"],
            "amount": 100, "currency": "MYR", "status": "captured",
            "captured": True, "amount_refunded": 0,
        }
        with patch("shop.curlec.fetch_payment", return_value=payment), patch("shop.curlec.fetch_order", return_value=remote):
            results = self.run_parallel(fulfill_payment, ["pay_parallel", "pay_parallel"])
        self.assertEqual(results[0].paid_at, results[1].paid_at)
        self.assertTrue(all(result.status == Order.Status.PAID for result in results))
        self.assertEqual(Order.objects.count(), 1)
