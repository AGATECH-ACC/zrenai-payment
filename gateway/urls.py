from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path
from shop import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", auth_views.LoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/signup/", views.signup, name="signup"),
    path("", views.store, name="store"),
    path("purchases/", views.purchases, name="purchases"),
    path("purchases/<uuid:order_id>/", views.purchase, name="purchase"),
    path("api/checkout/", views.checkout, name="checkout"),
    path("api/orders/<uuid:order_id>/", views.order_status, name="order-status"),
    path("api/orders/<uuid:order_id>/resume/", views.resume_checkout, name="resume-checkout"),
    path("api/curlec/callback/<uuid:order_id>/", views.callback, name="callback"),
    path("api/curlec/webhook/", views.webhook, name="webhook"),
]
