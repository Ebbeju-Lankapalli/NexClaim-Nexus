"""
NexClaim Authentication Tests.

Tests for registration, OTP, login, JWT, and profile endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

# Mock email sending globally for auth tests to prevent SMTP timeouts
patch("app.shared.backend.email_service.EmailService.send_otp_email", return_value=True).start()


class TestCaptcha:
    """Tests for CAPTCHA endpoint."""

    def test_get_captcha_returns_question_and_answer(self, client: TestClient):
        """CAPTCHA endpoint should return a math question and its answer."""
        response = client.get("/api/auth/captcha")
        assert response.status_code == 200
        data = response.json()
        assert "question" in data
        assert "answer" in data
        assert isinstance(data["answer"], int)


class TestRegistration:
    """Tests for policyholder registration."""

    def test_register_valid_policyholder(self, client: TestClient):
        """Valid registration should return 201 with success message."""
        response = client.post(
            "/api/auth/register",
            json={
                "full_name": "Test User",
                "email": "jahnavichevuri@gmail.com",
                "phone": "9876543210",
                "policy_number": "POL-TEST-001",
                "policy_pin": "1234",
                "password": "Test@Pass1",
                "captcha_answer": 10,
                "captcha_expected": 10,
            },
        )
        assert response.status_code == 201
        assert "Registration successful" in response.json()["message"]

    def test_register_duplicate_email_fails(self, client: TestClient):
        """Duplicate email registration should return 409."""
        data = {
            "full_name": "Duplicate User",
            "email": "dup@example.com",
            "phone": "9999999999",
            "policy_number": "POL-DUP-001",
            "policy_pin": "5678",
            "password": "Test@Pass1",
            "captcha_answer": 5,
            "captcha_expected": 5,
        }
        client.post("/api/auth/register", json=data)
        data["policy_number"] = "POL-DUP-002"
        response = client.post("/api/auth/register", json=data)
        assert response.status_code == 409

    def test_register_weak_password_fails(self, client: TestClient):
        """Weak password should return 422."""
        response = client.post(
            "/api/auth/register",
            json={
                "full_name": "Weak Pass",
                "email": "weakpass@example.com",
                "phone": "1234567890",
                "policy_number": "POL-WEAK-001",
                "policy_pin": "0000",
                "password": "weak",
                "captcha_answer": 5,
                "captcha_expected": 5,
            },
        )
        assert response.status_code == 422


class TestLogin:
    """Tests for user login."""

    def test_admin_login_succeeds(self, client: TestClient):
        """Admin login with correct credentials should return a JWT token."""
        response = client.post(
            "/api/auth/login",
            json={"email": "test_admin@nexclaim.com", "password": "Admin@Test2024", "role": "admin"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["role"] == "admin"

    def test_wrong_password_fails(self, client: TestClient):
        """Incorrect password should return 401."""
        response = client.post(
            "/api/auth/login",
            json={"email": "test_admin@nexclaim.com", "password": "WrongPassword", "role": "admin"},
        )
        assert response.status_code == 401

    def test_reviewer_login_succeeds(self, client: TestClient):
        """Reviewer login should return reviewer role token."""
        response = client.post(
            "/api/auth/login",
            json={"email": "test_reviewer@nexclaim.com", "password": "Reviewer@Test2024", "role": "reviewer", "captcha_answer": "10", "captcha_expected": "10"},
        )
        assert response.status_code == 200
        assert response.json()["role"] == "reviewer"

    def test_nonexistent_user_fails(self, client: TestClient):
        """Login for non-existent email should return 401."""
        response = client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "Whatever@1", "role": "policyholder"},
        )
        assert response.status_code == 401


class TestProfile:
    """Tests for the /me profile endpoint."""

    def test_get_profile_authenticated(self, client: TestClient, admin_token: str):
        """Authenticated request should return user profile."""
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["email"] == "test_admin@nexclaim.com"

    def test_get_profile_unauthenticated(self, client: TestClient):
        """Unauthenticated request should return 401 or 403."""
        response = client.get("/api/auth/me")
        assert response.status_code in [401, 403]
