from django.contrib.auth.models import Permission, User
from django.test import TestCase, override_settings

from .models import Order, Product, TokenCode


@override_settings(AXES_ENABLED=False, ACADEMY_SSO_ENABLED=False)
class DashboardAccessTests(TestCase):
    def setUp(self):
        self.buyer = User.objects.create_user("buyer")
        self.other = User.objects.create_user("other")
        self.staff = User.objects.create_user("stock-manager", is_staff=True)
        self.product = Product.objects.create(name="Test package", price_sen=1000)
        self.paid = self.order(self.buyer, Order.Status.PAID, 1500)
        self.pending = self.order(self.buyer, Order.Status.REVIEW, 3000)
        self.order(self.other, Order.Status.PAID, 90000)

    def order(self, user, status, amount):
        token = TokenCode(product=self.product)
        token.set_code(f"TEST-ONLY-{user.pk}-{status}")
        token.save()
        return Order.objects.create(
            user=user, product=self.product, product_name=self.product.name,
            token=token, amount=amount, status=status,
        )

    def test_purchase_metrics_and_filters_are_owner_scoped(self):
        self.client.force_login(self.buyer)
        page = self.client.get("/purchases/?status=paid")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["paid_total"], "马币 15.00")
        self.assertEqual(page.context["summary"]["total"], 2)
        self.assertEqual(page.context["summary"]["pending"], 1)
        self.assertEqual(list(page.context["orders"]), [self.paid])
        self.assertNotContains(page, self.pending.pk)
        progress = self.client.get("/purchases/?status=pending")
        self.assertEqual(list(progress.context["orders"]), [self.pending])
        self.assertEqual(progress.context["paid_total"], "马币 15.00")
        self.assertEqual(self.client.get("/purchases/?status=unknown").context["purchase_filter"], "all")

    def test_inventory_staff_cannot_read_purchase_dashboard(self):
        self.staff.user_permissions.add(Permission.objects.get(codename="view_tokencode"))
        self.client.force_login(self.staff)
        page = self.client.get("/admin/")
        self.assertEqual(page.status_code, 200)
        self.assertTrue(page.context["can_view_codes"])
        self.assertFalse(page.context["can_view_orders"])
        self.assertNotIn("paid_total", page.context)
        self.assertNotIn("recent_orders", page.context)
        self.assertNotContains(page, "马币 945.00")
        self.assertNotContains(page, '/admin/shop/product/add/')
        self.assertEqual(self.client.get("/admin/shop/order/").status_code, 403)

    def test_order_viewer_sees_only_confirmed_sum_without_inventory_access(self):
        self.staff.user_permissions.add(Permission.objects.get(codename="view_order"))
        self.client.force_login(self.staff)
        page = self.client.get("/admin/")
        self.assertEqual(page.context["paid_total"], "马币 915.00")
        self.assertEqual(page.context["order_totals"]["pending"], 1)
        self.assertFalse(page.context["can_view_codes"])
        self.assertNotContains(page, '/admin/shop/tokencode/add/')

    def test_customer_cannot_open_admin_dashboard(self):
        self.client.force_login(self.buyer)
        self.assertEqual(self.client.get("/admin/").status_code, 302)
        denied = self.client.get("/admin/login/")
        self.assertNotContains(denied, self.buyer.username)
        self.assertContains(denied, "您已登录客户账号。")
