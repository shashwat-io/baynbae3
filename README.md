# Bay'n Bae — storefront

Small-batch Indian resort wear. Kaftans, cover-ups, resort dresses, co-ord and shorts sets, ₹1,000–5,000.
Server-rendered Django, Razorpay prepaid checkout, no customer accounts, stock per size, Django admin as the back office.

## Run it

```bash
git clone <this repo> baynbae && cd baynbae
ADMIN_PASSWORD=changeme ./bootstrap.sh     # venv, deps, .env, images, migrate, seed, admin user
.venv/bin/python manage.py runserver
```

- Storefront: http://127.0.0.1:8000/
- Back office: http://127.0.0.1:8000/admin/ (user `admin`, the password you set)

Without Razorpay keys the checkout runs in **sandbox mode**: a local page stands in for Razorpay's hosted
checkout and returns through the real callback with a real signature check, so the whole buy flow can be
walked on a laptop. Add `rzp_test_` keys to `.env` and it switches to Razorpay's hosted checkout automatically.

## Tests

```bash
.venv/bin/python manage.py test
```

Covers the bag, checkout, signature verification, callback and webhook idempotency, stock decrement, oversell
flagging, retries, tracking, and the admin. No network calls; the Razorpay SDK is mocked.

## How the payment path works

1. `POST /checkout/` validates the address, creates a `pending` Order with price snapshots, and asks Razorpay for
   an order id (`orders/razorpay_gateway.py`, the only file that knows about paise).
2. `/checkout/pay/<token>/` shows the summary and a plain HTML form that posts to Razorpay's hosted checkout.
   No JavaScript is required anywhere on the site.
3. Razorpay POSTs back to `/checkout/callback/`. The session cookie is not available cross-site, so the order is
   found by gateway id and verified with the HMAC signature only.
4. `Order.mark_paid()` moves `pending → paid` exactly once (atomic conditional update) and decrements stock exactly
   once. A stock shortfall never blocks the payment; it lands in `ops_notes` and the admin list flags it.
5. `/webhooks/razorpay/` handles `payment.captured` as a backstop if the shopper closes the tab. Same idempotent path.
6. The confirmation page is addressed by a signed token, so it works with or without a session and doubles as the receipt.

Unpaid checkouts are marked abandoned by `python manage.py expire_orders` (run from cron).

## Layout

```
catalog/   products, per-size variants, images, seed catalogue (seed_data.py, manage.py seed_catalog)
orders/    session bag, checkout, Razorpay gateway, callback/webhook, tracking, admin
support/   contact form → SupportTicket, FAQ, policy pages
templates/ server-rendered pages; static/css/site.css is the whole stylesheet
tools/render_imagery.py   generates every product and editorial image as SVG in the two brand colours
```

## Configuration (`.env`)

| Variable | Notes |
| --- | --- |
| `SECRET_KEY` | required |
| `DEBUG` | `true` locally |
| `ALLOWED_HOSTS`, `SITE_URL` | public origin; `SITE_URL` is used for the Razorpay callback URL |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` | blank = sandbox mode |
| `RAZORPAY_WEBHOOK_SECRET` | optional; webhook returns 403 without it |
| `SUPPORT_EMAIL`, `SUPPORT_WHATSAPP`, `INSTAGRAM_HANDLE` | storefront contact details |

Shipping rules (free over ₹1,999, ₹79 otherwise) and dispatch copy live in `STORE` in `config/settings.py`.

## Deploying

`DEBUG=false` turns on secure cookies and WhiteNoise's hashed static files; run `python manage.py collectstatic`
before starting the WSGI server. Point the Razorpay dashboard webhook at `<SITE_URL>/webhooks/razorpay/`.
