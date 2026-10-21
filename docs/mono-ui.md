# Mono Intelligence / Option 04 — payment app

Implemented in the existing Django 5.2 application. No framework migration,
production deployment, Git push, new payment provider, or cloud data mutation.
The project's brand remains **ZrenAI Token Store / Payment Admin**. The supplied
kit's unrelated Studio, course, partner, commission and sample chart content is
not part of this app.

## Local preview

```sh
.venv/bin/python manage.py runserver 127.0.0.1:8001
```

- Store: http://127.0.0.1:8001/ (sign-in required)
- Purchase dashboard: http://127.0.0.1:8001/purchases/
- Staff dashboard: http://127.0.0.1:8001/admin/
- Local credentials remain in the ignored `data/local-admin-access.txt`.

The preview uses the existing local SQLite database; it currently has no products
or purchases. Zero totals and empty states are real, not gallery placeholders.
No demonstration inventory was inserted. The previous local schema migration for
academy identity was applied; this design adds no model migration.

Production still uses the configured Supabase PostgreSQL connection and academy
SSO. The local development setting retains its existing local account login.
The public entry remains sign-in first. The authenticated `/` catalog and the SSO
sign-in page have editable HTML headlines and the supplied contour artwork.

## Shared layers and components

| Layer | Files / responsibilities |
| --- | --- |
| Tokens | `static/ui/tokens.css`: exact kit colors, spacing, radii, local Inter and Chinese system font fallbacks. Font URL adapted to Django static paths. |
| Primitives | `static/ui/components.css`: original kit buttons, fields, panels/cards, badges, alerts, tables, segmented controls, dialogs, empty states, skeletons, focus and reduced-motion styles. |
| Adaptations | `static/ui/application.css`: shared navigation, metrics, table links, notification, loading indicator and responsive workspaces. |
| Helpers | `static/ui/components.js`: kit icon hydration and escaped helpers, with payment-store branding. `application.js`: native dialog opening/closing, focus return, dismissible messages and polite notifications. |
| Django partials | `templates/ui/`: assets, brand, button, field, icon, metric, order status, order table, empty state, messages, loading and purchase guide dialog. |
| Storefront | `templates/base.html`, `templates/shop/store.html`, `static/shop.css`: contour hero, real catalog, stock-aware checkout controls, guide dialog. |
| Customer workspace | `templates/dashboard_base.html`, `templates/shop/purchases.html`, `templates/shop/purchase.html`: black navigation, owner-scoped summary, status filters, delivery/copy/resume controls. |
| Staff workspace | `templates/admin/base_site.html`, `payment_index.html`, `static/admin.css`: permission-aware navigation and Django's existing forms, lists, filters, actions and related widgets. |
| Sign-in | `templates/registration/`, `templates/admin/login.html`, `static/admin-login.css`: existing SSO/local/staff flows in the shared visual system. |
| Data | `shop/admin_site.py`, `shop/views.py`, `gateway/settings.py`: custom Django AdminSite, permission-scoped dashboard queries and owner-scoped purchase filtering. |
| Verification | `shop/test_dashboard.py`: ownership, amount aggregation and role access regression tests. |

Use the `zr-button--primary` variant for black primary actions, `--accent` for
lime workspace actions, `--ghost` for quiet controls. Template fields retain
Django's labels, `aria-invalid`, error IDs and help-text associations. The shared
order table uses semantic headers, descriptive links and keyboard-accessible
horizontal scrolling. Segmented purchase links use `aria-current` and work
without JavaScript. Native dialogs support Escape, focus containment and return
to the invoking control. Loading UI represents actual payment polling; checkout
buttons expose `aria-busy`. Notifications do not carry token codes.

The original UI kit MIT license and Inter / Feather vendor notices are preserved
in `static/ui/`. Chart.js and its source-project business aggregation are not
included because there is no chart in this implementation. All UI fonts and
icons are served locally. Curlec's existing hosted payment script remains the
necessary payment integration.

## Data and access rules

- Purchase counts are scoped to `request.user`; status filters do not change the
  scope or top-level totals. In progress includes creating, pending and review.
- Paid totals sum integer `amount` values on currently `paid` orders, formatted
  as MYR with Decimal. These are all-time confirmed purchase totals, not a bank
  settlement, revenue or refund accounting chart.
- Admin summaries require the corresponding ModelAdmin view/change permission
  and use its queryset. Staff with inventory access cannot read order totals.
- Available codes are unassigned inventory across all packages; reserved and
  delivered codes remain assigned. Active product counts do not imply stock.
- Academy identity, staff roles, CSRF, signed callbacks/webhooks, encrypted code
  storage, checkout price validation and code ownership remain enforced.
- No new token quantities, selling prices or redeemable codes were invented.

## Verification — 2026-10-21

- `python scripts/check_postgres.py`: **44 tests pass**, disposable local
  PostgreSQL with the private schema, including existing payment/authentication,
  signature, reconciliation, inventory/concurrency and 4 new dashboard tests.
- `manage.py check` and `collectstatic --noinput`: pass.
- `node --check` on the shared helpers, application behavior, checkout and purchase
  scripts: pass. `git diff --check`: clean.
- Browser: local staff sign-in and sign-out, dashboard links, invalid product
  price validation (no product saved), purchase filters, dialog Tab/Escape and
  focus return, desktop/mobile layouts. Fixed mobile artwork/text overlap, form
  field overflow and an icon-only logout label found during these checks.
- Browser confirms Inter loaded locally and background `rgb(241, 242, 239)`.
  No horizontal page overflow on the desktop storefront. Wide data tables use
  bounded scrolling; automated tests exercise populated table output.
- Screenshots in `docs/mono-preview/`: desktop/mobile storefront and admin,
  mobile purchase history. These show the actual empty local database.
- No payment was charged during this visual QA. Actual SSO redirects and hosted
  Curlec payment completion were not re-run against production for this local
  design task; the regression suite verifies their existing application paths.

## 简体中文界面（2026-10-21）

商店、学院登录入口、购买记录、订单详情、购买指南及管理后台均使用简体中文。系统语言为 `zh-hans`；字段校验、日期及后台自带操作采用中文翻译，金额显示为“马币”。后台的登录安全插件使用 `locale/zh_Hans/LC_MESSAGES/django.po` 补充翻译；修改后运行 `msgfmt locale/zh_Hans/LC_MESSAGES/django.po -o locale/zh_Hans/LC_MESSAGES/django.mo`。

`shop/migrations/0003_alter_order_options_alter_product_options_and_more.py` 仅记录字段显示名称、帮助文字及订单状态显示标签的调整；订单状态值、价格单位、支付协议及权限规则保持不变。套餐名称、用户账号和兑换码等实际数据不做翻译。支付平台独立托管的收银台语言不由本站模板控制。

本地检查包括桌面和 390 像素手机视图、套餐价格错误提示、弹窗键盘退出及焦点返回。已更新中文商店、管理概览及购买记录截图，现有 44 项测试通过。未部署。
