"""Academy session handoff: authorization code + S256 PKCE + browser state."""
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from urllib.parse import urlencode
from uuid import UUID

import httpx
from django.conf import settings
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET

from .models import AcademyIdentity


class IdentityError(Exception):
    def __init__(self, unavailable=False):
        self.unavailable = unavailable


def academy_request(path, data):
    body = json.dumps(data, sort_keys=True, separators=(",", ":"))
    timestamp = str(int(time.time()))
    signature = hmac.new(
        settings.PAYMENT_SSO_SECRET.encode(),
        (timestamp + "\n" + path + "\n" + body).encode(), hashlib.sha256,
    ).hexdigest()
    try:
        response = httpx.post(settings.ACADEMY_ORIGIN + path, content=body, headers={
            "Content-Type": "application/json", "X-ZrenAI-Time": timestamp,
            "X-ZrenAI-Signature": signature,
        }, timeout=15, follow_redirects=False)
        if response.status_code != 200:
            raise IdentityError(unavailable=response.status_code >= 500 or response.status_code == 429)
        data = response.json()
        subject = str(UUID(data["sub"]))
        if (not isinstance(data["email"], str) or "@" not in data["email"] or
                len(data["email"]) > 254 or not re.fullmatch(r"[0-9a-f]{64}", data["session_handle"]) or
                not isinstance(data["expires_at"], int) or data["expires_at"] <= time.time()):
            raise ValueError
        return {**data, "sub": subject}
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise IdentityError(unavailable=True) from None


def safe_next(value):
    return value if value and value.startswith("/") and url_has_allowed_host_and_scheme(
        value, allowed_hosts=set(), require_https=True,
    ) else "/"


def login_page(request):
    if not settings.ACADEMY_SSO_ENABLED:
        return LoginView.as_view(template_name="registration/local_login.html")(request)
    if request.user.is_authenticated:
        return redirect("store")
    return render(request, "registration/login.html", {"next": safe_next(request.GET.get("next"))})


@require_GET
def start(request):
    if not settings.ACADEMY_SSO_ENABLED:
        return redirect("login")
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    request.session["academy_pending"] = {
        "state": state, "verifier": verifier, "created": time.time(),
        "next": safe_next(request.GET.get("next")),
    }
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return redirect(settings.ACADEMY_ORIGIN + "/payments/authorize?" + urlencode({
        "state": state, "challenge": challenge,
    }))


@require_GET
def callback(request):
    if not settings.ACADEMY_SSO_ENABLED:
        return HttpResponse("学院登录暂不可用。", status=503)
    pending = request.session.pop("academy_pending", None)
    state, code = request.GET.get("state", ""), request.GET.get("code", "")
    if (not pending or time.time() - pending.get("created", 0) > 300 or
            not re.fullmatch(r"[A-Za-z0-9_-]{43}", state) or
            not hmac.compare_digest(state, pending.get("state", "")) or
            not re.fullmatch(r"[A-Za-z0-9_-]{43}", code)):
        return render(request, "registration/sso_error.html", status=400)
    try:
        identity = academy_request("/api/payment-sso/exchange", {
            "code": code, "state": state, "verifier": pending["verifier"],
        })
        with transaction.atomic():
            binding = AcademyIdentity.objects.select_related("user").filter(subject=identity["sub"]).first()
            if binding:
                user = binding.user
            else:
                # Namespaced UUID, never link to an existing account by email.
                user, created = get_user_model().objects.get_or_create(
                    username="academy_" + identity["sub"],
                    defaults={"email": identity["email"]},
                )
                if not created:
                    raise IdentityError()
                user.set_unusable_password()
                user.save(update_fields=["password"])
                AcademyIdentity.objects.create(subject=identity["sub"], user=user)
            if not user.is_active or user.is_staff or user.is_superuser:
                raise IdentityError()
            if user.email != identity["email"]:
                user.email = identity["email"]
                user.save(update_fields=["email"])
        # Rotate the Django session ID; roles remain local and are never imported.
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        request.session["academy"] = {
            "sub": identity["sub"], "session_handle": identity["session_handle"],
            "expires_at": identity["expires_at"],
        }
        request.session.set_expiry(min(identity["expires_at"] - int(time.time()), 3600))
        response = redirect(pending["next"])
        response["Referrer-Policy"] = "no-referrer"
        return response
    except IdentityError as error:
        return render(request, "registration/sso_error.html", status=503 if error.unavailable else 403)


class AcademySessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.academy_sso_enabled = settings.ACADEMY_SSO_ENABLED
        request.academy_origin = settings.ACADEMY_ORIGIN
        # Admin uses its own existing login. Provider callbacks authenticate by HMAC.
        excluded = request.path.startswith(("/admin/", "/api/curlec/", "/accounts/sso/", "/static/"))
        if (settings.ACADEMY_SSO_ENABLED and request.user.is_authenticated and
                not request.user.is_staff and not excluded and request.path != "/accounts/logout/"):
            session = request.session.get("academy")
            try:
                if not session or session.get("expires_at", 0) <= time.time():
                    raise IdentityError()
                identity = academy_request("/api/payment-sso/session", {"session_handle": session["session_handle"]})
                if (identity["sub"] != session["sub"] or identity["session_handle"] != session["session_handle"] or
                        not AcademyIdentity.objects.filter(user=request.user, subject=identity["sub"]).exists()):
                    raise IdentityError()
                # Email is verified by Supabase, not supplied by a URL or user metadata.
                if request.user.email != identity["email"]:
                    request.user.email = identity["email"]
                    request.user.save(update_fields=["email"])
            except IdentityError as error:
                if error.unavailable:
                    return JsonResponse({"error": "众仁登录暂不可用，请重试。"}, status=503)
                logout(request)
                if request.path.startswith("/api/"):
                    return JsonResponse({"error": "您的众仁登录状态已过期，请重新登录。"}, status=401)
                return redirect(reverse("login") + "?" + urlencode({"next": request.get_full_path()}))
        return self.get_response(request)
