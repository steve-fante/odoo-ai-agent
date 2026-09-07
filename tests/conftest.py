from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from odoo_ai_agent.db import SQLiteDatabase  # noqa: E402
from odoo_ai_agent.retriever import build_retriever  # noqa: E402
from scripts.seed_demo import seed  # noqa: E402


@pytest.fixture(scope="session")
def demo_db_path(tmp_path_factory) -> Path:  # noqa: ANN001
    path = tmp_path_factory.mktemp("data") / "demo_odoo.sqlite"
    seed(path)
    return path


@pytest.fixture()
def db(demo_db_path: Path) -> SQLiteDatabase:
    database = SQLiteDatabase(demo_db_path, max_rows=50)
    yield database
    database.close()


@pytest.fixture(scope="session")
def retriever():  # noqa: ANN201
    return build_retriever(ROOT / "data" / "kb")
