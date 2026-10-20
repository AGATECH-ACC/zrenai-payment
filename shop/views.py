import json
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from . import curlec
from .forms import SignupForm
from .models import Order, Product
from .services import InventoryError, fulfill_payment, start_checkout, verify_callback


def api_login_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Please log in to continue."}, status=401)
        return view(request, *args, **kwargs)
    return wrapped


@sensitive_post_parameters("password1", "password2")
@require_http_methods(["GET", "POST"])
def signup(request):
    if settings.ACADEMY_SSO_ENABLED:
        return redirect("login")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Account created. Log in to buy your first token code.")
        return redirect("login")
    return render(request, "registration/signup.html", {"form": form})


@login_required
@require_GET
def store(request):
    products = Product.objects.filter(active=True).annotate(
        available=Count("codes", filter=Q(codes__order__isnull=True)),
    ).order_by("price_sen", "pk")
    return render(request, "shop/store.html", {
        "products": products,
        "payments_ready": bool(settings.CURLEC_KEY_ID and settings.CURLEC_KEY_SECRET),
    })


@login_required
@require_GET
def purchases(request):
    return render(request, "shop/purchases.html", {"orders": Order.objects.filter(user=request.user)})


@login_required
@require_GET
def purchase(request, order_id):
    order = get_object_or_404(Order.objects.select_related("token"), pk=order_id, user=request.user)
    return render(request, "shop/purchase.html", {
        "order": order, "token_code": order.token.code if order.status == Order.Status.PAID else None,
    })


@api_login_required
@require_POST
def checkout(request):
    try:
        payload = json.loads(request.body)
        if not isinstance(payload, dict) or type(payload.get("product_id")) is not int:
            raise ValueError
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "A valid product_id is required."}, status=400)
    try:
        order = start_checkout(request.user, payload["product_id"])
    except Product.DoesNotExist:
        return JsonResponse({"error": "Product not found."}, status=404)
    except InventoryError as exc:
        return JsonResponse({"error": str(exc)}, status=409)
    except curlec.PaymentError as exc:
        return JsonResponse({"error": str(exc)}, status=503)
    return checkout_response(order, request.user)


def checkout_response(order, user):
    if order.status == Order.Status.PAID:
        return JsonResponse({"purchase_url": reverse("purchase", args=[order.pk])})
    return JsonResponse({
        "local_order_id": str(order.pk),
        "purchase_url": reverse("purchase", args=[order.pk]),
        "checkout": {
            "key": settings.CURLEC_KEY_ID, "order_id": order.provider_order_id,
            "amount": order.amount, "currency": order.currency, "name": "ZrenAI",
            "description": order.product_name,
            "callback_url": settings.APP_BASE_URL + reverse("callback", args=[order.pk]),
            "redirect": True,
            "prefill": {"email": user.email},
            "theme": {"color": "#176b56"},
        },
    })


@api_login_required
@require_POST
def resume_checkout(request, order_id):
    order = get_object_or_404(Order, pk=order_id, user=request.user)
    if order.status == Order.Status.PAID:
        return checkout_response(order, request.user)
    try:
        curlec.require_keys()
    except curlec.ConfigurationError as exc:
        return JsonResponse({"error": str(exc)}, status=503)
    if order.status != Order.Status.PENDING or not order.provider_order_id:
        return JsonResponse({"error": "This purchase needs a payment check. Please contact the store."}, status=409)
    return checkout_response(order, request.user)


@api_login_required
@require_GET
def order_status(request, order_id):
    order = get_object_or_404(Order.objects.select_related("token"), pk=order_id, user=request.user)
    result = {"id": str(order.pk), "status": order.status, "product": order.product_name}
    if order.status == Order.Status.PAID:
        result["token_code"] = order.token.code
    return JsonResponse(result)


@csrf_exempt
@require_POST
def callback(request, order_id):
    # Provider redirect POSTs cannot carry our CSRF token or same-site session.
    # Authenticate via HMAC and redirect to the owner-protected purchase page.
    order = get_object_or_404(Order, pk=order_id)
    try:
        verify_callback(
            order, request.POST.get("razorpay_payment_id", ""),
            request.POST.get("razorpay_signature", ""),
        )
    except curlec.PaymentError:
        return HttpResponse(
            "Payment could not yet be verified. Open My purchases after logging in. "
            "Do not pay again; the store can check the payment reference.",
            status=400, content_type="text/plain",
        )
    return redirect("purchase", order_id=order.pk)


@csrf_exempt
@require_POST
def webhook(request):
    if not settings.CURLEC_WEBHOOK_SECRET:
        return JsonResponse({"error": "Webhook is not configured."}, status=503)
    raw_body = request.body
    if not curlec.valid_signature(
        raw_body, request.headers.get("X-Razorpay-Signature", ""),
        settings.CURLEC_WEBHOOK_SECRET,
    ):
        return JsonResponse({"error": "Invalid signature."}, status=400)
    try:
        event = json.loads(raw_body)
        if not isinstance(event, dict):
            raise ValueError
        if event.get("event") not in ("payment.captured", "order.paid"):
            return JsonResponse({"received": True})
        payment_id = event["payload"]["payment"]["entity"]["id"]
        if not isinstance(payment_id, str):
            raise ValueError
    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid event payload."}, status=400)
    try:
        # Fetch authoritative state; payloads can be stale or arrive out of order.
        # The unique payment and token constraints make callback/webhook retries idempotent.
        fulfill_payment(payment_id)
    except curlec.PaymentError:
        return JsonResponse({"error": "Payment reconciliation pending."}, status=503)
    return JsonResponse({"received": True})
