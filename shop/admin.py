from django import forms
from django.contrib import admin
from django.views.decorators.debug import sensitive_post_parameters
from django.utils.decorators import method_decorator

from .forms import TokenCodeForm
from .models import Order, Product, TokenCode


admin.site.site_header = "众仁 · 额度管理"
admin.site.site_title = "众仁管理后台"
admin.site.index_title = "套餐、兑换码库存与订单"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "available_codes", "active")
    list_filter = ("active",)

    @admin.display(description="售价（马币）")
    def price(self, obj):
        return obj.price

    @admin.display(description="可用兑换码")
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

    @admin.display(description="兑换码（仅管理员可见）")
    def decrypted_token(self, obj):
        return obj.code

    @admin.display(description="关联订单")
    def assignment(self, obj):
        try:
            order = obj.order
            return f"{order.user.username} · {order.get_status_display()} · {order.pk}"
        except Order.DoesNotExist:
            return "可用"

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

    @admin.display(description="金额（马币）")
    def price(self, obj):
        return obj.price

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# Axes has no bundled Chinese catalog or translated labels for computed columns.
# Retain its handlers, permissions, filters and audit records.
from axes.admin import AccessAttemptAdmin
from axes.models import AccessAttempt


class ChineseAccessAttemptAdmin(AccessAttemptAdmin):
    @admin.display(description="锁定状态")
    def status(self, obj):
        return super().status(obj)

    @admin.display(description="失效时间")
    def expiration(self, obj):
        return super().expiration(obj)

    @admin.action(description="清理过期尝试")
    def cleanup_expired_attempts(self, request, queryset):
        count = self.handler.clean_expired_user_attempts(request=request)
        self.message_user(request, f"已清理 {count} 条过期的登录尝试记录。")


if admin.site.is_registered(AccessAttempt):
    admin.site.unregister(AccessAttempt)
    admin.site.register(AccessAttempt, ChineseAccessAttemptAdmin)
