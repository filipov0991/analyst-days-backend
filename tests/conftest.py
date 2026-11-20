import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.seed import seed


@pytest.fixture
def application(tmp_path):
    app = create_app(Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'test.db'}"))
    seed(app.state.engine)
    yield app
    app.state.engine.dispose()


@pytest.fixture
def client(application):
    with TestClient(application) as client:
        yield client


@pytest.fixture
def origin():
    return {"Origin": "http://localhost:3000"}
