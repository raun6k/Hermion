"""Invariant: app/engine is pure (no I/O, DB, network, clock, randomness)."""

import ast
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2] / "app" / "engine"
FORBIDDEN = {
    "sqlalchemy",
    "httpx",
    "openai",
    "websockets",
    "fastapi",
    "asyncio",
    "random",
    "time",
    "datetime",
    "os",
    "socket",
    "app.db",
    "app.services",
    "app.agent",
    "app.speech",
    "app.api",
}


def test_engine_imports_nothing_impure() -> None:
    for path in ENGINE.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                assert not any(name == f or name.startswith(f + ".") for f in FORBIDDEN), (
                    f"{path.name}: {name}"
                )
