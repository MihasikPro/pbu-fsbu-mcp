FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
WORKDIR /app
# The runtime stage below is a *different* image (python:3.12-slim-bookworm,
# not the uv image) - if uv were left free to manage its own Python, the venv
# it builds here could end up with shebangs pointing at an interpreter path
# that does not exist in the runtime stage. Pinning it to the build image's
# own system Python removes that mismatch instead of relying on the two
# images happening to agree on a path.
ENV UV_PYTHON_DOWNLOADS=never UV_PYTHON_PREFERENCE=only-system
COPY pyproject.toml uv.lock* ./
COPY src ./src
COPY etl ./etl
COPY data/sources ./data/sources
# --no-editable: the runtime stage copies only .venv, not /app/src - an
# editable install's .pth file points back at /app/src, which is on disk in
# this stage but not guaranteed to stay at that exact path once copied.
RUN uv sync --no-dev --frozen --no-editable
# --no-sync on both, and this is not belt-and-braces: `uv run` re-syncs the
# environment by default, using the project's defaults rather than the flags
# given to `uv sync` above. Without it the editable install and the dev group
# come back, the venv ends up with a .pth pointing at /app/src, and the runtime
# stage - which does not copy src/ - dies with ModuleNotFoundError on startup.
# Verified by building: that is exactly what happened before this flag was added.
RUN uv run --no-sync python -m etl.build_db --sources data/sources/standards --output data/build/pbu_fsbu.db
RUN uv run --no-sync python -m etl.validate --db data/build/pbu_fsbu.db

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/data/build/pbu_fsbu.db /app/data/build/pbu_fsbu.db
COPY LICENSE /app/LICENSE
COPY data/LICENSE /app/data/LICENSE
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 18010
# --no-editable above makes the venv self-contained, so /app/src no longer
# needs to be copied into this stage at all.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:18010/healthz', timeout=3)"
CMD ["pbu-fsbu-mcp", "--transport", "http", "--host", "0.0.0.0", "--port", "18010", "--db", "/app/data/build/pbu_fsbu.db"]
