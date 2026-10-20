from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from shop import curlec
from shop.models import Order
from shop.services import fulfill_payment, validate_provider_order


class Command(BaseCommand):
    help = "Recover a payment or attach an ambiguous remote order after checking it in the Curlec Dashboard."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--payment-id")
        group.add_argument("--provider-order-id")

    def handle(self, *args, **options):
        try:
            if options["payment_id"]:
                order = fulfill_payment(options["payment_id"])
            else:
                remote = curlec.fetch_order(options["provider_order_id"])
                with transaction.atomic():
                    order = Order.objects.get(pk=remote.get("receipt"))
                    validate_provider_order(order, remote)
                    if remote["id"] != options["provider_order_id"]:
                        raise curlec.PaymentError("The order reference does not match.")
                    order.provider_order_id = remote["id"]
                    if order.status != Order.Status.PAID:
                        order.status = Order.Status.PENDING
                    order.save(update_fields=["provider_order_id", "status"])
        except Exception as exc:
            raise CommandError("Could not reconcile. Check the reference, merchant account and local receipt.") from exc
        self.stdout.write(f"Purchase {order.pk}: {order.get_status_display()}")
