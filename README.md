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

With `DEBUG=true` and no Razorpay keys the checkout runs in **sandbox mode**: a local page stands in for
Razorpay's checkout and returns through the real verify endpoint with a real signature check, so the whole buy
flow can be walked on a laptop. Add `rzp_test_` keys to `.env` and it switches to Razorpay's Standard Checkout
automatically. Sandbox mode never exists with `DEBUG=false`: the process refuses to start until every Razorpay
variable is set.

## Tests

```bash
.venv/bin/python manage.py test
```

Covers the bag, checkout, signature verification, verify-endpoint and webhook idempotency, stock decrement, oversell
flagging, retries, tracking, and the admin. No network calls; the Razorpay SDK is mocked.

## How the payment path works

1. `POST /checkout/` validates the address, creates a `pending` Order with price snapshots, and asks Razorpay for
   an order id (`orders/razorpay_gateway.py`, the only file that knows about paise).
2. `/checkout/pay/<order-number>/` shows the summary and a Pay button that opens Razorpay's Standard Checkout
   modal (`checkout.js`) with the order id, key id and amount built server-side. Order pages are only visible to
   the session that is checking out; anyone else gets a 404. This is the one page on the site that needs
   JavaScript; everything else is plain HTML.
3. On success the modal hands the browser `razorpay_order_id`, `razorpay_payment_id` and `razorpay_signature`,
   which it POSTs to `/checkout/verify/` — same origin, so the CSRF token and session apply. The order is found by
   gateway id and the HMAC signature is the only thing trusted. Closing the modal makes no request; the order stays
   pending and stock is untouched.
4. `Order.mark_paid()` moves `pending → paid` exactly once (atomic conditional update) and decrements stock exactly
   once. A stock shortfall never blocks the payment; it lands in `ops_notes` and the admin list flags it.
5. `/webhooks/razorpay/` handles `payment.captured` as a backstop if the shopper closes the tab. Same idempotent path.
   It is the only CSRF-exempt view.
6. The confirmation page is the receipt. On payment the order number is added to the session's `confirmed_orders`
   list, and `/order/<order-number>/` renders only for a session that holds the number; a guessed number is a 404.
   Later status checks go through `/track/` with the order number and email.

Unpaid checkouts are marked abandoned by `python manage.py expire_orders` (run from cron).

## Layout

```
catalog/   products, per-size variants, images, seed catalogue (seed_data.py, manage.py seed_catalog)
orders/    session bag, checkout, Razorpay gateway, verify endpoint/webhook, tracking, admin
support/   contact form → SupportTicket, FAQ, policy pages
templates/ server-rendered pages; static/css/site.css is the whole stylesheet
tools/render_imagery.py   generates every product and editorial image as SVG in the two brand colours
```

## Configuration (`.env`)

| Variable | Notes |
| --- | --- |
| `SECRET_KEY` | required |
| `DEBUG` | `true` locally |
| `ALLOWED_HOSTS`, `SITE_URL` | public origin; `SITE_URL` is used for canonical links, the sitemap and social cards |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` | required when `DEBUG=false`; blank with `DEBUG=true` = sandbox mode |
| `RAZORPAY_WEBHOOK_SECRET` | required when `DEBUG=false`; the webhook returns 403 without it |
| `SUPPORT_EMAIL`, `SUPPORT_WHATSAPP`, `INSTAGRAM_HANDLE` | storefront contact details |

Shipping is free across India on all orders; that sentence and the dispatch copy live in `STORE` in `config/settings.py`.

## Deploying

`DEBUG=false` turns on secure cookies and WhiteNoise's hashed static files; run `python manage.py collectstatic`
before starting the WSGI server. Point the Razorpay dashboard webhook at `<SITE_URL>/webhooks/razorpay/`.
