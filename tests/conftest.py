# tests/conftest.py — 測試用隔離 DB（不污染 data/webpos.db）
import pytest

@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    import database as db
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
