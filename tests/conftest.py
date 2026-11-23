import pytest


@pytest.fixture
def app(tmp_path):
    from app import create_app
    from config import TestConfig
    from extensions import db
    TestConfig.UPLOAD_FOLDER = str(tmp_path / "uploads")
    TestConfig.REPORT_FOLDER = str(tmp_path / "reports")
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
