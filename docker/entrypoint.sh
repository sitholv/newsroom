#!/bin/sh
set -eu

# Database readiness is enforced by Compose; a migration error must stop startup.
python manage.py migrate --noinput
exec gunicorn newsroom.wsgi:application \
    --bind 0.0.0.0:8000 --workers 2 --threads 2 \
    --access-logfile - --error-logfile -
