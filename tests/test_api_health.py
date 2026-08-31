"""
RecoverOS — API Health Tests

Tests for the health and events endpoints.
Requires the API to be running or uses TestClient.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from apps.api.main import app

client = TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_200(self):
        """Health endpoint should return 200."""
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_health_has_status(self):
        """Health response should contain status field."""
        response = client.get("/api/health")
        data = response.json()
        assert "status" in data
        assert data["status"] in ("ok", "degraded")

    def test_health_has_version(self):
        """Health response should contain version."""
        response = client.get("/api/health")
        data = response.json()
        assert "version" in data
        assert data["version"] == "0.1.0"

    def test_health_has_database_status(self):
        """Health response should report database status."""
        response = client.get("/api/health")
        data = response.json()
        assert "database" in data
        assert data["database"] in ("connected", "disconnected")

    def test_health_has_counts(self):
        """Health response should contain counts object."""
        response = client.get("/api/health")
        data = response.json()
        assert "counts" in data
        assert "events" in data["counts"]
        assert "customers" in data["counts"]
        assert "merchants" in data["counts"]

    def test_health_has_request_id_header(self):
        """Response should include X-Request-ID header."""
        response = client.get("/api/health")
        assert "x-request-id" in response.headers


class TestEventsStatsEndpoint:
    def test_events_stats_returns_200(self):
        """Events stats endpoint should return 200."""
        response = client.get("/api/events/stats")
        assert response.status_code == 200

    def test_events_stats_has_summary(self):
        """Stats response should contain summary."""
        response = client.get("/api/events/stats")
        data = response.json()
        assert "summary" in data
        assert "total_events" in data["summary"]
        assert "total_revenue_at_risk_paise" in data["summary"]

    def test_events_stats_has_breakdowns(self):
        """Stats response should contain breakdowns."""
        response = client.get("/api/events/stats")
        data = response.json()
        assert "by_event_type" in data
        assert "by_payment_method" in data
        assert "patterns" in data
