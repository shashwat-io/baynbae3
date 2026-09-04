#!/usr/bin/env bash
# One-shot setup from a fresh clone: venv, deps, .env, images, database, catalogue, admin user.
set -euo pipefail
cd "$(dirname "$0")"

PY=${PYTHON:-python3}
if [ ! -d .venv ]; then "$PY" -m venv .venv; fi
. .venv/bin/activate
pip install -q --disable-pip-version-check -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
  sed -i.bak "s|^SECRET_KEY=.*|SECRET_KEY=$KEY|" .env && rm -f .env.bak
  echo "Wrote .env with a fresh SECRET_KEY (DEBUG=true, Razorpay in sandbox mode)."
fi

python tools/render_imagery.py
python manage.py migrate --noinput
python manage.py seed_catalog

if [ -n "${ADMIN_PASSWORD:-}" ]; then
  DJANGO_SUPERUSER_PASSWORD="$ADMIN_PASSWORD" python manage.py createsuperuser --noinput --username "${ADMIN_USER:-admin}" --email "${ADMIN_EMAIL:-admin@example.com}" 2>/dev/null \
    && echo "Admin user '${ADMIN_USER:-admin}' created." || echo "Admin user already exists."
else
  echo "Skipping admin user (set ADMIN_PASSWORD=... to create one, or run: python manage.py createsuperuser)."
fi

echo
echo "Ready. Run:  .venv/bin/python manage.py runserver"
echo "Storefront:  http://127.0.0.1:8000/     Admin: http://127.0.0.1:8000/admin/"
