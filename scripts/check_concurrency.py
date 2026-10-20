"""Exercise real file-backed SQLite reservation contention using disposable data."""
import io
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gateway.settings")

with tempfile.TemporaryDirectory(prefix="zrenai-concurrency-") as directory:
    os.environ["SQLITE_PATH"] = str(Path(directory) / "test.sqlite3")
    import django
    django.setup()
    from django.contrib.auth.models import User
    from django.core.management import call_command
    from django.db import close_old_connections, connections
    from django.test import override_settings
    from shop.models import Order, Product, TokenCode
    from shop.services import InventoryError, start_checkout

    call_command("migrate", verbosity=0, stdout=io.StringIO())
    product = Product.objects.create(name="Concurrency fixture", price_sen=100)
    token = TokenCode(product=product)
    token.set_code("DISPOSABLE-CONCURRENCY-FIXTURE")
    token.save()
    buyers = [User.objects.create_user(username=f"test-{i}") for i in range(2)]
    barrier = Barrier(2)

    def buy(user_id):
        close_old_connections()
        try:
            user = User.objects.get(pk=user_id)
            barrier.wait(timeout=10)
            try:
                return str(start_checkout(user, product.pk).pk)
            except InventoryError:
                return "sold-out"
        finally:
            connections.close_all()

    def remote(order):
        return {
            "id": "order_" + order.pk.hex, "receipt": str(order.pk),
            "amount": order.amount, "currency": order.currency,
        }

    with override_settings(CURLEC_KEY_ID="test", CURLEC_KEY_SECRET="test"), patch("shop.curlec.create_order", side_effect=remote):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(buy, [user.pk for user in buyers]))
    assert results.count("sold-out") == 1, results
    assert Order.objects.count() == 1
    assert Order.objects.get().token_id == token.pk
    connections.close_all()
    print("PASS: simultaneous buyers competing for the last code create exactly one order.")
