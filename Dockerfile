FROM python:3.12.15-alpine3.24@sha256:b658b05ce9c4eb97ec6fc19424818a1f31993659c2b505a532f470e83807815d
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv==0.13.5
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
COPY apps/api/ apps/api/
COPY apps/admin-api/ apps/admin-api/
COPY apps/worker/ apps/worker/
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --all-packages --no-dev
COPY alembic.ini ./
COPY migrations/ migrations/
RUN addgroup -g 10001 kitchen && adduser -D -u 10001 -G kitchen kitchen
USER kitchen
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "kitchen_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--no-access-log"]
