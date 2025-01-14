import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest_factoryboy import register
from sqlalchemy_utils import create_database, database_exists, drop_database
from sqlmodel import Session, SQLModel, create_engine

from api import create_application, factories
from api.dependencies import (
    get_assessment_config_file,
    get_session,
    get_settings,
)
from api.settings import Settings

TEST_DB_SERVER_URL: str = os.environ.get("TEST_DB_SERVER_URL", "postgresql://")

model_factories = [f for f in factories.all_factories]
for factory in model_factories:
    register(factory)


def set_session_for_factories(factory_objects, session: Session):
    for f in factory_objects:
        f._meta.sqlalchemy_session = session


@pytest.fixture(name="db_engine", scope="session")
def db_engine_fixture():
    engine = create_engine(f"{TEST_DB_SERVER_URL}/test-answerbook")
    if database_exists(engine.url):
        # Catch case in which previous test run failed without teardown
        drop_database(engine.url)
    create_database(engine.url)
    SQLModel.metadata.create_all(engine)
    yield engine
    drop_database(engine.url)


@pytest.fixture(name="session", autouse=True)
def session_fixture(db_engine):
    connection = db_engine.connect()

    transaction = connection.begin()
    with Session(connection) as session:
        set_session_for_factories(model_factories, session)
        yield session
        transaction.rollback()
        connection.close()


@pytest.fixture(name="app")
def app_fixture(session: Session):
    app: FastAPI = create_application()

    def get_session_override():
        return session

    def get_settings_override():
        return Settings(
            testing=1, assessments_dir=Path(__file__).parent / "test_assessments"
        )

    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_settings] = get_settings_override

    yield app
    app.dependency_overrides.clear()


@pytest.fixture(name="client")
def client_fixture(app):
    def client_for_assessment(assessment_config):
        app.dependency_overrides[get_assessment_config_file] = lambda: assessment_config
        return TestClient(app)

    return client_for_assessment
