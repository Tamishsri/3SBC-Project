"""Mock Team Integration Hub & Backend Server for ATS Capstone Project.

Simulates the complete 4-person capstone ecosystem:
- Teammate Sushrith (Backend DB / API): Exposes `/api/candidates/{id}`
- Teammate Rohit (Job Board Web Scraper): Exposes `/api/jobs/unapplied`
- Teammate Saran (Resume Parser): Exposes `/api/parser/verify`
- Teammate Tamish (ATS Form Filler Suite): Dispatches & records applications
"""

from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

# Ensure project root is in sys.path
project_root = Path(__file__).resolve().parent.parent
import sys
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.contract_verifier import verify_parser_payload

logger = logging.getLogger(__name__)

# Pre-seeded candidate profiles in Sushrith's mock database
MOCK_CANDIDATE_DB: dict[str, dict[str, Any]] = {
    "tamish-01": {
        "personal": {
            "first_name": "Tamish",
            "last_name": "Sridatta",
            "email": "tamish.sridatta@example.com",
            "phone": "+919876543210",
            "linkedin_url": "https://linkedin.com/in/tamishsri",
            "github_url": "https://github.com/Tamishsri",
            "location": "Chennai, Tamil Nadu, India",
            "website": "https://tamishsri.dev",
        },
        "experience": [
            {
                "company": "3SBC Tech",
                "title": "Lead Automation Engineer",
                "start_date": "2022-01",
                "description": "Architected enterprise ATS automation framework with Playwright and Python."
            }
        ],
        "education": [
            {
                "institution": "Anna University",
                "degree": "B.Tech in Information Technology",
                "graduation_date": "2020-05",
            }
        ],
        "skills": ["Python", "Playwright", "FastAPI", "Docker", "PostgreSQL", "React", "TypeScript"],
        "cover_letter": "I am excited to submit my application for the engineering position.",
        "work_authorization": {
            "authorized_to_work": True,
            "requires_sponsorship": False,
            "notice_period_days": 30,
            "expected_salary": "$140k",
            "willing_to_relocate": True,
        },
        "demographics": {
            "gender": "Male",
            "race_ethnicity": "Asian",
            "veteran_status": "I am not a protected veteran",
            "disability_status": "No, I don't have a disability",
        }
    }
}

# Pre-seeded scraped job queue from Rohit's Web Scraper
MOCK_SCRAPED_JOBS: list[dict[str, Any]] = [
    {
        "job_id": "job_gh_01",
        "company": "Stripe",
        "role": "Senior Automation Engineer",
        "url": "https://boards.greenhouse.io/stripe/jobs/1",
        "ats_platform": "Greenhouse",
    },
    {
        "job_id": "job_wd_02",
        "company": "Plexus Global",
        "role": "Lead Infrastructure Architect",
        "url": "https://plexus.wd3.myworkdayjobs.com/Careers/job/2",
        "ats_platform": "Workday",
    },
    {
        "job_id": "job_lev_03",
        "company": "Scale AI",
        "role": "Full Stack Engineer",
        "url": "https://jobs.lever.co/scaleai/3",
        "ats_platform": "Lever",
    }
]


class TeamHubHTTPHandler(BaseHTTPRequestHandler):
    """Multi-endpoint handler simulating backend, scraper, and parser services."""

    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/health":
            self._send_json(200, {
                "service": "ATS Capstone Team Integration Hub",
                "status": "online",
                "team_members": {
                    "Tamish": "ATS Form Filler Suite (Browser CDP Automation)",
                    "Saran": "Resume Parser Service",
                    "Rohit": "Job Board Web Scraper",
                    "Sushrith": "Backend API & Candidate Database",
                },
                "endpoints": [
                    "GET /health",
                    "GET /api/candidates/<id>",
                    "GET /api/jobs/unapplied",
                    "POST /api/parser/verify",
                    "POST /api/applications/record",
                ]
            })
        elif self.path.startswith("/api/candidates/"):
            cand_id = self.path.split("/")[-1]
            if cand_id in MOCK_CANDIDATE_DB:
                self._send_json(200, MOCK_CANDIDATE_DB[cand_id])
            else:
                self._send_json(404, {"error": f"Candidate '{cand_id}' not found in Sushrith's DB."})
        elif self.path == "/api/jobs/unapplied":
            self._send_json(200, {"count": len(MOCK_SCRAPED_JOBS), "jobs": MOCK_SCRAPED_JOBS})
        else:
            self._send_json(404, {"error": "Endpoint not found"})

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"

        try:
            payload = json.loads(body)
        except Exception:
            self._send_json(400, {"error": "Invalid JSON payload"})
            return

        if self.path == "/api/parser/verify":
            # Saran's parser validation contract
            diag = verify_parser_payload(payload)
            self._send_json(200, {
                "is_valid": diag.is_valid,
                "candidate_name": diag.candidate_name,
                "compatibility_score": diag.compatibility_score,
                "missing_required": diag.missing_required,
                "type_errors": diag.type_errors,
            })
        elif self.path == "/api/applications/record":
            # Sushrith's application tracking endpoint
            self._send_json(201, {
                "status": "recorded",
                "timestamp": payload.get("timestamp"),
                "application_id": f"app_{len(MOCK_SCRAPED_JOBS) + 1}",
                "message": "Successfully recorded application state in team backend.",
            })
        else:
            self._send_json(404, {"error": "Endpoint not found"})

    def _send_json(self, status: int, data: Any) -> None:
        encoded = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug(f"[TEAM HUB] {format % args}")


def start_team_mock_server(host: str = "127.0.0.1", port: int = 8000, block: bool = True) -> ThreadingHTTPServer:
    """Start the team integration mock server."""
    server = ThreadingHTTPServer((host, port), TeamHubHTTPHandler)
    if block:
        print(f"[*] ATS Capstone Team Mock Hub running on http://{host}:{port}")
        print("[*] Press Ctrl+C to stop.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping Team Mock Hub...")
            server.shutdown()
            server.server_close()
    else:
        import threading
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
    return server


if __name__ == "__main__":
    start_team_mock_server(port=8000, block=True)
