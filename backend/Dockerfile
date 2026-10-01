FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /uvx /bin/

WORKDIR /app

# Use the interpreter in this image. Do not let uv fetch another CPython.
ENV UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy

# Dependency layer. Source is copied only after install, so app edits
# do not bust this cache. GIT_COMMIT stays below that, for the same reason.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project \
    && rm -rf /root/.cache/uv

COPY app ./app

ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=${GIT_COMMIT}

EXPOSE 8000

CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
