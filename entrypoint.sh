#!/bin/sh
set -e

python manage.py migrate --fake-initial --noinput
python manage.py runserver 0.0.0.0:${APP_PORT:-8000}
