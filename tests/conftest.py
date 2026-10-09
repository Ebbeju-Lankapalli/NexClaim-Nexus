import os

# Explicit test-only configuration; never reuse these values in deployments.
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-do-not-use-outside-tests-0123456789")
os.environ.setdefault("ADMIN_EMAIL", "")
os.environ.setdefault("ADMIN_PASSWORD", "")
os.environ.setdefault("REVIEWER_EMAIL", "")
os.environ.setdefault("REVIEWER_PASSWORD", "")

"""
NexClaim Test Configuration.

Provides shared fixtures for all test modules.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.shared.backend.database import Base, get_db
from app.shared.backend.models import Admin, Reviewer, Role, User
from app.shared.backend.security import hash_password
from app.main import app

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite:///./test.db"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    """Override database dependency with test database."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Create all tables for test database."""
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    # Seed roles
    db = TestingSessionLocal()
    try:
        for role_name in ("policyholder", "reviewer", "admin"):
            if not db.query(Role).filter(Role.name == role_name).first():
                db.add(Role(name=role_name))
        db.commit()

        # Seed admin user
        admin_role = db.query(Role).filter(Role.name == "admin").first()
        if not db.query(User).filter(User.email == "test_admin@nexclaim.com").first():
            user = User(
                full_name="Test Admin",
                email="test_admin@nexclaim.com",
                hashed_password=hash_password("Admin@Test2024"),
                role_id=admin_role.id,
                is_active=True,
                is_verified=True,
            )
            db.add(user)
            db.flush()
            db.add(Admin(user_id=user.id))
            db.commit()

        # Seed reviewer user
        reviewer_role = db.query(Role).filter(Role.name == "reviewer").first()
        if not db.query(User).filter(User.email == "test_reviewer@nexclaim.com").first():
            user = User(
                full_name="Test Reviewer",
                email="test_reviewer@nexclaim.com",
                hashed_password=hash_password("Reviewer@Test2024"),
                role_id=reviewer_role.id,
                is_active=True,
                is_verified=True,
            )
            db.add(user)
            db.flush()
            db.add(Reviewer(user_id=user.id, employee_id="T001", is_active=True))
            db.commit()
    finally:
        db.close()

    yield
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()
    import os
    if os.path.exists("test.db"):
        os.remove("test.db")


@pytest.fixture
def client():
    """Return a FastAPI TestClient."""
    return TestClient(app)


@pytest.fixture
def admin_token(client):
    """Return a JWT token for the test admin."""
    response = client.post(
        "/api/auth/login",
        json={"email": "test_admin@nexclaim.com", "password": "Admin@Test2024", "role": "admin"},
    )
    return response.json()["access_token"]


@pytest.fixture
def reviewer_token(client):
    """Return a JWT token for the test reviewer."""
    response = client.post(
        "/api/auth/login",
        json={"email": "test_reviewer@nexclaim.com", "password": "Reviewer@Test2024", "role": "reviewer", "captcha_answer": "10", "captcha_expected": "10"},
    )
    return response.json()["access_token"]


@pytest.fixture
def auth_headers(admin_token):
    """Return auth headers for the test admin."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def reviewer_headers(reviewer_token):
    """Return auth headers for the test reviewer."""
    return {"Authorization": f"Bearer {reviewer_token}"}
