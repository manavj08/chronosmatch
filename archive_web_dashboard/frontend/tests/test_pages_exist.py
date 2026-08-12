"""
frontend/tests/test_pages_exist.py
------------------------------------
Day 2: MEMBER C's frontend test scaffold.

The project has no JS build tooling (no npm/node setup anywhere), so
these tests run with plain pytest against the static HTML files
directly --- structural checks only (page exists, correct scripts are
referenced). Real behavioral tests (API calls succeed, WebSocket
reconnects, buttons trigger requests) need a browser/DOM and land once
api.js / websocket.js are actually wired to a live backend
(see TASKS.md, Day 15+).
"""

from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parent.parent

EXPECTED_PAGES = [
    "index.html",
    "dashboard.html",
    "orderbook.html",
    "trades.html",
    "analytics.html",
    "logs.html",
    "settings.html",
]


def test_all_expected_pages_exist():
    for page in EXPECTED_PAGES:
        assert (FRONTEND_DIR / page).exists(), f"missing {page}"


def test_dashboard_references_chart_and_websocket_scripts():
    html = (FRONTEND_DIR / "dashboard.html").read_text(encoding="utf-8")
    for script in ["dashboard.js", "websocket.js", "charts.js"]:
        assert script in html, f"dashboard.html does not reference {script}"


def test_api_js_not_yet_linked_in_dashboard():
    """Known gap as of Day 2: api.js exists as a file but dashboard.html
    never includes a <script> tag for it. Documented here rather than
    silently fixed, since wiring api.js for real is Member C's Day 15
    task (see TASKS.md) --- adding the <script> tag now, before the
    file has any content, would just load an empty script."""
    html = (FRONTEND_DIR / "dashboard.html").read_text(encoding="utf-8")
    assert "api.js" not in html


def test_pages_have_viewport_meta_for_responsiveness():
    for page in EXPECTED_PAGES:
        html = (FRONTEND_DIR / page).read_text(encoding="utf-8")
        assert "viewport" in html, f"{page} missing responsive viewport meta tag"
