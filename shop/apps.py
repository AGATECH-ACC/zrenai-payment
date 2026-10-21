from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connections
from django.db.backends.signals import connection_created
from django.db.models.signals import post_migrate


def check_private_schema(sender, connection, **kwargs):
    expected = settings.DATABASE_SCHEMA
    if not expected or connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_schema()")
        actual = cursor.fetchone()[0]
    if actual != expected:
        raise ImproperlyConfigured(
            f"The database login must use the private {expected} schema. "
            "Configure the database role's search_path before running migrations."
        )


def protect_private_tables(sender, using, **kwargs):
    connection = connections[using]
    schema = settings.DATABASE_SCHEMA
    if not schema or connection.vendor != "postgresql":
        return
    quote = connection.ops.quote_name
    with connection.cursor() as cursor:
        # Includes Django account/session tables and the migration ledger.
        # The dedicated app role owns these tables. Only this trusted backend
        # bypasses their RLS; there are no public API policies or grants.
        cursor.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = %s AND tableowner = current_user",
            [schema],
        )
        tables = cursor.fetchall()
        for (name,) in tables:
            table = f"{quote(schema)}.{quote(name)}"
            cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            cursor.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")


class ShopConfig(AppConfig):
    name = "shop"
    verbose_name = "额度商店"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        connection_created.connect(check_private_schema, dispatch_uid="shop.private_schema")
        post_migrate.connect(
            protect_private_tables, sender=self, dispatch_uid="shop.private_tables",
        )
