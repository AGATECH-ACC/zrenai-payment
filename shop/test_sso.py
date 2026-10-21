import secrets
import time
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from .models import AcademyIdentity
from .sso import IdentityError


@override_settings(ACADEMY_SSO_ENABLED=True, ACADEMY_ORIGIN="https://academy.example.com",
                   PAYMENT_SSO_SECRET="test-only-sso-secret-" * 3, AXES_ENABLED=False)
class AcademySSOTests(TestCase):
    def setUp(self):
        self.identity = {"sub": str(uuid4()), "email": "buyer@example.com",
                         "session_handle": "a" * 64, "expires_at": int(time.time()) + 1800}

    def begin(self, next_path="/"):
        response = self.client.get("/accounts/sso/start/", {"next": next_path})
        self.assertEqual(response.status_code, 302)
        parts = urlsplit(response["Location"])
        self.assertEqual(parts.netloc, "academy.example.com")
        self.assertNotIn("verifier", parts.query)
        return parse_qs(parts.query)["state"][0]

    def finish(self, state=None):
        return self.client.get("/accounts/sso/callback/", {
            "state": state or self.begin(), "code": secrets.token_urlsafe(32),
        })

    def test_signed_out_entry_is_login_and_local_signup_disabled(self):
        self.assertEqual(self.client.get("/")["Location"], "/accounts/login/?next=/")
        page = self.client.get("/accounts/login/")
        self.assertContains(page, "使用众仁账号继续")
        self.assertNotContains(page, 'type="password"')
        self.assertEqual(self.client.post("/accounts/signup/", {"username": "intruder"}).status_code, 302)
        self.assertEqual(User.objects.count(), 0)

    @patch("shop.sso.academy_request")
    def test_verified_uuid_creates_customer_not_staff_or_email_link(self, remote):
        staff = User.objects.create_user("admin", email=self.identity["email"], is_staff=True)
        remote.return_value = self.identity
        state = self.begin("/purchases/")
        verifier = self.client.session["academy_pending"]["verifier"]
        response = self.finish(state)
        self.assertEqual(response["Location"], "/purchases/")
        remote.assert_called_once()
        self.assertEqual(remote.call_args.args[1]["verifier"], verifier)
        binding = AcademyIdentity.objects.get(subject=self.identity["sub"])
        self.assertNotEqual(binding.user_id, staff.pk)
        self.assertFalse(binding.user.is_staff)
        self.assertFalse(binding.user.has_usable_password())
        self.assertNotIn("academy_pending", self.client.session)
        self.assertEqual(self.client.get("/purchases/").status_code, 200)
        self.assertEqual(self.client.get("/admin/").status_code, 302)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertContains(self.client.get("/"), "选择您的额度套餐。")

    @patch("shop.sso.academy_request")
    def test_wrong_expired_or_replayed_browser_state_never_exchanges(self, remote):
        state = self.begin()
        self.assertEqual(self.finish("ä").status_code, 400)
        self.assertEqual(self.finish(state).status_code, 400)
        self.begin()
        session = self.client.session
        pending = session["academy_pending"]
        pending["created"] -= 301
        session["academy_pending"] = pending
        session.save()
        self.assertEqual(self.finish(pending["state"]).status_code, 400)
        remote.assert_not_called()

    @patch("shop.sso.academy_request")
    def test_untrusted_return_url_is_not_used(self, remote):
        remote.return_value = self.identity
        state = self.begin("//evil.example")
        self.assertEqual(self.finish(state)["Location"], "/")

    @patch("shop.sso.academy_request")
    def test_academy_logout_revokes_payment_access(self, remote):
        remote.return_value = self.identity
        self.finish()
        remote.side_effect = IdentityError()
        self.assertEqual(self.client.get("/api/orders/" + str(uuid4()) + "/").status_code, 401)
        self.assertNotIn("_auth_user_id", self.client.session)

    @patch("shop.sso.academy_request")
    def test_outage_denies_checkout_without_destroying_session(self, remote):
        remote.return_value = self.identity
        self.finish()
        remote.side_effect = IdentityError(unavailable=True)
        self.assertEqual(self.client.post("/api/checkout/", data='{"product_id":1}', content_type="application/json").status_code, 503)
        self.assertIn("_auth_user_id", self.client.session)

    @patch("shop.sso.academy_request")
    def test_same_uuid_uses_same_customer_and_updated_verified_email(self, remote):
        remote.return_value = self.identity
        self.finish()
        first_id = self.client.session["_auth_user_id"]
        self.client.post("/accounts/logout/")
        self.identity["email"] = "new@example.com"
        self.finish()
        self.assertEqual(first_id, self.client.session["_auth_user_id"])
        self.assertEqual(User.objects.get(pk=first_id).email, "new@example.com")
        self.assertEqual(AcademyIdentity.objects.count(), 1)

    @patch("shop.sso.academy_request")
    def test_new_identity_with_same_email_gets_separate_purchase_history(self, remote):
        remote.return_value = self.identity
        self.finish()
        first_id = self.client.session["_auth_user_id"]
        self.client.post("/accounts/logout/")
        self.identity["sub"] = str(uuid4())
        self.finish()
        self.assertNotEqual(first_id, self.client.session["_auth_user_id"])

    @patch("shop.sso.academy_request")
    def test_staff_binding_cannot_be_used_for_sso(self, remote):
        user = User.objects.create_user("staff", is_staff=True)
        AcademyIdentity.objects.create(user=user, subject=self.identity["sub"])
        remote.return_value = self.identity
        self.assertEqual(self.finish().status_code, 403)
        self.assertNotIn("_auth_user_id", self.client.session)

    @patch("shop.sso.academy_request")
    def test_old_local_customer_session_no_longer_authenticates(self, remote):
        self.client.force_login(User.objects.create_user("legacy"))
        self.assertEqual(self.client.get("/purchases/").status_code, 302)
        remote.assert_not_called()
