# syntax=docker/dockerfile:1
FROM --platform=$BUILDPLATFORM node:24-bookworm-slim AS frontend
WORKDIR /build/web
RUN npm install --global pnpm@12.6.0
COPY web/ ./
RUN pnpm install --frozen-lockfile
ARG SOURCE_REVISION
RUN test -n "$SOURCE_REVISION"
RUN CAF_SOURCE_REVISION="$SOURCE_REVISION" pnpm build

FROM python:3.12-slim-bookworm AS python-build
COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY packages/ packages/
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm AS runtime
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && install -d /etc/apt/keyrings \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc -o /etc/apt/keyrings/pgdg.asc \
    && echo 'deb [signed-by=/etc/apt/keyrings/pgdg.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main' > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
       tesseract-ocr tesseract-ocr-eng postgresql-client-16 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 caf \
    && useradd --uid 10001 --gid caf --create-home caf
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CAF_ENV=production
COPY --from=python-build /app/.venv .venv/
# Keep migration scripts and workspace metadata available to administration commands.
COPY --from=python-build /app/packages packages/
COPY pyproject.toml uv.lock alembic.ini ./
COPY deploy/settings.toml config/settings.toml
COPY config/scoring.toml config/depth.toml config/sources.toml config/models.toml config/
COPY taxonomy/ taxonomy/
COPY prompts/ prompts/
COPY profiles/ profiles/
COPY overrides/ overrides/
COPY --from=frontend /build/web/apps/student/dist web/apps/student/dist/
COPY --from=frontend /build/web/apps/curator/dist web/apps/curator/dist/
ARG SOURCE_REVISION
LABEL org.opencontainers.image.revision="$SOURCE_REVISION"
RUN install -d -o caf -g caf /srv/caf/data
USER 10001:10001
EXPOSE 8788
CMD ["uvicorn", "caf_api.main:app", "--host", "0.0.0.0", "--port", "8788", "--workers", "1"]
