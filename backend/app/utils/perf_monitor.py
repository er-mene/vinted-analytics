"""
Performance & Bottleneck Monitoring System for Vinted Analytics.

Tracks runtime spent in:
  - web_scraping: HTTP network calls to Vinted (catalog search, session warmup, item verification)
  - db_write: SQLite INSERT, UPDATE, DELETE, transactions, commits
  - db_read: SQLite SELECT queries and result fetching
  - time_sleep: Rate-limiting pauses (page delay, warmup delay, worker cooldown, idle waits)
  - other: CPU processing (HTML/JSON parsing, scheduling, in-memory computations)
"""

import collections
import functools
import logging
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("perf_monitor")

CATEGORIES = ("web_scraping", "db_write", "db_read", "time_sleep", "other")


class OperationStats:
    """Statistics for a single named operation."""
    __slots__ = ("name", "category", "count", "total_seconds", "min_seconds", "max_seconds", "last_occurred_at")

    def __init__(self, name: str, category: str):
        self.name = name
        self.category = category
        self.count: int = 0
        self.total_seconds: float = 0.0
        self.min_seconds: float = float("inf")
        self.max_seconds: float = 0.0
        self.last_occurred_at: Optional[str] = None

    def record(self, duration: float):
        self.count += 1
        self.total_seconds += duration
        if duration < self.min_seconds:
            self.min_seconds = duration
        if duration > self.max_seconds:
            self.max_seconds = duration
        self.last_occurred_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self, total_category_seconds: float = 0.0) -> dict:
        avg_ms = (self.total_seconds / self.count * 1000.0) if self.count > 0 else 0.0
        min_ms = (self.min_seconds * 1000.0) if self.count > 0 else 0.0
        max_ms = (self.max_seconds * 1000.0) if self.count > 0 else 0.0
        pct = (self.total_seconds / total_category_seconds * 100.0) if total_category_seconds > 0 else 0.0
        return {
            "name": self.name,
            "category": self.category,
            "count": self.count,
            "total_seconds": round(self.total_seconds, 4),
            "percentage_of_category": round(pct, 2),
            "avg_ms": round(avg_ms, 2),
            "min_ms": round(min_ms, 2),
            "max_ms": round(max_ms, 2),
            "last_occurred_at": self.last_occurred_at,
        }


class CategoryStats:
    """Cumulative statistics for an entire operation category."""
    __slots__ = ("category", "count", "total_seconds", "min_seconds", "max_seconds", "operations")

    def __init__(self, category: str):
        self.category = category
        self.count: int = 0
        self.total_seconds: float = 0.0
        self.min_seconds: float = float("inf")
        self.max_seconds: float = 0.0
        self.operations: Dict[str, OperationStats] = {}

    def record(self, op_name: str, duration: float):
        self.count += 1
        self.total_seconds += duration
        if duration < self.min_seconds:
            self.min_seconds = duration
        if duration > self.max_seconds:
            self.max_seconds = duration

        if op_name not in self.operations:
            self.operations[op_name] = OperationStats(op_name, self.category)
        self.operations[op_name].record(duration)

    def to_dict(self, total_program_seconds: float = 0.0) -> dict:
        avg_ms = (self.total_seconds / self.count * 1000.0) if self.count > 0 else 0.0
        min_ms = (self.min_seconds * 1000.0) if self.count > 0 else 0.0
        max_ms = (self.max_seconds * 1000.0) if self.count > 0 else 0.0
        pct = (self.total_seconds / total_program_seconds * 100.0) if total_program_seconds > 0 else 0.0
        
        ops_sorted = sorted(
            [op.to_dict(self.total_seconds) for op in self.operations.values()],
            key=lambda x: x["total_seconds"],
            reverse=True,
        )

        return {
            "category": self.category,
            "count": self.count,
            "total_seconds": round(self.total_seconds, 4),
            "percentage": round(pct, 2),
            "avg_ms": round(avg_ms, 2),
            "min_ms": round(min_ms, 2),
            "max_ms": round(max_ms, 2),
            "operations": ops_sorted,
        }


class ScrapeRunContext:
    """Context manager to measure runtime breakdown of an individual monitor scrape cycle."""

    def __init__(self, monitor, monitor_id: int, monitor_name: str):
        self.monitor = monitor
        self.monitor_id = monitor_id
        self.monitor_name = monitor_name
        self.start_ts = 0.0
        self.start_snapshot: Dict[str, float] = {}
        self.pages_fetched: int = 0
        self.items_found: int = 0
        self.new_items: int = 0

    def set_results(self, pages: int = 0, items: int = 0, new_items: int = 0):
        self.pages_fetched = pages
        self.items_found = items
        self.new_items = new_items

    def __enter__(self):
        self.start_ts = time.perf_counter()
        with self.monitor._lock:
            for cat in ("web_scraping", "db_write", "db_read", "time_sleep"):
                self.start_snapshot[cat] = self.monitor._categories[cat].total_seconds
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.perf_counter() - self.start_ts
        deltas = {}
        tracked_sum = 0.0

        with self.monitor._lock:
            for cat in ("web_scraping", "db_write", "db_read", "time_sleep"):
                curr = self.monitor._categories[cat].total_seconds
                diff = max(0.0, curr - self.start_snapshot.get(cat, 0.0))
                deltas[cat] = round(diff, 4)
                tracked_sum += diff

        other = max(0.0, duration - tracked_sum)
        deltas["other"] = round(other, 4)

        # Percentages
        percentages = {}
        for cat, val in deltas.items():
            percentages[cat] = round((val / duration * 100.0) if duration > 0 else 0.0, 1)

        # Determine primary bottleneck
        sorted_cats = sorted(deltas.items(), key=lambda x: x[1], reverse=True)
        primary_bottleneck = sorted_cats[0][0] if sorted_cats else "unknown"

        result = {
            "monitor_id": self.monitor_id,
            "monitor_name": self.monitor_name,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(duration, 3),
            "pages_fetched": self.pages_fetched,
            "items_found": self.items_found,
            "new_items": self.new_items,
            "breakdown_seconds": deltas,
            "breakdown_percentages": percentages,
            "primary_bottleneck": primary_bottleneck,
            "error": str(exc_val) if exc_val else None,
        }

        with self.monitor._lock:
            self.monitor.last_scrape = result
            self.monitor.recent_scrapes.append(result)

        # Log concise performance report
        logger.info(
            "⏱️ [Bottleneck Profile] Monitor '%s' scrape finished in %.2fs | "
            "sleep: %.2fs (%s%%) | scraping: %.2fs (%s%%) | db_write: %.2fs (%s%%) | db_read: %.2fs (%s%%) | other: %.2fs (%s%%) -> Bottleneck: %s",
            self.monitor_name,
            duration,
            deltas["time_sleep"],
            percentages["time_sleep"],
            deltas["web_scraping"],
            percentages["web_scraping"],
            deltas["db_write"],
            percentages["db_write"],
            deltas["db_read"],
            percentages["db_read"],
            deltas["other"],
            percentages["other"],
            primary_bottleneck,
        )


class BottleneckMonitor:
    """Central singleton to record, aggregate, and analyze performance bottlenecks."""

    def __init__(self, history_size: int = 100):
        self._lock = threading.RLock()
        self.start_time = time.time()
        self.history_size = history_size
        self._categories: Dict[str, CategoryStats] = {cat: CategoryStats(cat) for cat in CATEGORIES}
        self.recent_events: collections.deque = collections.deque(maxlen=history_size)
        self.last_scrape: Optional[dict] = None
        self.recent_scrapes: collections.deque = collections.deque(maxlen=20)
        self._orig_sleep = time.sleep
        self._is_sleep_patched = False

    def reset(self):
        """Resets all cumulative statistics and event history."""
        with self._lock:
            self.start_time = time.time()
            self._categories = {cat: CategoryStats(cat) for cat in CATEGORIES}
            self.recent_events.clear()
            self.last_scrape = None
            self.recent_scrapes.clear()

    def record(self, category: str, name: str, duration: float, metadata: Optional[dict] = None):
        """Records an operation duration in seconds."""
        if category not in self._categories:
            category = "other"

        with self._lock:
            self._categories[category].record(name, duration)
            self.recent_events.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "category": category,
                "name": name,
                "duration_ms": round(duration * 1000.0, 2),
                "metadata": metadata or {},
            })

    def track(self, category: str, name: str, metadata: Optional[dict] = None):
        """Context manager to measure runtime of a block."""
        return _BlockContext(self, category, name, metadata)

    def measure(self, category: str, name: Optional[str] = None):
        """Function decorator to measure execution time."""
        def decorator(func: Callable):
            op_name = name or func.__name__

            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                t0 = time.perf_counter()
                try:
                    return func(*args, **kwargs)
                finally:
                    dt = time.perf_counter() - t0
                    self.record(category, op_name, dt)
            return wrapper
        return decorator

    def sleep(self, seconds: float, name: str = "time.sleep", category: str = "time_sleep", metadata: Optional[dict] = None) -> float:
        """Executes time.sleep and accurately logs the idle sleep time."""
        t0 = time.perf_counter()
        self._orig_sleep(seconds)
        dt = time.perf_counter() - t0
        self.record(category, name, dt, metadata)
        return dt

    def event_wait(
        self,
        event: threading.Event,
        timeout: Optional[float],
        name: str = "event_wait",
        category: str = "time_sleep",
        metadata: Optional[dict] = None,
    ) -> bool:
        """Executes Event.wait(timeout) and logs the wait time under rate-limiting / sleep."""
        t0 = time.perf_counter()
        signaled = event.wait(timeout=timeout)
        dt = time.perf_counter() - t0
        self.record(category, name, dt, metadata)
        return signaled

    def track_scrape(self, monitor_id: int, monitor_name: str) -> ScrapeRunContext:
        """Returns a ScrapeRunContext to trace a complete monitor scrape execution."""
        return ScrapeRunContext(self, monitor_id, monitor_name)

    def patch_time_sleep(self):
        """Patches time.sleep globally to record uninstrumented sleeps automatically."""
        if self._is_sleep_patched:
            return
        orig_sleep = self._orig_sleep

        def patched_sleep(seconds):
            t0 = time.perf_counter()
            orig_sleep(seconds)
            dt = time.perf_counter() - t0
            self.record("time_sleep", "generic_sleep", dt)

        time.sleep = patched_sleep
        self._is_sleep_patched = True

    # ── Analytics & Statistics ────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Returns comprehensive performance metrics and bottleneck analysis."""
        with self._lock:
            uptime = max(0.001, time.time() - self.start_time)
            
            # Sum up tracked time
            tracked_total = sum(c.total_seconds for c in self._categories.values())
            
            # The difference between total wall clock and tracked time is CPU / unmonitored processing
            other_seconds = max(0.0, uptime - tracked_total)
            
            # Total considered for percentages is tracked_total (or uptime if desired)
            base_total = max(0.001, tracked_total)

            summary = {}
            for cat in CATEGORIES:
                c_stats = self._categories[cat]
                avg_ms = (c_stats.total_seconds / c_stats.count * 1000.0) if c_stats.count > 0 else 0.0
                min_ms = (c_stats.min_seconds * 1000.0) if c_stats.count > 0 and c_stats.min_seconds != float("inf") else 0.0
                max_ms = (c_stats.max_seconds * 1000.0) if c_stats.count > 0 else 0.0
                pct = (c_stats.total_seconds / base_total * 100.0) if base_total > 0 else 0.0

                summary[cat] = {
                    "total_seconds": round(c_stats.total_seconds, 4),
                    "percentage": round(pct, 2),
                    "count": c_stats.count,
                    "avg_ms": round(avg_ms, 2),
                    "min_ms": round(min_ms, 2),
                    "max_ms": round(max_ms, 2),
                }

            # Operations breakdown
            operations = {}
            all_ops = []
            for cat in CATEGORIES:
                c_stats = self._categories[cat]
                ops_list = [op.to_dict(c_stats.total_seconds) for op in c_stats.operations.values()]
                ops_list.sort(key=lambda x: x["total_seconds"], reverse=True)
                operations[cat] = ops_list
                for op in ops_list:
                    all_ops.append({**op, "pct_of_all": round(op["total_seconds"] / base_total * 100.0, 2)})

            all_ops.sort(key=lambda x: x["total_seconds"], reverse=True)
            top_bottlenecks = all_ops[:10]

            # Primary bottleneck identification & diagnostic recommendation
            ranked_categories = sorted(
                [(cat, summary[cat]["percentage"], summary[cat]["total_seconds"]) for cat in CATEGORIES if cat != "other"],
                key=lambda x: x[1],
                reverse=True,
            )
            primary_bottleneck = ranked_categories[0][0] if ranked_categories else "time_sleep"
            primary_pct = ranked_categories[0][1] if ranked_categories else 0.0

            insights = self._generate_bottleneck_insights(primary_bottleneck, primary_pct, summary)

            return {
                "uptime_seconds": round(uptime, 2),
                "total_tracked_seconds": round(tracked_total, 4),
                "primary_bottleneck": primary_bottleneck,
                "primary_bottleneck_pct": primary_pct,
                "insights": insights,
                "summary": summary,
                "top_operations": top_bottlenecks,
                "operations_by_category": operations,
                "last_scrape": self.last_scrape,
                "recent_scrapes": list(self.recent_scrapes),
                "recent_events": list(self.recent_events),
            }

    def _generate_bottleneck_insights(self, bottleneck: str, pct: float, summary: dict) -> List[str]:
        insights = []
        if bottleneck == "time_sleep":
            insights.append(
                f"Rate limiting sleeps dominate the runtime ({pct}% of tracked time). "
                "This is expected and healthy for scraping to avoid rate limits (HTTP 429) and IP bans from Vinted."
            )
            insights.append("To speed up scrapes safely, adjust 'page_delay_seconds' or interval settings if permitted.")
        elif bottleneck == "web_scraping":
            insights.append(
                f"Web scraping network latency is the primary bottleneck ({pct}% of tracked time). "
                "The program is spending most of its active time waiting for HTTP responses from Vinted's catalog API."
            )
            insights.append("Check network latency, proxy speeds, or lower max_pages to reduce roundtrips.")
        elif bottleneck == "db_write":
            insights.append(
                f"Database writes are the primary bottleneck ({pct}% of tracked time). "
                "Disk I/O and SQLite transaction commits during listing saves are taking notable time."
            )
            insights.append("Batching inserts and ensuring WAL journal mode is enabled will help minimize write locks.")
        elif bottleneck == "db_read":
            insights.append(
                f"Database reads are the primary bottleneck ({pct}% of tracked time). "
                "Query filtering and full-table scans may be slowing down lookups."
            )
            insights.append("Verify indexes on listings(monitor_id, is_active) and verification_queue(last_check).")
        return insights

    def get_summary_text(self) -> str:
        """Returns a preformatted, human-readable terminal / report string."""
        stats = self.get_stats()
        lines = [
            "==================================================================",
            "                   VINTED BOTTLENECK MONITOR                      ",
            "==================================================================",
            f"Uptime: {stats['uptime_seconds']:.1f}s | Tracked Time: {stats['total_tracked_seconds']:.2f}s",
            f"Primary Bottleneck: {stats['primary_bottleneck'].upper()} ({stats['primary_bottleneck_pct']}%)",
            "------------------------------------------------------------------",
            f"{'Category':<15} {'Total (s)':<12} {'Percent':<10} {'Calls':<8} {'Avg (ms)':<10}",
            "------------------------------------------------------------------",
        ]
        for cat, data in stats["summary"].items():
            lines.append(
                f"{cat:<15} {data['total_seconds']:<12.3f} {data['percentage']:>6.1f}%    {data['count']:<8} {data['avg_ms']:<10.1f}"
            )
        lines.append("------------------------------------------------------------------")
        lines.append("Top Slowest Operations:")
        for op in stats["top_operations"][:5]:
            lines.append(
                f"  • {op['name']} ({op['category']}): {op['total_seconds']:.2f}s ({op['pct_of_all']}%) across {op['count']} calls (avg: {op['avg_ms']}ms)"
            )
        if stats.get("last_scrape"):
            ls = stats["last_scrape"]
            lines.append("------------------------------------------------------------------")
            lines.append(f"Last Scrape: Monitor #{ls['monitor_id']} '{ls['monitor_name']}' in {ls['duration_seconds']}s")
            lines.append(f"  Breakdown: {ls['breakdown_percentages']}")
        lines.append("==================================================================")
        return "\n".join(lines)


class _BlockContext:
    __slots__ = ("monitor", "category", "name", "metadata", "start_ts")

    def __init__(self, monitor: BottleneckMonitor, category: str, name: str, metadata: Optional[dict] = None):
        self.monitor = monitor
        self.category = category
        self.name = name
        self.metadata = metadata
        self.start_ts = 0.0

    def __enter__(self):
        self.start_ts = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.perf_counter() - self.start_ts
        self.monitor.record(self.category, self.name, duration, self.metadata)


# Global singleton instance
perf_monitor = BottleneckMonitor()


# ── SQLite Database Instrumentation Wrapper ──────────────────────────────────

class TracedCursor:
    """Transparent proxy around sqlite3.Cursor to record DB execution and fetch latency."""

    __slots__ = ("_cursor", "_monitor")

    def __init__(self, cursor: sqlite3.Cursor, monitor: BottleneckMonitor):
        self._cursor = cursor
        self._monitor = monitor

    def _classify_sql(self, sql: str) -> Tuple[str, str]:
        cleaned = sql.strip().split()
        if not cleaned:
            return "db_read", "sql_empty"
        cmd = cleaned[0].upper()

        table = "unknown"
        m = re.search(r'(?:FROM|INTO|UPDATE|TABLE)\s+([a-zA-Z0-9_]+)', sql, re.IGNORECASE)
        if m:
            table = m.group(1).lower()

        if cmd in ("SELECT", "EXPLAIN"):
            return "db_read", f"select_{table}"
        elif cmd == "PRAGMA":
            lower_sql = sql.lower()
            if "journal_mode" in lower_sql or "foreign_keys" in lower_sql:
                return "db_write", "pragma_config"
            return "db_read", "pragma_query"
        elif cmd in ("INSERT", "REPLACE"):
            return "db_write", f"insert_{table}"
        elif cmd == "UPDATE":
            return "db_write", f"update_{table}"
        elif cmd == "DELETE":
            return "db_write", f"delete_{table}"
        elif cmd in ("CREATE", "ALTER", "DROP"):
            return "db_write", f"schema_{cmd.lower()}_{table}"
        return "db_write", f"sql_{cmd.lower()}"

    def execute(self, sql: str, parameters: Any = ()):
        cat, name = self._classify_sql(sql)
        t0 = time.perf_counter()
        try:
            return self._cursor.execute(sql, parameters)
        finally:
            dt = time.perf_counter() - t0
            self._monitor.record(cat, name, dt)

    def executemany(self, sql: str, seq_of_parameters: Any):
        cat, name = self._classify_sql(sql)
        t0 = time.perf_counter()
        try:
            return self._cursor.executemany(sql, seq_of_parameters)
        finally:
            dt = time.perf_counter() - t0
            self._monitor.record(cat, f"{name}_batch", dt)

    def fetchone(self):
        t0 = time.perf_counter()
        try:
            return self._cursor.fetchone()
        finally:
            dt = time.perf_counter() - t0
            self._monitor.record("db_read", "fetch_row", dt)

    def fetchall(self):
        t0 = time.perf_counter()
        try:
            return self._cursor.fetchall()
        finally:
            dt = time.perf_counter() - t0
            self._monitor.record("db_read", "fetch_all", dt)

    def __iter__(self):
        return iter(self._cursor)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)


class TracedConnection:
    """Transparent proxy around sqlite3.Connection that wraps cursors and measures commit latency."""

    __slots__ = ("_conn", "_monitor")

    def __init__(self, conn: sqlite3.Connection, monitor: BottleneckMonitor):
        self._conn = conn
        self._monitor = monitor

    def cursor(self) -> TracedCursor:
        return TracedCursor(self._conn.cursor(), self._monitor)

    def execute(self, sql: str, parameters: Any = ()) -> TracedCursor:
        cur = self.cursor()
        cur.execute(sql, parameters)
        return cur

    def commit(self):
        t0 = time.perf_counter()
        try:
            return self._conn.commit()
        finally:
            dt = time.perf_counter() - t0
            self._monitor.record("db_write", "db_commit", dt)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.commit()
        return False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def __setattr__(self, name: str, value: Any):
        if name in ("_conn", "_monitor"):
            super().__setattr__(name, value)
        else:
            setattr(self._conn, name, value)


def trace_connection(conn: sqlite3.Connection) -> TracedConnection:
    """Wraps a sqlite3.Connection with performance instrumentation."""
    return TracedConnection(conn, perf_monitor)
