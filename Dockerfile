FROM python:3.12-slim AS wheels

ENV PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential default-libmysqlclient-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 DJANGO_DEBUG=0
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmariadb3 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
COPY --from=wheels /wheels /wheels
RUN python -m pip install --no-cache-dir --no-index \
    --find-links=/wheels -r requirements.txt && rm -rf /wheels
COPY --chown=10001:10001 . .
# This public build-only placeholder is never the runtime signing key.
RUN NEWSROOM_SQLITE=1 DJANGO_SECRET_KEY=build-only-not-a-runtime-secret \
    python manage.py collectstatic --noinput \
    && chown -R 10001:10001 /app/staticfiles
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=6 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=4)"
ENTRYPOINT ["sh", "docker/entrypoint.sh"]
