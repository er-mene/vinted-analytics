import pytest
import sqlite3
import threading
import time
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.app.utils.perf_monitor import BottleneckMonitor, TracedConnection, trace_connection
import backend.app.db.database as db
from backend.main import app


@pytest.fixture
def monitor():
    return BottleneckMonitor(history_size=50)


def test_basic_recording_and_stats(monitor):
    monitor.record("web_scraping", "catalog_fetch", 0.15)
    monitor.record("web_scraping", "catalog_fetch", 0.25)
    monitor.record("time_sleep", "page_delay", 1.0)
    monitor.record("db_write", "insert_listings", 0.05)
    monitor.record("db_read", "select_listings", 0.02)

    stats = monitor.get_stats()
    assert stats["summary"]["web_scraping"]["count"] == 2
    assert abs(stats["summary"]["web_scraping"]["total_seconds"] - 0.40) < 0.001
    assert stats["summary"]["web_scraping"]["avg_ms"] == 200.0
    assert stats["summary"]["web_scraping"]["min_ms"] == 150.0
    assert stats["summary"]["web_scraping"]["max_ms"] == 250.0

    assert stats["summary"]["time_sleep"]["count"] == 1
    assert abs(stats["summary"]["time_sleep"]["total_seconds"] - 1.0) < 0.001

    assert stats["summary"]["db_write"]["count"] == 1
    assert abs(stats["summary"]["db_write"]["total_seconds"] - 0.05) < 0.001

    assert stats["summary"]["db_read"]["count"] == 1
    assert abs(stats["summary"]["db_read"]["total_seconds"] - 0.02) < 0.001

    # Primary bottleneck should be time_sleep since 1.0s is largest
    assert stats["primary_bottleneck"] == "time_sleep"
    assert stats["primary_bottleneck_pct"] > 60.0
    assert len(stats["insights"]) > 0


def test_context_manager_and_decorator(monitor):
    with monitor.track("web_scraping", "test_block"):
        time.sleep(0.01)

    @monitor.measure("db_write", "test_func")
    def do_work():
        time.sleep(0.01)
        return 42

    res = do_work()
    assert res == 42

    stats = monitor.get_stats()
    assert stats["summary"]["web_scraping"]["count"] == 1
    assert stats["summary"]["web_scraping"]["total_seconds"] > 0
    assert stats["summary"]["db_write"]["count"] == 1
    assert stats["summary"]["db_write"]["total_seconds"] > 0


def test_sleep_and_event_wait_tracking(monitor):
    # sleep tracking
    slept = monitor.sleep(0.01, name="test_sleep", category="time_sleep")
    assert slept >= 0.01

    # event_wait tracking
    ev = threading.Event()
    signaled = monitor.event_wait(ev, timeout=0.01, name="test_wait", category="time_sleep")
    assert not signaled

    stats = monitor.get_stats()
    assert stats["summary"]["time_sleep"]["count"] == 2
    assert stats["summary"]["time_sleep"]["total_seconds"] >= 0.02


def test_traced_connection_and_cursor(monitor):
    raw = sqlite3.connect(":memory:")
    conn = TracedConnection(raw, monitor)
    conn.row_factory = sqlite3.Row

    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);")
    cur = conn.cursor()
    cur.execute("INSERT INTO users (name) VALUES (?)", ("Bob",))
    conn.commit()

    cur.execute("SELECT * FROM users WHERE name = ?", ("Bob",))
    row = cur.fetchone()
    assert row["name"] == "Bob"

    cur.execute("SELECT * FROM users")
    all_rows = cur.fetchall()
    assert len(all_rows) == 1

    stats = monitor.get_stats()
    assert stats["summary"]["db_write"]["count"] >= 3  # create, insert, commit
    assert stats["summary"]["db_read"]["count"] >= 4   # select, fetchone, select, fetchall
    conn.close()


def test_track_scrape_session(monitor):
    with monitor.track_scrape(10, "Test Search") as ctx:
        monitor.record("web_scraping", "catalog_page_get", 0.5)
        monitor.record("time_sleep", "page_delay", 2.0)
        monitor.record("db_write", "insert_listings", 0.1)
        ctx.set_results(pages=2, items=30, new_items=5)

    stats = monitor.get_stats()
    assert stats["last_scrape"] is not None
    ls = stats["last_scrape"]
    assert ls["monitor_id"] == 10
    assert ls["monitor_name"] == "Test Search"
    assert ls["pages_fetched"] == 2
    assert ls["items_found"] == 30
    assert ls["new_items"] == 5
    assert ls["primary_bottleneck"] == "time_sleep"
    assert ls["breakdown_seconds"]["time_sleep"] >= 2.0
    assert ls["breakdown_seconds"]["web_scraping"] >= 0.5
    assert ls["breakdown_seconds"]["db_write"] >= 0.1


def test_reset_and_report_text(monitor):
    monitor.record("web_scraping", "test_get", 0.5)
    report = monitor.get_summary_text()
    assert "VINTED BOTTLENECK MONITOR" in report
    assert "web_scraping" in report

    monitor.reset()
    stats = monitor.get_stats()
    assert stats["summary"]["web_scraping"]["count"] == 0
    assert stats["summary"]["web_scraping"]["total_seconds"] == 0.0


def test_fastapi_endpoints():
    client = TestClient(app)

    # GET /api/performance
    res = client.get("/api/performance")
    assert res.status_code == 200
    data = res.json()
    assert "summary" in data
    assert "web_scraping" in data["summary"]
    assert "db_write" in data["summary"]
    assert "db_read" in data["summary"]
    assert "time_sleep" in data["summary"]
    assert "primary_bottleneck" in data

    # GET /api/performance/report
    res_rep = client.get("/api/performance/report")
    assert res_rep.status_code == 200
    assert "VINTED BOTTLENECK MONITOR" in res_rep.text

    # POST /api/performance/reset
    res_reset = client.post("/api/performance/reset")
    assert res_reset.status_code == 200
    assert "reset successfully" in res_reset.json()["message"]


def test_polling_endpoint_filter():
    import logging
    from backend.main import PollingEndpointFilter

    filt = PollingEndpointFilter()

    # 1. Successful poll request - MUST be filtered (False)
    rec_poll_overview = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:49287", "GET", "/api/overview?_=1791478266489", "1.1", 200),
        exc_info=None,
    )
    assert filt.filter(rec_poll_overview) is False

    # 2. Successful monitor progress poll - MUST be filtered (False)
    rec_poll_progress = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:49291", "GET", "/api/monitor/6/progress?_=1791478267181", "1.1", 200),
        exc_info=None,
    )
    assert filt.filter(rec_poll_progress) is False

    # 3. Successful monitor top poll - MUST be filtered (False)
    rec_poll_top = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:49291", "GET", "/api/monitor/6/top?_=1791478267181", "1.1", 200),
        exc_info=None,
    )
    assert filt.filter(rec_poll_top) is False

    # 4. Error response on poll endpoint - MUST NOT be filtered (True)
    rec_poll_err = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:49291", "GET", "/api/monitor/6/progress", "1.1", 500),
        exc_info=None,
    )
    assert filt.filter(rec_poll_err) is True

    # 5. Non-polling request (e.g. creating monitor) - MUST NOT be filtered (True)
    rec_create = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("127.0.0.1:49291", "POST", "/api/monitor", "1.1", 200),
        exc_info=None,
    )
    assert filt.filter(rec_create) is True

