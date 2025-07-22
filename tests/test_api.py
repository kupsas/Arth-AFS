"""Tests for Arth API endpoints."""

import pytest
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


class TestHealthCheck:
    """Test health check endpoint."""

    def test_health_check(self):
        """Test health check endpoint returns 200."""
        response = client.get("/v1/healthz")
        assert response.status_code == 200
        assert response.json() == {
            "status": "healthy",
            "service": "arth"
        }


class TestRootEndpoint:
    """Test root endpoint."""

    def test_root_endpoint(self):
        """Test root endpoint returns HTML."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Arth" in response.text
        assert "Personal Finance System" in response.text


class TestAPIDocumentation:
    """Test API documentation endpoints."""

    def test_docs_endpoint(self):
        """Test that docs endpoint exists."""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_redoc_endpoint(self):
        """Test that redoc endpoint exists."""
        response = client.get("/redoc")
        assert response.status_code == 200 