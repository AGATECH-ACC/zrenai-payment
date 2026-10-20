import hashlib
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import TokenCode


class SignupForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "password1", "password2")


class TokenCodeForm(forms.ModelForm):
    token_key = forms.CharField(
        label="Token key", max_length=4096,
        widget=forms.PasswordInput(render_value=False),
        help_text="Paste one unique code. It is encrypted before storage.",
    )

    class Meta:
        model = TokenCode
        fields = ("product", "label", "token_key")

    def clean_token_key(self):
        value = self.cleaned_data["token_key"].strip()
        fingerprint = hashlib.sha256(value.encode()).hexdigest()
        if TokenCode.objects.filter(fingerprint=fingerprint).exists():
            raise forms.ValidationError("This token code is already in inventory.")
        return value

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.set_code(self.cleaned_data["token_key"])
        if commit:
            obj.save()
        return obj
