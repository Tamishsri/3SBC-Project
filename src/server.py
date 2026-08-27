"""Embedded Live Dashboard HTTP server for real-time monitoring.

Spins up a lightweight local web server to display the application pipeline
dashboard and exposes JSON analytics endpoints with dynamic polling.
Zero external server dependencies required (uses standard library http.server).
"""

from __future__ import annotations

import json
import logging
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from src.exporter import build_html_dashboard_content
from src.tracker import load_tracker

logger = logging.getLogger(__name__)


class DashboardHTTPRequestHandler(BaseHTTPRequestHandler):
    """Custom multi-threaded HTTP handler serving live dashboard and API stats."""

    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        if self.path in ("/", "/dashboard", "/index.html"):
            self._serve_dashboard_html()
        elif self.path == "/api/stats":
            self._serve_api_stats()
        elif self.path == "/api/tracker":
            self._serve_api_tracker()
        elif self.path == "/health":
            self._serve_health()
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def _serve_dashboard_html(self) -> None:
        """Regenerate and return the latest dashboard HTML in-memory."""
        try:
            content = build_html_dashboard_content()

            # Inject auto-refresh poll script before </body>
            live_refresh_script = """
            <script>
                // Live background poller every 5 seconds
                setInterval(async () => {
                    try {
                        const res = await fetch('/api/stats');
                        if (res.ok) {
                            const data = await res.json();
                            const liveBadge = document.querySelector('.badge-live');
                            if (liveBadge) liveBadge.innerText = 'Live Synced: ' + new Date().toLocaleTimeString();
                        }
                    } catch (e) {
                        console.warn('Dashboard poll error:', e);
                    }
                }, 5000);
            </script>
            """
            if "</body>" in content:
                content = content.replace("</body>", f"{live_refresh_script}\n</body>")

            body = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            # Client disconnected early
            pass
        except Exception as exc:
            try:
                self.send_response(500)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(f"Server Error: {exc}".encode("utf-8"))
            except Exception:
                pass

    def _serve_api_stats(self) -> None:
        """Return aggregated application stats as JSON."""
        entries = load_tracker()
        total = len(entries)
        platforms: dict[str, int] = {}
        total_rate = 0.0

        for e in entries:
            plat = e.get("ats_platform", "Unknown")
            platforms[plat] = platforms.get(plat, 0) + 1
            try:
                total_rate += float(e.get("success_rate_pct", 0))
            except ValueError:
                pass

        avg_rate = (total_rate / total) if total > 0 else 0.0

        stats = {
            "total_applications": total,
            "avg_success_rate": round(avg_rate, 1),
            "platforms": platforms,
            "recent_count": min(total, 10),
        }
        body = json.dumps(stats, indent=2).encode("utf-8")
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def _serve_api_tracker(self) -> None:
        """Return all raw application rows as JSON."""
        entries = load_tracker()
        body = json.dumps(entries, indent=2).encode("utf-8")
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def _serve_health(self) -> None:
        body = json.dumps({"status": "ok", "version": "2.5"}).encode("utf-8")
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress noisy standard HTTP logs in production console
        logger.debug("[HTTP SERVER] %s", format % args)


def run_server(
    host: str = "127.0.0.1",
    port: int = 8080,
    open_browser: bool = True,
    block: bool = True,
) -> ThreadingHTTPServer:
    """Start the live dashboard HTTP server.

    Args:
        host: Host IP to bind (default 127.0.0.1).
        port: Port number (default 8080).
        open_browser: Whether to automatically launch default web browser.
        block: If True, blocks on serve_forever(); if False, starts in background thread.

    Returns:
        ThreadingHTTPServer instance.
    """
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, DashboardHTTPRequestHandler)
    url = f"http://{host}:{port}/"

    logger.info("[SERVER] Live Dashboard running at: %s", url)

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    if block:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("[SERVER] Dashboard server stopped by user.")
            httpd.server_close()
    else:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

    return httpd
