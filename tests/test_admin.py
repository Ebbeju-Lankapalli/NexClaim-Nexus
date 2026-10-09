"""
NexClaim Admin API Tests.

Tests for policy management, reviewer management, user blocking,
and escalated claim handling.
"""

import pytest
from fastapi.testclient import TestClient


class TestAdminDashboard:
    """Tests for admin dashboard endpoint."""

    def test_dashboard_accessible_by_admin(self, client: TestClient, auth_headers: dict):
        """Admin should be able to access dashboard."""
        response = client.get("/api/admin/dashboard", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_claims" in data
        assert "total_users" in data

    def test_dashboard_denied_for_reviewer(self, client: TestClient, reviewer_headers: dict):
        """Reviewer should not access admin dashboard."""
        response = client.get("/api/admin/dashboard", headers=reviewer_headers)
        assert response.status_code == 403

    def test_dashboard_denied_without_auth(self, client: TestClient):
        """Unauthenticated request should return 401 or 403."""
        response = client.get("/api/admin/dashboard")
        assert response.status_code in [401, 403]


class TestPolicyManagement:
    """Tests for policy CRUD operations."""

    def test_create_policy_manually(self, client: TestClient, auth_headers: dict):
        """Admin should be able to create a policy manually."""
        response = client.post(
            "/api/admin/policies/manual",
            json={
                "policy_number": "TEST-POL-001",
                "policy_name": "Test Health Policy",
                "coverage_limit": 500000.0,
                "covered_diseases": ["Dengue", "Malaria", "Typhoid"],
                "waiting_period_days": 30,
                "is_active": True,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        assert response.json()["policy_id"] is not None

    def test_list_policies(self, client: TestClient, auth_headers: dict):
        """Admin should be able to list policies."""
        response = client.get("/api/admin/policies", headers=auth_headers)
        assert response.status_code == 200
        assert "items" in response.json()

    def test_duplicate_policy_fails(self, client: TestClient, auth_headers: dict):
        """Duplicate policy number should return 409."""
        policy_data = {
            "policy_number": "UNIQUE-POL-999",
            "policy_name": "Unique Policy",
            "coverage_limit": 100000.0,
            "covered_diseases": ["Fever"],
            "waiting_period_days": 0,
            "is_active": True,
        }
        client.post("/api/admin/policies/manual", json=policy_data, headers=auth_headers)
        response = client.post("/api/admin/policies/manual", json=policy_data, headers=auth_headers)
        assert response.status_code == 409


class TestReviewerManagement:
    """Tests for reviewer account management."""

    def test_create_reviewer(self, client: TestClient, auth_headers: dict):
        """Admin should be able to create a reviewer."""
        response = client.post(
            "/api/admin/reviewers",
            json={
                "full_name": "New Reviewer",
                "email": "new_reviewer_test@nexclaim.com",
                "password": "Reviewer@New2024",
                "employee_id": "EMP-100",
                "department": "Medical Claims",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201

    def test_list_reviewers(self, client: TestClient, auth_headers: dict):
        """Admin should be able to list reviewers."""
        response = client.get("/api/admin/reviewers", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestUserManagement:
    """Tests for user blocking and listing."""

    def test_list_users(self, client: TestClient, auth_headers: dict):
        """Admin should be able to list all users."""
        response = client.get("/api/admin/users", headers=auth_headers)
        assert response.status_code == 200
        assert "items" in response.json()


class TestEscalatedClaims:
    """Tests for escalated claims management."""

    def test_list_escalated_claims(self, client: TestClient, auth_headers: dict):
        """Admin should be able to list escalated claims."""
        response = client.get("/api/admin/escalated-claims", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
