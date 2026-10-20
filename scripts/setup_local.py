"""Generate application secrets locally, without printing or replacing existing values."""
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import dotenv_values, set_key

root = Path(__file__).resolve().parent.parent
env = root / ".env"
if not env.exists():
    env.write_text((root / ".env.example").read_text())
os.chmod(env, 0o600)
values = dotenv_values(env)
for name, value in {
    "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
    "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
    "CURLEC_WEBHOOK_SECRET": secrets.token_urlsafe(48),
}.items():
    if not values.get(name):
        set_key(env, name, value)
print("Local application keys configured in .env (permissions 0600).")
print("Add your Curlec key ID and secret there. Keep the encryption key backed up privately.")
