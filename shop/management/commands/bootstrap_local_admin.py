import os
import secrets
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a local-only admin with a random password saved privately under data/."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("For local development only. Use createsuperuser for deployment.")
        if User.objects.filter(username="admin").exists():
            self.stdout.write("Admin already exists; password unchanged.")
            return
        password = secrets.token_urlsafe(24)
        directory = Path(settings.BASE_DIR) / "data"
        directory.mkdir(mode=0o700, exist_ok=True)
        credentials = directory / "local-admin-access.txt"
        # Exclusive creation avoids overwriting a user's existing credential file.
        fd = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as file:
            file.write(
                f"Local development admin only\nURL: {settings.APP_BASE_URL}/admin/\n"
                f"Username: admin\nPassword: {password}\n\n"
                "Change this password in the admin panel. Do not commit or share this file.\n"
            )
        User.objects.create_superuser("admin", "", password)
        self.stdout.write("Local admin created. Credentials saved privately in data/local-admin-access.txt.")
