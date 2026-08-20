FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    VERIDRA_BIND_HOST=0.0.0.0 \
    VERIDRA_BIND_PORT=8000

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN python -m pip install --no-cache-dir . \
    && python -m playwright install --with-deps chromium \
    && groupadd --system veridra \
    && useradd --system --gid veridra --create-home veridra \
    && mkdir -p /var/lib/veridra \
    && chown -R veridra:veridra /var/lib/veridra /ms-playwright

USER veridra

EXPOSE 8000

CMD ["veridra-api"]
