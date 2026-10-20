# ZrenAI token code store

A working Django application for selling unique token codes through Curlec.
Admins enter products, MYR prices, and token keys. A customer signs up, pays
through Curlec Standard Checkout, and receives one reserved code in their
purchase history after the server verifies a captured payment.

This implements **one-time code purchases**. Recurring subscriptions are not
enabled: each renewal would need an agreed code allocation and out-of-stock policy.
Codes are supplied by the store; this app does not generate tokens or redeem
them in another service.

## Local development

Python 3.12 or later is recommended; local checks use Python 3.14 and
`.python-version` selects Python 3.12 for Vercel.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock.txt
.venv/bin/python scripts/setup_local.py
.venv/bin/python manage.py migrate
.venv/bin/python manage.py bootstrap_local_admin
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

- Store: <http://127.0.0.1:8000/>
- Customer login: <http://127.0.0.1:8000/accounts/login/>
- Admin: <http://127.0.0.1:8000/admin/>
- Initial local admin credentials: `data/local-admin-access.txt` (mode 0600).

The setup script creates independent application, encryption, and webhook keys
in `.env`. It does not print secrets or overwrite keys that already exist.
No sample products, token codes, or simulated payment success are enabled.
The local SQLite database and `.env` are ignored by Git.

## Configure your store

1. Log in to the admin panel. Change the generated local admin password.
2. Under **Products**, create a name, description, and price in sen.
   For example, a price of `1500` means RM 15.00. This is an input example,
   not a configured product or a suggested selling price.
3. Under **Token codes**, select the product and paste one unique token key.
   Use the optional label for your internal batch/reference.
4. Repeat for each code. Keys are encrypted in the database and duplicate
   keys are rejected across products. Existing entries are immutable.
5. Customers can register and log in. A purchase delivers exactly one code.
6. Use **Orders** to see the buyer, product, payment references, delivery
   status, and assigned token. Authorized staff can open the token record
   to view the actual key.

Prices and active state are editable. Existing orders keep the original price
and product name. Deactivating a product prevents new purchases; an existing
reserved checkout can still be completed.

## Connect Curlec test payments

In `.env`, configure the credentials from your own Curlec Test Mode account:

```dotenv
CURLEC_KEY_ID=your_test_key_id
CURLEC_KEY_SECRET=your_test_key_secret
```

Use the generated `CURLEC_WEBHOOK_SECRET` from `.env` when adding the webhook
in Curlec. It is separate from the API key secret. Do not paste any secret into
chat or commit `.env`.

For a payment test, use a publicly accessible HTTPS staging domain:

```dotenv
DEBUG=false
APP_BASE_URL=https://your-staging-domain
ALLOWED_HOSTS=your-staging-domain
```

Configure Curlec:

- Enable automatic payment capture.
- Webhook URL: `https://your-staging-domain/api/curlec/webhook/`
- Subscribe to `payment.captured` and `order.paid`.
- Enter the matching `CURLEC_WEBHOOK_SECRET`.
- Allowlist the checkout callback domain. Callback URLs use
  `/api/curlec/callback/<local-order-uuid>/`.
- Keep Test Mode credentials and webhook settings together. Use a separate
  database and inventory for Live Mode; never switch a store with pending test
  orders to live keys.

Curlec cannot deliver webhooks to localhost. Its documentation also lists
restrictions for common tunnel providers; prefer an HTTPS staging deployment.
The app uses `redirect: true` and a callback URL to support the documented FPX
redirect flow.

Test with a disposable token code first. Confirm that a successful test payment
reveals the code in My purchases and that the admin order shows Delivered.
Check that failure/dismissal leaves the code hidden and that replaying a webhook
does not allocate another code. A real Curlec test payment still needs to be run
with your configured merchant keys.

## Payment and inventory guarantees

- Server-side product prices are authoritative. Browser amounts and user IDs
  are not accepted as purchase parameters.
- A code is reserved atomically **before** making a provider order.
- Each code can belong to one purchase; each provider payment ID is unique.
- PostgreSQL locks the buyer, product, and reserved inventory rows to protect
  concurrent checkouts; payment fulfillment locks its order row.
- Repeated checkout requests reuse the same pending order.
- The checkout callback verifies HMAC using the server-stored provider order ID.
- Webhooks verify HMAC over the raw request bytes.
- Delivery fetches both payment and order from Curlec and checks order receipt,
  references, amount, currency, captured status, and refund amount.
- Authorization alone does not deliver. Callback/webhook retries are idempotent.
- Token retrieval requires the purchasing account. Customer responses are
  private and not cacheable. Staff access uses Django permissions.
- Login rate limiting is enabled through django-axes.
- Token codes are encrypted using a dedicated Fernet key. Back up this key
  separately from the database; losing it makes codes unrecoverable.

### Interrupted checkouts and reconciliation

A customer can resume a pending order from My purchases even if the product is
sold out or inactive. Codes reserved by abandoned or uncertain checkouts are
**not automatically returned to stock**: a late captured payment could otherwise
sell the same code twice. The admin list shows these outstanding reservations.
There is a maximum of three unpaid purchases per customer.

If a provider order request times out, the purchase is marked Needs reconciliation.
Locate its receipt (the local purchase UUID) in your Curlec Dashboard, then run:

```sh
# Attach the confirmed remote order; the app validates receipt and price.
.venv/bin/python manage.py reconcile_payment --provider-order-id order_REFERENCE

# Re-fetch and fulfill a captured payment, including after a lost webhook.
.venv/bin/python manage.py reconcile_payment --payment-id pay_REFERENCE
```

These commands never issue charges. Do not retry ambiguous creates or recycle
their codes manually. A refunded code that was already shown to a customer is
not reusable; refund processing and revocation in the target service are manual.
This version does not automatically process refunds or release reservations.

## HTTP API

Customer APIs use Django session cookies. All customer POST requests require
the `X-CSRFToken` header; the storefront provides a working implementation.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/checkout/` | Create/resume checkout with `{"product_id": 1}` |
| POST | `/api/orders/<uuid>/resume/` | Resume the owner's existing checkout |
| GET | `/api/orders/<uuid>/` | Owner-only status; includes `token_code` only when delivered |
| POST | `/api/curlec/callback/<uuid>/` | Signed Curlec redirect callback |
| POST | `/api/curlec/webhook/` | Signed provider event notification |

The callback and webhook are intentionally CSRF-exempt because they are
provider POSTs; their HMAC checks replace browser CSRF authentication.

## Verification

```sh
.venv/bin/python manage.py test shop
.venv/bin/python scripts/check_concurrency.py
# If local PostgreSQL tools are installed: all tests, including row-lock races,
# run inside a disposable cluster without reading or modifying cloud data.
.venv/bin/python scripts/check_postgres.py
.venv/bin/python manage.py check
.venv/bin/python manage.py collectstatic --noinput
```

The automated suite uses isolated test fixtures and mocked provider transport
to cover fraud, retry, inventory, and access-control cases without creating
merchant charges. Runtime payment code always calls the real Curlec API.

## Hosting

### Vercel

Vercel detects `manage.py` and `gateway.wsgi.application`. It automatically
collects static files, so no custom build or output-directory override is needed.
The project supports PostgreSQL using `DATABASE_URL`; SQLite is rejected on
Vercel rather than silently losing orders between invocations.

Before deploying, configure these **Production** environment variables in the
`zrenai-payment` Vercel project:

| Variable | Value/source |
| --- | --- |
| `DJANGO_SECRET_KEY` | A long stable random application secret |
| `TOKEN_ENCRYPTION_KEY` | A stable Fernet key; preserve the existing key when migrating inventory |
| `DATABASE_URL` | PostgreSQL URL supplied by the connected Storage integration |
| `DATABASE_SCHEMA` | `zrenai_payment` for the private Supabase schema |
| `DEBUG` | `false` |
| `APP_BASE_URL` | The canonical public HTTPS store URL |
| `ALLOWED_HOSTS` | The canonical hostname, plus any other intended aliases, comma separated |
| `CURLEC_KEY_ID` | Curlec Test Mode key ID until live acceptance testing is complete |
| `CURLEC_KEY_SECRET` | Matching Curlec API secret |
| `CURLEC_WEBHOOK_SECRET` | The exact secret configured on the Curlec webhook |

Do not generate new encryption/session keys on every build. Add secrets through
Vercel's environment settings or CLI stdin; never commit the local `.env`.
The app also allows the deployment's exact `VERCEL_URL` hostname and trusts
Vercel's HTTPS forwarding header. It does not allow every `*.vercel.app` host.

Connect your Supabase PostgreSQL database using its transaction-pooler
connection URL (port 6543, TLS required). Psycopg prepared statements and
server-side cursors are disabled for compatibility with this pooler.
Use a dedicated database role and private schema for Django's tables so they
are not exposed through Supabase's Data API. Supabase publishable/service API
keys do not replace the PostgreSQL password in `DATABASE_URL`.
The database role's default `search_path` must point to `zrenai_payment`.
The app verifies this on every database connection, preventing migrations or
requests from accidentally using another schema. After migrations, it enables
RLS and revokes PUBLIC table access for all tables owned by the app in that
schema, including Django's account and session tables. No public RLS policies
are created: the trusted Django role owns its tables and handles authorization.
Use a separate database for Preview; do not connect preview code to production
inventory.

Before the first deployment, migrate the connected database explicitly:

```sh
vercel env pull .env.vercel.production --environment=production --yes
APP_ENV_FILE=.env.vercel.production VERCEL=1 .venv/bin/python manage.py migrate --noinput
APP_ENV_FILE=.env.vercel.production VERCEL=1 .venv/bin/python manage.py check --deploy
APP_ENV_FILE=.env.vercel.production VERCEL=1 .venv/bin/python manage.py createsuperuser
```

Environment files contain secrets and must stay private. `APP_ENV_FILE` makes
using cloud settings explicit; ordinary local development continues to load
`.env` and the local database. Migrations are deliberately not run automatically
by every build. After environment changes, redeploy—existing deployments retain
their previous settings.

Configure the Curlec webhook and callback allowlist for `APP_BASE_URL` as
described above. A deployment succeeding does not by itself verify a payment.

### Persistent host

SQLite remains available on a single persistent host with HTTPS.
Its transactions use `BEGIN IMMEDIATE`, serializing inventory allocation across
local processes. Keep the database on local persistent disk, not an ephemeral
or shared network filesystem. Set `DATABASE_URL` to use PostgreSQL instead.

```sh
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py check --deploy
.venv/bin/gunicorn gateway.wsgi:application --bind 127.0.0.1:8000 --workers 2
```

Use a trusted HTTPS reverse proxy, configure its secure scheme forwarding in
Django to suit that host, and set `DEBUG=false`, `APP_BASE_URL`, and `ALLOWED_HOSTS`.
Create a separate production admin with `manage.py createsuperuser`.
Back up the database consistently using SQLite's backup API, plus the encryption
key separately (or use your PostgreSQL provider's backup facilities).
Apply signup/checkout abuse limits at the ingress before opening
public sales; login lockouts and per-account unpaid-order limits are not a full
inventory-abuse defense. Customer self-service password reset/email delivery
is not configured; administrators can reset accounts after verifying ownership.

## Provider documentation

- [Curlec Standard Checkout](https://curlec.com/docs/payments/payment-gateway/web-integration/standard/integration-steps)
- [Curlec API keys](https://curlec.com/docs/payments/dashboard/account-settings/api-keys)
- [Webhook validation and testing](https://curlec.com/docs/webhooks/validate-test/)
- [Fetch a payment](https://curlec.com/docs/api/payments/fetch-with-id/)
- [Subscriptions API, for a future recurring flow](https://curlec.com/docs/api/payments/subscriptions)
