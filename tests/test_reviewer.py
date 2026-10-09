"""
NexClaim Reviewer API Tests.

Tests for reviewer dashboard and claim review workflow.
"""

import pytest
from fastapi.testclient import TestClient


class TestReviewerDashboard:
    """Tests for reviewer dashboard."""

    def test_dashboard_accessible_by_reviewer(self, client: TestClient, reviewer_headers: dict):
        """Reviewer should access dashboard."""
        response = client.get("/api/reviewer/dashboard", headers=reviewer_headers)
        assert response.status_code == 200
        data = response.json()
        assert "pending_claims" in data

    def test_dashboard_denied_for_admin(self, client: TestClient, auth_headers: dict):
        """Admin should not access reviewer dashboard."""
        response = client.get("/api/reviewer/dashboard", headers=auth_headers)
        assert response.status_code == 403


class TestReviewerClaimList:
    """Tests for reviewer claim queue."""

    def test_list_claims_returns_paginated_result(self, client: TestClient, reviewer_headers: dict):
        """Reviewer should get paginated claims list."""
        response = client.get("/api/reviewer/claims", headers=reviewer_headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    def test_list_claims_unauthenticated(self, client: TestClient):
        """Unauthenticated request should return 401 or 403."""
        response = client.get("/api/reviewer/claims")
        assert response.status_code in [401, 403]


class TestReviewerDecision:
    """Tests for reviewer decision endpoints."""

    def test_nonexistent_claim_returns_404(self, client: TestClient, reviewer_headers: dict):
        """Decision on non-existent claim should return 404."""
        response = client.post(
            "/api/reviewer/claims/99999/decision",
            json={"decision": "APPROVED", "comments": "Test"},
            headers=reviewer_headers,
        )
        assert response.status_code == 404
