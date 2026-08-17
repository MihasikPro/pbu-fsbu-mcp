FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS build
WORKDIR /app
COPY pyproject.toml uv.lock* ./
COPY src ./src
COPY etl ./etl
COPY data/sources ./data/sources
RUN uv sync --no-dev --frozen
RUN uv run python -m etl.build_db --sources data/sources/standards --output data/build/pbu_fsbu.db
RUN uv run python -m etl.validate --db data/build/pbu_fsbu.db

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/src /app/src
COPY --from=build /app/data/build/pbu_fsbu.db /app/data/build/pbu_fsbu.db
COPY LICENSE /app/LICENSE
COPY data/LICENSE /app/data/LICENSE
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 18010
CMD ["pbu-fsbu-mcp", "--transport", "http", "--host", "0.0.0.0", "--port", "18010", "--db", "/app/data/build/pbu_fsbu.db"]
