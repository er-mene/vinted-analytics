import os
import sqlite3
import pytest
from unittest.mock import patch
import backend.app.db.database as db

@pytest.fixture
def test_db(tmp_path):
    test_db_path = str(tmp_path / "test_vinted.db")
    with patch.object(db, "DB_NAME", test_db_path):
        db.init_db()
        yield test_db_path


def test_pivot_ignores_promoted_listings():
    prev_data = {
        101: {"position": 10, "price": 20.0, "has_been_promoted": 0},
        102: {"position": 200, "price": 50.0, "has_been_promoted": 1},
    }
    items = [
        {"id": 102, "price": 50.0, "has_been_promoted": 1},  # promoted item jumped to pos 0
        {"id": 201, "price": 15.0, "has_been_promoted": 0},
        {"id": 101, "price": 20.0, "has_been_promoted": 0},  # organic item at pos 2
    ]
    pivot = db._calculate_scrape_pivot(items, prev_data)
    assert pivot == 10  # Must be 10 from organic item, NOT 200 from promoted item


def test_pivot_ignores_extreme_outliers():
    prev_data = {
        101: {"position": 5, "price": 20.0, "has_been_promoted": 0},
        102: {"position": 12, "price": 30.0, "has_been_promoted": 0},
        103: {"position": 180, "price": 40.0, "has_been_promoted": 0},
    }
    items = [
        {"id": 103, "price": 40.0, "has_been_promoted": 0},  # jumped 180 positions (outlier)
        {"id": 101, "price": 20.0, "has_been_promoted": 0},
        {"id": 102, "price": 30.0, "has_been_promoted": 0},
    ]
    pivot = db._calculate_scrape_pivot(items, prev_data)
    assert pivot == 12  # Must ignore the 180 outlier


def test_pivot_negative_when_no_common_items():
    prev_data = {
        101: {"position": 5, "price": 20.0, "has_been_promoted": 0},
    }
    items = [
        {"id": 999, "price": 100.0, "has_been_promoted": 0},
    ]
    pivot = db._calculate_scrape_pivot(items, prev_data)
    assert pivot == -1


def test_consecutive_misses_and_queueing(test_db):
    with patch.object(db, "DB_NAME", test_db):
        monitor_id = db.create_monitor("Test Monitor", "test query", 1, 10.0, 50.0)

        # Scrape 1: Save items A (1), B (2), C (3)
        items_1 = [
            {"id": 1, "title": "Item A", "brand": "Nike", "price": 20.0, "url": "http://a", "has_been_promoted": 0},
            {"id": 2, "title": "Item B", "brand": "Nike", "price": 25.0, "url": "http://b", "has_been_promoted": 0},
            {"id": 3, "title": "Item C", "brand": "Nike", "price": 30.0, "url": "http://c", "has_been_promoted": 0},
        ]
        db.save_listings(monitor_id, items_1)

        # Verification queue should be empty
        assert db.get_verification_queue_summary()["total"] == 0

        # Scrape 2: Item B (id 2) is missing for the 1st time
        # New item D at top, then A, then C
        items_2 = [
            {"id": 4, "title": "Item D", "brand": "Nike", "price": 15.0, "url": "http://d", "has_been_promoted": 0},
            {"id": 1, "title": "Item A", "brand": "Nike", "price": 20.0, "url": "http://a", "has_been_promoted": 0},
            {"id": 3, "title": "Item C", "brand": "Nike", "price": 30.0, "url": "http://c", "has_been_promoted": 0},
        ]
        db.save_listings(monitor_id, items_2)

        # After 1st miss, Item B should NOT be in verification_queue yet (needs confirmation)
        assert db.get_verification_queue_summary()["total"] == 0
        active_items = db.get_active_positions_for_monitor(monitor_id)
        assert active_items[2]["consecutive_misses"] == 1

        # Scrape 3: Item B is missing for the 2nd consecutive time
        items_3 = [
            {"id": 4, "title": "Item D", "brand": "Nike", "price": 15.0, "url": "http://d", "has_been_promoted": 0},
            {"id": 1, "title": "Item A", "brand": "Nike", "price": 20.0, "url": "http://a", "has_been_promoted": 0},
            {"id": 3, "title": "Item C", "brand": "Nike", "price": 30.0, "url": "http://c", "has_been_promoted": 0},
        ]
        db.save_listings(monitor_id, items_3)

        # After 2nd consecutive miss, Item B MUST be enqueued into verification_queue!
        queue_items = db.get_verification_queue_items()
        assert len(queue_items) == 1
        assert queue_items[0]["id"] == 2

        # Scrape 4: Item B reappears! (false alarm resolved)
        items_4 = [
            {"id": 2, "title": "Item B", "brand": "Nike", "price": 25.0, "url": "http://b", "has_been_promoted": 0},
            {"id": 1, "title": "Item A", "brand": "Nike", "price": 20.0, "url": "http://a", "has_been_promoted": 0},
        ]
        db.save_listings(monitor_id, items_4)

        # Reappearing item must be removed from verification_queue immediately!
        assert db.get_verification_queue_summary()["total"] == 0
        active_items = db.get_active_positions_for_monitor(monitor_id)
        assert active_items[2]["consecutive_misses"] == 0


def test_pivot_negative_does_not_dump_queue(test_db):
    with patch.object(db, "DB_NAME", test_db):
        monitor_id = db.create_monitor("Test Monitor", "test query", 1, 10.0, 50.0)

        # Scrape 1: Save items A, B
        items_1 = [
            {"id": 1, "title": "Item A", "brand": "Nike", "price": 20.0, "url": "http://a", "has_been_promoted": 0},
            {"id": 2, "title": "Item B", "brand": "Nike", "price": 25.0, "url": "http://b", "has_been_promoted": 0},
        ]
        db.save_listings(monitor_id, items_1)

        # Scrape 2: Completely new items (pivot < 0)
        items_2 = [
            {"id": 10, "title": "Item X", "brand": "Nike", "price": 30.0, "url": "http://x", "has_been_promoted": 0},
            {"id": 11, "title": "Item Y", "brand": "Nike", "price": 35.0, "url": "http://y", "has_been_promoted": 0},
        ]
        db.save_listings(monitor_id, items_2)

        # Should NOT dump previous items into verification queue
        assert db.get_verification_queue_summary()["total"] == 0


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
            INSERT INTO verification_queue (id, url, queued_at, last_check)
            VALUES (99, 'http://shoe', datetime('now', '-1 day'), datetime('now', '-1 day'))
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


def test_deferred_zombie_enqueuing(test_db):
    with patch.object(db, "DB_NAME", test_db):
        monitor_id = db.create_monitor("Test Monitor", "test query", 1, 10.0, 50.0)

        # Scrape 1: Save item 1 (pos 0) and item 2 (pos 1)
        items_1 = [
            {"id": 1, "title": "Item A", "brand": "Nike", "price": 20.0, "url": "http://a", "has_been_promoted": 0},
            {"id": 2, "title": "Item B", "brand": "Nike", "price": 25.0, "url": "http://b", "has_been_promoted": 0},
        ]
        db.save_listings(monitor_id, items_1)

        # Manually simulate item 2 being past pivot and unseen for 3 days
        conn = sqlite3.connect(test_db)
        conn.execute("UPDATE listings SET last_seen_at = datetime('now', '-3 days'), scrape_position = 100 WHERE id = 2")
        conn.commit()
        conn.close()

        # Scrape 2: Only item 1 is returned (pivot will be pos 0)
        items_2 = [
            {"id": 1, "title": "Item A", "brand": "Nike", "price": 20.0, "url": "http://a", "has_been_promoted": 0},
        ]
        db.save_listings(monitor_id, items_2)

        # Item 2 (position 100 > pivot 0) was unseen for 3 days >= QUEUE_ZOMBIE_THRESHOLD_DAYS (2 days)
        # It must be picked up by the deferred queue!
        queue_items = db.get_verification_queue_items()
        assert len(queue_items) == 1
        assert queue_items[0]["id"] == 2


def test_pivot_capped_at_scrape_depth():
    prev_data = {
        101: {"position": 50, "price": 20.0, "has_been_promoted": 0},
    }
    # Only 5 items returned
    items = [
        {"id": 201, "price": 10.0, "has_been_promoted": 0},
        {"id": 202, "price": 10.0, "has_been_promoted": 0},
        {"id": 203, "price": 10.0, "has_been_promoted": 0},
        {"id": 204, "price": 10.0, "has_been_promoted": 0},
        {"id": 101, "price": 20.0, "has_been_promoted": 0},  # at curr_pos 4, but old_pos is 50
    ]
    pivot = db._calculate_scrape_pivot(items, prev_data)
    # The old_pos 50 is an extreme shift (curr_pos 4 < old_pos - 15) so it should be skipped
    assert pivot == -1

