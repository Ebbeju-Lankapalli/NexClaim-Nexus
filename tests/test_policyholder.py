"""
NexClaim Policyholder API Tests.

Tests for policyholder dashboard and claim operations.
"""

import pytest
from fastapi.testclient import TestClient


class TestPolicyholderDashboard:
    """Tests for policyholder dashboard access control."""

    def test_dashboard_denied_for_reviewer(self, client: TestClient, reviewer_headers: dict):
        """Reviewer should not access policyholder dashboard."""
        response = client.get("/api/policyholder/dashboard", headers=reviewer_headers)
        assert response.status_code == 403

    def test_dashboard_denied_without_auth(self, client: TestClient):
        """Unauthenticated request should return 401 or 403."""
        response = client.get("/api/policyholder/dashboard")
        assert response.status_code in [401, 403]


class TestClaimList:
    """Tests for policyholder claim listing."""

    def test_claim_list_requires_auth(self, client: TestClient):
        """Unauthenticated claim list should return 401 or 403."""
        response = client.get("/api/policyholder/claims")
        assert response.status_code in [401, 403]
