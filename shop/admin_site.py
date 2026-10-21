"""Django admin presentation; retain ModelAdmin permissions and querysets."""
from decimal import Decimal

from django.contrib.admin import AdminSite
from django.contrib.admin.apps import AdminConfig
from django.db.models import Count, Q, Sum


class PaymentAdminConfig(AdminConfig):
    default_site = "shop.admin_site.PaymentAdminSite"


class PaymentAdminSite(AdminSite):
    index_template = "admin/payment_index.html"

    def get_app_list(self, request, app_label=None):
        apps = super().get_app_list(request, app_label)
        for app in apps:
            if app["app_label"] == "axes":
                app["name"] = "登录安全"
        return sorted(apps, key=lambda app: (app["app_label"] != "shop", app["name"]))

    def index(self, request, extra_context=None):
        from .models import Order, Product, TokenCode

        context = {"title": "商店概览"}
        for model, key in ((Order, "orders"), (Product, "products"), (TokenCode, "codes")):
            model_admin = self._registry[model]
            allowed = model_admin.has_view_or_change_permission(request)
            context[f"can_view_{key}"] = allowed
            if not allowed:
                continue
            rows = model_admin.get_queryset(request)
            if model is Order:
                totals = rows.aggregate(
                    paid=Count("pk", filter=Q(status=Order.Status.PAID)),
                    pending=Count("pk", filter=~Q(status=Order.Status.PAID)),
                    paid_sen=Sum("amount", filter=Q(status=Order.Status.PAID)),
                )
                context.update(
                    order_totals=totals,
                    paid_total=f"马币 {Decimal(totals['paid_sen'] or 0) / 100:,.2f}",
                    recent_orders=rows[:6],
                )
            elif model is Product:
                context.update(active_products=rows.filter(active=True).count(), total_products=rows.count())
            else:
                context.update(
                    available_codes=rows.filter(order__isnull=True).count(),
                    assigned_codes=rows.filter(order__isnull=False).count(),
                )
        return super().index(request, extra_context={**context, **(extra_context or {})})
