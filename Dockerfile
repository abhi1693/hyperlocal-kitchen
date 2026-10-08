FROM python:3.12-alpine3.23
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_LINK_MODE=copy
RUN pip install --no-cache-dir uv==0.12.21
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
