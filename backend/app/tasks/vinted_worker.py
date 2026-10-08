import heapq
import json
import logging
import random
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from app.db.database import (
    get_monitor,
    get_monitors_list,
    save_listings,
    update_monitor_last_scrape,
    get_items_to_verify,
    mark_item_as_sold,
    clear_queue,
    delete_listing,
    delete_from_queue,
    update_listing_listed_at,
)
from app.services.vinted_service import search_vinted, check_item_status, ItemStatus

logger = logging.getLogger(__name__)


def _parse_last_scrape(last_scrape_str: Optional[str]) -> Optional[float]:
    if not last_scrape_str:
        return None
    try:
        dt = datetime.strptime(last_scrape_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        try:
            return datetime.fromisoformat(last_scrape_str).timestamp()
        except Exception:
            return None


def _get_interval_seconds(monitor: dict) -> int:
    d = monitor.get("interval_days") or 0
    h = monitor.get("interval_hours") or 0
    m = monitor.get("interval_minutes") or 0
    s = monitor.get("interval_seconds") or 0
    total = d * 86400 + h * 3600 + m * 60 + s
    return total if total >= 60 else 1800


class VintedWorker:
    def __init__(self, min_cooldown_seconds: float = 25.0):
        self.min_cooldown = min_cooldown_seconds
        self.running = False
        self.thread: Optional[threading.Thread] = None

        self._lock = threading.Lock()
        self._wake_up_event = threading.Event()

        # Min-heap queue: list of (nominal_next_run_ts, monitor_id)
        self._queue: list[tuple[float, int]] = []
        # Mapping: monitor_id -> nominal_next_run_ts
        self._monitor_next_runs: dict[int, float] = {}

        self._last_scrape_finished_at: float = 0.0
        self._current_running_monitor_id: Optional[int] = None

        # Scrape progress per monitor: monitor_id -> {"current": int, "total": int}
        self._progress: dict[int, dict] = {}

    def start(self):
        if self.running:
            return
        self.running = True
        self._load_monitors_from_db()
        self.thread = threading.Thread(target=self._run_loop, name="VintedWorker", daemon=True)
        self.thread.start()
        logger.info("VintedWorker started with %d active monitor(s) in queue.", len(self._monitor_next_runs))

    def stop(self):
        self.running = False
        self._wake_up_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        self.thread = None
        logger.info("VintedWorker stopped.")

    def notify(self):
        """Wakes up the worker immediately when monitors are added, updated or deleted."""
        self._wake_up_event.set()

    # ── Progress & State API ──────────────────────────────────────────────────

    def get_next_run(self, monitor_id: int) -> Optional[float]:
        with self._lock:
            return self._monitor_next_runs.get(monitor_id)

    def is_monitor_running(self, monitor_id: int) -> bool:
        with self._lock:
            return self._current_running_monitor_id == monitor_id

    def get_progress(self, monitor_id: int) -> dict:
        with self._lock:
            p = self._progress.get(monitor_id)
            is_running = (self._current_running_monitor_id == monitor_id)
            if p is None:
                return {"current": 0, "total": 0, "running": is_running}
            return {**p, "running": is_running}

    # ── Monitor Queue Management ──────────────────────────────────────────────

    def _load_monitors_from_db(self):
        """Restores the queue on startup / crash recovery."""
        with self._lock:
            self._queue.clear()
            self._monitor_next_runs.clear()

            monitors = get_monitors_list()
            now = time.time()

            for m in monitors:
                if not m.get("is_active", 1):
                    continue

                interval = _get_interval_seconds(m)
                last_scrape_ts = _parse_last_scrape(m.get("last_scrape"))

                if last_scrape_ts is not None:
                    next_run = last_scrape_ts + interval
                else:
                    # Never scraped: schedule immediately
                    next_run = now

                self._monitor_next_runs[m["id"]] = next_run
                heapq.heappush(self._queue, (next_run, m["id"]))

    def on_monitor_added(self, monitor_id: int):
        m = get_monitor(monitor_id)
        if not m or not m.get("is_active", 1):
            return

        now = time.time()
        interval = _get_interval_seconds(m)
        last_scrape_ts = _parse_last_scrape(m.get("last_scrape"))
        next_run = (last_scrape_ts + interval) if last_scrape_ts is not None else now

        with self._lock:
            self._monitor_next_runs[monitor_id] = next_run
            heapq.heappush(self._queue, (next_run, monitor_id))

        self.notify()

    def on_monitor_updated(self, monitor_id: int):
        m = get_monitor(monitor_id)
        with self._lock:
            if not m or not m.get("is_active", 1):
                self._monitor_next_runs.pop(monitor_id, None)
            else:
                interval = _get_interval_seconds(m)
                last_scrape_ts = _parse_last_scrape(m.get("last_scrape"))
                next_run = (last_scrape_ts + interval) if last_scrape_ts is not None else time.time()
                self._monitor_next_runs[monitor_id] = next_run

            # Rebuild min-heap
            self._queue = [(ts, mid) for mid, ts in self._monitor_next_runs.items()]
            heapq.heapify(self._queue)

        self.notify()

    def on_monitor_deleted(self, monitor_id: int):
        with self._lock:
            self._monitor_next_runs.pop(monitor_id, None)
            self._progress.pop(monitor_id, None)
            self._queue = [(ts, mid) for mid, ts in self._monitor_next_runs.items()]
            heapq.heapify(self._queue)

        self.notify()

    # ── Worker Main Loop ──────────────────────────────────────────────────────

    def _run_loop(self):
        while self.running:
            try:
                now = time.time()
                earliest = None

                with self._lock:
                    # Clean top of heap if any stale/removed monitors remain
                    while self._queue:
                        top_ts, top_id = self._queue[0]
                        if top_id not in self._monitor_next_runs or self._monitor_next_runs[top_id] != top_ts:
                            heapq.heappop(self._queue)
                        else:
                            break
                    if self._queue:
                        earliest = self._queue[0]

                if earliest:
                    nominal_next_run, monitor_id = earliest
                    earliest_allowed = self._last_scrape_finished_at + self.min_cooldown
                    effective_run_time = max(nominal_next_run, earliest_allowed)

                    if now >= effective_run_time:
                        # Pop and execute
                        with self._lock:
                            if self._queue and self._queue[0] == earliest:
                                heapq.heappop(self._queue)
                                self._current_running_monitor_id = monitor_id
                            else:
                                continue

                        try:
                            self._execute_monitor_scrape(monitor_id)
                        except Exception as e:
                            logger.exception("Error executing scrape for monitor %s: %s", monitor_id, e)
                        finally:
                            self._last_scrape_finished_at = time.time()
                            with self._lock:
                                self._current_running_monitor_id = None
                                self._progress.pop(monitor_id, None)

                        # Re-schedule monitor for next run
                        m = get_monitor(monitor_id)
                        if m and m.get("is_active", 1):
                            interval = _get_interval_seconds(m)
                            new_next_run = self._last_scrape_finished_at + interval
                            with self._lock:
                                self._monitor_next_runs[monitor_id] = new_next_run
                                heapq.heappush(self._queue, (new_next_run, monitor_id))
                        else:
                            with self._lock:
                                self._monitor_next_runs.pop(monitor_id, None)
                        continue
                    else:
                        # Still waiting for effective_run_time
                        wait_seconds = effective_run_time - now
                        if wait_seconds >= 12.0:
                            # Idle window is large enough: verify 1 item from verification queue
                            verified = self._verify_single_item()
                            if verified:
                                pause = min(wait_seconds - 3.0, random.uniform(8.0, 12.0))
                                if pause > 0:
                                    self._wake_up_event.wait(timeout=pause)
                                    self._wake_up_event.clear()
                                continue

                        # Wait until effective_run_time (interruptible)
                        self._wake_up_event.wait(timeout=wait_seconds)
                        self._wake_up_event.clear()
                else:
                    # No active monitors in queue: work on verification queue
                    verified = self._verify_single_item()
                    if verified:
                        self._wake_up_event.wait(timeout=random.uniform(10.0, 15.0))
                        self._wake_up_event.clear()
                    else:
                        # Idle: sleep until notified or 30s timeout
                        self._wake_up_event.wait(timeout=30.0)
                        self._wake_up_event.clear()

            except Exception:
                logger.exception("Unexpected error in VintedWorker loop.")
                time.sleep(5)

    # ── Scrape Execution ──────────────────────────────────────────────────────

    def _execute_monitor_scrape(self, monitor_id: int):
        m = get_monitor(monitor_id)
        if not m:
            return

        status_ids = json.loads(m["status_ids"]) if isinstance(m.get("status_ids"), str) else (m.get("status_ids") or [])
        max_pages = m.get("max_pages")
        page_delay_seconds = max(m.get("page_delay_seconds") or 6.0, 5.0)
        max_age = m.get("max_age") or 7.0
        search_time_seconds = min(m.get("search_time_seconds") or 5184000, int(max_age * 86400))

        logger.info("🔄 Running Monitor: %s (ID: %s)...", m["name"], monitor_id)

        def progress_cb(current: int, total: int):
            with self._lock:
                self._progress[monitor_id] = {"current": current, "total": total}

        progress_cb(0, 1)

        items = search_vinted(
            query=m["query"],
            brand_id=m["brand_id"],
            min_price=m["min_price"],
            max_price=m["max_price"],
            status_ids=status_ids,
            max_pages=max_pages,
            page_delay_seconds=page_delay_seconds,
            search_time_seconds=search_time_seconds,
            progress_callback=progress_cb,
        )

        new_count = save_listings(monitor_id, items, max_pages)
        update_monitor_last_scrape(monitor_id)
        logger.info("✅ Monitor %s completed: %d items scraped (%d new).", m["name"], len(items), new_count)

    # ── Single Item Verification ──────────────────────────────────────────────

    def _verify_single_item(self) -> bool:
        """Verifies a single listing from verification_queue. Returns True if an item was checked."""
        try:
            clear_queue()
            items = get_items_to_verify(max_items=1)
            if not items:
                return False

            item = items[0]
            try:
                result = check_item_status(item["url"])
            except Exception as e:
                logger.info("Verification failed for listing %s: %s", item["id"], e)
                return False

            status = getattr(result, "status", result)
            listed_at = getattr(result, "listed_at", None)

            if status == ItemStatus.REMOVED:
                delete_listing(item["id"])
                logger.info("Listing %s removed.", item["id"])
            elif status == ItemStatus.SOLD:
                mark_item_as_sold(item["id"], listed_at=listed_at)
                logger.info("Listing %s marked as sold (listed_at: %s).", item["id"], listed_at)
            elif status == ItemStatus.ERROR:
                logger.warning("Verification failed for listing %s.", item["id"])
            elif status == ItemStatus.ACTIVE:
                if listed_at:
                    update_listing_listed_at(item["id"], listed_at)
                delete_from_queue(item["id"])
                logger.info("Listing %s verified active – removed from queue (listed_at: %s).", item["id"], listed_at)
            return True
        except Exception:
            logger.exception("Single item verification failed.")
            return False


vinted_worker = VintedWorker()
