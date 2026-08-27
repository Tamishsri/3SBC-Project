"""Integration tests for the Team Integration Gateway Mock Backend."""

from __future__ import annotations

import socket
import threading
import time
import httpx
import pytest

from scripts.mock_team_backend import start_team_mock_server


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def team_hub_server():
    port = find_free_port()
    server = start_team_mock_server(host="127.0.0.1", port=port, block=False)
    time.sleep(0.2)  # Give time to bind
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


def test_team_hub_health(team_hub_server: str):
    """Verify team hub health endpoint returns team member roles."""
    with httpx.Client(base_url=team_hub_server, timeout=5.0) as client:
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "online"
        assert "Tamish" in data["team_members"]
        assert "Saran" in data["team_members"]
        assert "Rohit" in data["team_members"]
        assert "Sushrith" in data["team_members"]


def test_team_hub_get_candidate(team_hub_server: str):
    """Verify Sushrith's candidate DB endpoint returns pre-seeded candidate."""
    with httpx.Client(base_url=team_hub_server, timeout=5.0) as client:
        r = client.get("/api/candidates/tamish-01")
        assert r.status_code == 200
        cand = r.json()
        assert cand["personal"]["first_name"] == "Tamish"
        assert cand["personal"]["email"] == "tamish.sridatta@example.com"


def test_team_hub_candidate_not_found(team_hub_server: str):
    """Verify non-existent candidate returns 404."""
    with httpx.Client(base_url=team_hub_server, timeout=5.0) as client:
        r = client.get("/api/candidates/unknown-user")
        assert r.status_code == 404


def test_team_hub_get_scraped_jobs(team_hub_server: str):
    """Verify Rohit's scraper endpoint returns queued application URLs."""
    with httpx.Client(base_url=team_hub_server, timeout=5.0) as client:
        r = client.get("/api/jobs/unapplied")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] >= 3
        platforms = [j["ats_platform"] for j in data["jobs"]]
        assert "Greenhouse" in platforms
        assert "Workday" in platforms


def test_team_hub_parser_verify(team_hub_server: str):
    """Verify Saran's resume parser payload verification endpoint."""
    with httpx.Client(base_url=team_hub_server, timeout=5.0) as client:
        payload = {
            "personal": {
                "first_name": "Saran",
                "last_name": "Kumar",
                "email": "saran@example.com",
                "phone": "+919876543210",
            },
            "experience": [
                {
                    "company": "AI Labs",
                    "title": "ML Engineer",
                    "start_date": "2022-01",
                }
            ],
            "education": [
                {
                    "institution": "University",
                    "degree": "B.S. in CS",
                }
            ],
            "skills": ["NLP", "Python"],
        }
        r = client.post("/api/parser/verify", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["is_valid"] is True
        assert data["compatibility_score"] == 100.0


def test_team_hub_record_application(team_hub_server: str):
    """Verify recording an application state in the team backend."""
    with httpx.Client(base_url=team_hub_server, timeout=5.0) as client:
        payload = {
            "candidate_id": "tamish-01",
            "job_url": "https://boards.greenhouse.io/stripe/jobs/1",
            "status": "staged_for_review",
            "success_rate_pct": 100.0,
        }
        r = client.post("/api/applications/record", json=payload)
        assert r.status_code == 201
        data = r.json()
        assert data["status"] == "recorded"
        assert "application_id" in data
