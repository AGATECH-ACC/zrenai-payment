import hashlib
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import TokenCode


class SignupForm(UserCreationForm):
    email = forms.EmailField(label="邮箱", required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "password1", "password2")


class TokenCodeForm(forms.ModelForm):
    token_key = forms.CharField(
        label="兑换码", max_length=4096,
        widget=forms.PasswordInput(render_value=False),
        help_text="请粘贴一个唯一的兑换码，系统会加密保存。",
    )

    class Meta:
        model = TokenCode
        fields = ("product", "label", "token_key")

    def clean_token_key(self):
        value = self.cleaned_data["token_key"].strip()
        fingerprint = hashlib.sha256(value.encode()).hexdigest()
        if TokenCode.objects.filter(fingerprint=fingerprint).exists():
            raise forms.ValidationError("此兑换码已存在于库存中。")
        return value

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.set_code(self.cleaned_data["token_key"])
        if commit:
            obj.save()
        return obj
