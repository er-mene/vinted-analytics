import sqlite3
import pytest
from unittest.mock import patch
from datetime import datetime, timedelta
import backend.app.db.database as db


@pytest.fixture
def test_db(tmp_path):
    test_db_path = str(tmp_path / "test_vinted.db")
    with patch.object(db, "DB_NAME", test_db_path):
        db.init_db()
        yield test_db_path


def test_calculate_schedule_delay_hours():
    # Top 10 hottest (0-9): 6 hours
    assert db.calculate_schedule_delay_hours(0) == 6.0
    assert db.calculate_schedule_delay_hours(5) == 6.0
    assert db.calculate_schedule_delay_hours(9) == 6.0

    # Page 1 top (10-29): 12 hours
    assert db.calculate_schedule_delay_hours(10) == 12.0
    assert db.calculate_schedule_delay_hours(20) == 12.0
    assert db.calculate_schedule_delay_hours(29) == 12.0

    # Page 1 bottom (30-47): 18 hours
    assert db.calculate_schedule_delay_hours(30) == 18.0
    assert db.calculate_schedule_delay_hours(47) == 18.0

    # Page 2 (48-95): 24 hours
    assert db.calculate_schedule_delay_hours(48) == 24.0
    assert db.calculate_schedule_delay_hours(95) == 24.0

    # Page 3+ (96+): 36 hours
    assert db.calculate_schedule_delay_hours(96) == 36.0
    assert db.calculate_schedule_delay_hours(150) == 36.0


def test_save_listings_tiered_scheduling(test_db):
    with patch.object(db, "DB_NAME", test_db):
        monitor_id = db.create_monitor("Test Monitor", "test query", 1, 10.0, 50.0)

        items = [
            {"id": 1, "title": "Top Item", "brand": "Nike", "price": 20.0, "url": "http://1"},       # pos 0 -> 6h
            {"id": 2, "title": "Page 1 Mid", "brand": "Nike", "price": 25.0, "url": "http://2"},     # pos 1 (we'll set pos manually below or slice)
        ]
        # Let's create items at positions 0, 15, and 50
        large_items = [{"id": i, "title": f"Item {i}", "brand": "Nike", "price": 20.0, "url": f"http://{i}"} for i in range(55)]
        db.save_listings(monitor_id, large_items)

        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()

        # Item 0 (pos 0): scheduled ~ +6h
        cursor.execute("SELECT (julianday(scheduled_at) - julianday('now')) * 24 FROM verification_queue WHERE id = 0")
        diff_0 = cursor.fetchone()[0]
        assert 5.8 <= diff_0 <= 6.2

        # Item 15 (pos 15): scheduled ~ +12h
        cursor.execute("SELECT (julianday(scheduled_at) - julianday('now')) * 24 FROM verification_queue WHERE id = 15")
        diff_15 = cursor.fetchone()[0]
        assert 11.8 <= diff_15 <= 12.2

        # Item 50 (pos 50): scheduled ~ +24h
        cursor.execute("SELECT (julianday(scheduled_at) - julianday('now')) * 24 FROM verification_queue WHERE id = 50")
        diff_50 = cursor.fetchone()[0]
        assert 23.8 <= diff_50 <= 24.2

        conn.close()


def test_improving_position_advances_schedule(test_db):
    with patch.object(db, "DB_NAME", test_db):
        monitor_id = db.create_monitor("Test Monitor", "test query", 1, 10.0, 50.0)

        # Scrape 1: Item 10 is at position 60 (scheduled ~24h)
        items_1 = [{"id": i, "title": f"Item {i}", "brand": "Nike", "price": 20.0, "url": f"http://{i}"} for i in range(70)]
        db.save_listings(monitor_id, items_1)

        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT (julianday(scheduled_at) - julianday('now')) * 24 FROM verification_queue WHERE id = 60")
        assert cursor.fetchone()[0] > 20.0  # ~24h

        # Scrape 2: Item 60 jumped to position 2! (+6h)
        items_2 = [
            {"id": 1, "title": "Item 1", "brand": "Nike", "price": 20.0, "url": "http://1"},
            {"id": 2, "title": "Item 2", "brand": "Nike", "price": 20.0, "url": "http://2"},
            {"id": 60, "title": "Item 60", "brand": "Nike", "price": 20.0, "url": "http://60"},
        ]
        db.save_listings(monitor_id, items_2)

        # Item 60's scheduled_at must have been advanced to ~6h!
        cursor.execute("SELECT (julianday(scheduled_at) - julianday('now')) * 24 FROM verification_queue WHERE id = 60")
        diff_advanced = cursor.fetchone()[0]
        assert 5.8 <= diff_advanced <= 6.2
        conn.close()


def test_degrading_position_does_not_postpone_schedule(test_db):
    with patch.object(db, "DB_NAME", test_db):
        monitor_id = db.create_monitor("Test Monitor", "test query", 1, 10.0, 50.0)

        # Scrape 1: Item 10 is at pos 2 (+6h)
        items_1 = [
            {"id": 1, "title": "Item 1", "brand": "Nike", "price": 20.0, "url": "http://1"},
            {"id": 10, "title": "Item 10", "brand": "Nike", "price": 20.0, "url": "http://10"},
        ]
        db.save_listings(monitor_id, items_1)

        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT scheduled_at FROM verification_queue WHERE id = 10")
        initial_scheduled = cursor.fetchone()[0]

        # Scrape 2: Item 10 fell to pos 50 (+24h)
        items_2 = [{"id": i, "title": f"Item {i}", "brand": "Nike", "price": 20.0, "url": f"http://{i}"} for i in range(55)]
        db.save_listings(monitor_id, items_2)

        cursor.execute("SELECT scheduled_at FROM verification_queue WHERE id = 10")
        subsequent_scheduled = cursor.fetchone()[0]
        # Must retain the earlier scheduled_at
        assert subsequent_scheduled == initial_scheduled
        conn.close()


def test_get_items_to_verify_filters_future_scheduled(test_db):
    with patch.object(db, "DB_NAME", test_db):
        monitor_id = db.create_monitor("Test Monitor", "test query", 1, 10.0, 50.0)

        conn = sqlite3.connect(test_db)
        # Item 1: future (+5 hours)
        conn.execute("INSERT INTO listings (id, monitor_id, title, url, price, is_active) VALUES (1, ?, 'Future', 'http://1', 20.0, 1)", (monitor_id,))
        conn.execute("INSERT INTO verification_queue (id, url, queued_at, scheduled_at) VALUES (1, 'http://1', CURRENT_TIMESTAMP, datetime('now', '+5 hours'))")

        # Item 2: ready (-1 hour)
        conn.execute("INSERT INTO listings (id, monitor_id, title, url, price, is_active) VALUES (2, ?, 'Ready', 'http://2', 30.0, 1)", (monitor_id,))
        conn.execute("INSERT INTO verification_queue (id, url, queued_at, scheduled_at) VALUES (2, 'http://2', CURRENT_TIMESTAMP, datetime('now', '-1 hour'))")
        conn.commit()
        conn.close()

        summary = db.get_verification_queue_summary()
        assert summary["total"] == 2
        assert summary["ready"] == 1

        items = db.get_items_to_verify(max_items=5)
        # Only ready item 2 is returned
        assert len(items) == 1
        assert items[0]["id"] == 2

        # Check lease: item 2 scheduled_at is pushed +15 minutes
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT (julianday(scheduled_at) - julianday('now')) * 24 * 60 FROM verification_queue WHERE id = 2")
        lease_minutes = cursor.fetchone()[0]
        assert 13.0 <= lease_minutes <= 16.0
        conn.close()


def test_reschedule_verification(test_db):
    with patch.object(db, "DB_NAME", test_db):
        conn = sqlite3.connect(test_db)
        conn.execute("INSERT INTO verification_queue (id, url, queued_at, scheduled_at) VALUES (1, 'http://1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
        conn.commit()
        conn.close()

        db.reschedule_verification(1, delay_hours=2.0)

        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT (julianday(scheduled_at) - julianday('now')) * 24 FROM verification_queue WHERE id = 1")
        diff = cursor.fetchone()[0]
        assert 1.8 <= diff <= 2.2
        conn.close()


def test_reschedule_or_expire_active_listing(test_db):
    with patch.object(db, "DB_NAME", test_db):
        monitor_id = db.create_monitor("Test Monitor", "test query", 1, 10.0, 50.0, max_age=5.0)

        # Fresh listing (1 day old)
        conn = sqlite3.connect(test_db)
        conn.execute("INSERT INTO listings (id, monitor_id, title, url, price, is_active, listed_at) VALUES (1, ?, 'Fresh', 'http://1', 20.0, 1, datetime('now', '-1 day'))", (monitor_id,))
        conn.execute("INSERT INTO verification_queue (id, url, queued_at, scheduled_at) VALUES (1, 'http://1', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")

        # Stale listing (6 days old, max_age is 5 days)
        conn.execute("INSERT INTO listings (id, monitor_id, title, url, price, is_active, listed_at) VALUES (2, ?, 'Stale', 'http://2', 20.0, 1, datetime('now', '-6 days'))", (monitor_id,))
        conn.execute("INSERT INTO verification_queue (id, url, queued_at, scheduled_at) VALUES (2, 'http://2', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
        conn.commit()
        conn.close()

        # Rescheduling fresh item -> succeeds (+24h)
        assert db.reschedule_or_expire_active_listing(1, delay_hours=24.0) is True

        # Rescheduling stale item -> expires and removes from queue
        assert db.reschedule_or_expire_active_listing(2, delay_hours=24.0) is False

        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM verification_queue")
        remaining_ids = [row[0] for row in cursor.fetchall()]
        assert remaining_ids == [1]
        conn.close()


def test_clear_queue_preserves_listings(test_db):
    with patch.object(db, "DB_NAME", test_db):
        monitor_id = db.create_monitor("Test Monitor", "test query", 1, 10.0, 50.0, max_age=1.0)

        conn = sqlite3.connect(test_db)
        # Insert an old listing (8 days ago)
        conn.execute("""
            INSERT INTO listings (id, monitor_id, title, url, price, is_active, listed_at, last_seen_at)
            VALUES (99, ?, 'Old Shoe', 'http://shoe', 20.0, 1, datetime('now', '-8 days'), datetime('now', '-8 days'))
        """, (monitor_id,))
        # Enqueue it
        conn.execute("""
            INSERT INTO verification_queue (id, url, queued_at, scheduled_at, last_check)
            VALUES (99, 'http://shoe', datetime('now', '-1 day'), datetime('now', '-1 day'), datetime('now', '-1 day'))
        """)
        conn.commit()
        conn.close()

        assert db.get_verification_queue_summary()["total"] == 1

        # Run clear_queue
        db.clear_queue()

        # Item should be removed from verification_queue because it exceeds max_age
        assert db.get_verification_queue_summary()["total"] == 0

        # BUT the listing in listings table must NOT be deleted!
        conn = sqlite3.connect(test_db)
        row = conn.execute("SELECT id, title FROM listings WHERE id = 99").fetchone()
        conn.close()
        assert row is not None
        assert row[0] == 99
