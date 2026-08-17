# Intentionally empty. Its presence at the repo root, next to pyproject.toml,
# is what makes pytest add the repo root to sys.path - which is why
# `from etl.build_db import build` resolves in tests/. Do not delete this
# file because it looks empty and unused; deleting it breaks every test
# that imports from `etl`.
