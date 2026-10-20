from django import forms
from django.contrib import admin
from django.views.decorators.debug import sensitive_post_parameters
from django.utils.decorators import method_decorator

from .forms import TokenCodeForm
from .models import Order, Product, TokenCode


admin.site.site_header = "ZrenAI · Token administration"
admin.site.site_title = "ZrenAI Admin"
admin.site.index_title = "Products, token inventory and purchases"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "available_codes", "active")
    list_filter = ("active",)

    @admin.display(description="Available codes")
    def available_codes(self, obj):
        return obj.codes.filter(order__isnull=True).count()


@admin.register(TokenCode)
class TokenCodeAdmin(admin.ModelAdmin):
    list_display = ("id", "product", "label", "assignment", "created_at")
    list_filter = ("product",)
    search_fields = ("label", "product__name")

    def get_form(self, request, obj=None, **kwargs):
        kwargs["form"] = TokenCodeForm if obj is None else forms.ModelForm
        return super().get_form(request, obj, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return ("product", "label", "token_key")
        return ("product", "label", "decrypted_token", "assignment", "created_at")

    def get_readonly_fields(self, request, obj=None):
        return self.get_fields(request, obj) if obj else ()

    @admin.display(description="Token key (staff only)")
    def decrypted_token(self, obj):
        return obj.code

    @admin.display(description="Assigned purchase")
    def assignment(self, obj):
        try:
            order = obj.order
            return f"{order.user.username} · {order.get_status_display()} · {order.pk}"
        except Order.DoesNotExist:
            return "Available"

    def has_delete_permission(self, request, obj=None):
        # Never recycle reserved codes. Inventory entries are an audit trail.
        return False

    @method_decorator(sensitive_post_parameters("token_key"))
    def changeform_view(self, request, *args, **kwargs):
        return super().changeform_view(request, *args, **kwargs)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "product_name", "price", "status", "created_at", "paid_at")
    list_filter = ("status", "product")
    search_fields = ("id", "user__username", "provider_order_id", "payment_id")
    readonly_fields = (
        "id", "user", "product", "product_name", "token", "amount", "currency",
        "status", "provider_order_id", "payment_id", "created_at", "paid_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
