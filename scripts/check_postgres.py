"""Run tests against a disposable local PostgreSQL cluster; never uses cloud data."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlencode

from cryptography.fernet import Fernet
import psycopg

for command in ("initdb", "pg_ctl"):
    if not shutil.which(command):
        raise SystemExit(f"{command} is required for the disposable PostgreSQL test.")

with tempfile.TemporaryDirectory(prefix="zrenai-pg-") as directory:
    root = Path(directory)
    data = root / "cluster"
    log = root / "postgres.log"
    subprocess.run(
        ["initdb", "-D", str(data), "-U", "postgres", "--auth-local=trust",
         "--auth-host=reject", "--no-instructions", "--encoding=UTF8"],
        check=True, stdout=subprocess.DEVNULL,
    )
    try:
        # Unix socket in the private temp directory only; no TCP listener.
        subprocess.run(
            ["pg_ctl", "-D", str(data), "-l", str(log), "-o", f"-h '' -k {root}", "-w", "start"],
            check=True, stdout=subprocess.DEVNULL,
        )
        env = os.environ.copy()
        # New test databases inherit the private schema from this disposable template.
        with psycopg.connect(
            "postgresql://postgres@/template1?" + urlencode({"host": str(root)}),
            autocommit=True,
        ) as connection:
            connection.execute("CREATE SCHEMA zrenai_payment")
            connection.execute("REVOKE ALL ON SCHEMA zrenai_payment FROM PUBLIC")
            connection.execute("ALTER ROLE postgres SET search_path TO zrenai_payment")
        with psycopg.connect(
            "postgresql://postgres@/postgres?" + urlencode({"host": str(root)}),
            autocommit=True,
        ) as connection:
            connection.execute("CREATE SCHEMA zrenai_payment")
            connection.execute("REVOKE ALL ON SCHEMA zrenai_payment FROM PUBLIC")
        env.update({
            "DATABASE_URL": "postgresql://postgres@/postgres?" + urlencode({"host": str(root)}),
            "VERCEL": "0", "DEBUG": "true",
            "APP_ENV_FILE": str(root / "unused.env"),
            "DJANGO_SECRET_KEY": "disposable-postgres-test-secret",
            "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "DATABASE_SCHEMA": "zrenai_payment",
        })
        result = subprocess.run(
            [sys.executable, "manage.py", "test", "shop", "--noinput", "--verbosity=1"],
            env=env,
        )
    finally:
        subprocess.run(["pg_ctl", "-D", str(data), "-m", "immediate", "-w", "stop"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    raise SystemExit(result.returncode)
