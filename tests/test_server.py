"""Unit tests for the live dashboard HTTP server."""

import time
import socket
import pytest
import httpx

from src.server import run_server


def find_free_port() -> int:
    """Find a random available port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def dashboard_server():
    """Start server in background daemon thread and clean up after module tests."""
    port = find_free_port()
    httpd = run_server(host="127.0.0.1", port=port, open_browser=False, block=False)
    time.sleep(0.2)
    yield port
    try:
        httpd.shutdown()
        httpd.server_close()
    except Exception:
        pass


def test_server_health_endpoint(dashboard_server):
    port = dashboard_server
    url = f"http://127.0.0.1:{port}/health"

    with httpx.Client(timeout=10.0) as client:
        resp = client.get(url)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "2.7"


def test_server_dashboard_html_endpoint(dashboard_server):
    port = dashboard_server
    url = f"http://127.0.0.1:{port}/"

    with httpx.Client(timeout=10.0) as client:
        resp = client.get(url)
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "<!DOCTYPE html>" in resp.text
        assert "ATS Form Filler" in resp.text


def test_server_api_stats_endpoint(dashboard_server):
    port = dashboard_server
    url = f"http://127.0.0.1:{port}/api/stats"

    with httpx.Client(timeout=10.0) as client:
        resp = client.get(url)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_applications" in data
        assert "avg_success_rate" in data
        assert "platforms" in data


def test_server_api_tracker_endpoint(dashboard_server):
    port = dashboard_server
    url = f"http://127.0.0.1:{port}/api/tracker"

    with httpx.Client(timeout=10.0) as client:
        resp = client.get(url)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


def test_server_404_on_unknown_path(dashboard_server):
    port = dashboard_server
    url = f"http://127.0.0.1:{port}/unknown_route_xyz"

    with httpx.Client(timeout=10.0) as client:
        resp = client.get(url)
        assert resp.status_code == 404
