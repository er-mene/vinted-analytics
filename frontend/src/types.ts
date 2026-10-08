export interface Monitor {
  id: number;
  name: string;
  query: string;
  brand_id: number | null;
  min_price: number | null;
  max_price: number | null;
  status_ids: number[];
  max_pages: number | null;
  page_delay_seconds: number;
  search_time_seconds: number;
  max_age?: number;
  interval_days: number;
  interval_hours: number;
  interval_minutes: number;
  interval_seconds: number;
  total_listings: number;
  active_listings: number;
  sold_listings: number;
  avg_price: number | null;
  avg_likes: number | null;
  next_run_time: string | null;
  paused: boolean | null;
  last_scrape: string | null;
}

export interface RecentItem {
  id: number;
  title: string;
  brand: string | null;
  price: number | null;
  url: string;
  likes: number;
  listed_at: string | null;
  last_seen_at: string | null;
}

export interface QueueItem {
  id: number;
  url: string;
  queued_at: string;
  last_check: string;
  title: string | null;
  brand: string | null;
  price: number | null;
  is_active: number | null;
  sold_at: string | null;
  monitor_id: number | null;
  monitor_name: string | null;
}

export interface QueueSummary {
  total: number;
  oldest_queued: string | null;
}

export interface OverviewResponse {
  monitors: Monitor[];
  queue: QueueSummary;
}

export interface QueueResponse {
  total: number;
  oldest_queued: string | null;
  items: QueueItem[];
}

export interface AnalyticsSummary {
  id: number;
  name: string;
  total_listings: number;
  active_listings: number;
  sold_listings: number;
  avg_price: number | null;
  avg_likes: number | null;
}

export interface PriceHistoryPoint {
  day: string;
  listings_count: number;
  avg_price: number;
  min_price: number;
  max_price: number;
}

export interface ListingPoint {
  id: number;
  title: string;
  url: string;
  price: number | null;
  likes: number | null;
  listed_at: string | null;
  sold_at: string | null;
  is_active: number;
}

export interface SellSpeedPoint {
  id: number;
  title: string;
  url: string;
  price: number | null;
  likes: number | null;
  listed_at: string | null;
  sold_at: string | null;
  hours_to_sell: number | null;
}

export interface AnalyticsCorrelations {
  price_likes: number | null;
  price_sell_time: number | null;
}

export interface MonitorAnalytics {
  summary: AnalyticsSummary;
  price_history: PriceHistoryPoint[];
  price_likes: ListingPoint[];
  sell_speed: SellSpeedPoint[];
  correlations: AnalyticsCorrelations;
}

export interface MonitorListing {
  id: number;
  title: string;
  brand: string | null;
  price: number | null;
  url: string;
  likes: number | null;
  listed_at: string | null;
  is_active: number;
  sold_at: string | null;
}

export interface MonitorCreatePayload {
  name: string;
  query: string;
  brand_id?: number | null;
  min_price?: number | null;
  max_price?: number | null;
  status_ids?: number[];
  days?: number;
  hours?: number;
  minutes?: number;
  seconds?: number;
  max_pages?: number | null;
  page_delay_seconds?: number;
  search_time_seconds?: number;
  max_age?: number;
}

export interface MonitorCreateResponse {
  message: string;
  monitor_id: number;
  effective_interval: {
    days: number;
    hours: number;
    minutes: number;
    seconds: number;
    minimum_interval_seconds: number;
  };
}

export interface MonitorActionResponse {
  message: string;
  monitor_id: number;
}

export interface RunMonitorResponse {
  monitor: string;
  new_items_found: number;
  current_avg_price: number;
  total_active_scraped: number;
}

export interface ClearQueueResponse {
  message: string;
  deleted?: number;
}

export interface CategoryMetric {
  total_seconds: number;
  percentage: number;
  count: number;
  avg_ms: number;
  min_ms: number;
  max_ms: number;
}

export interface OperationMetric {
  name: string;
  category: string;
  count: number;
  total_seconds: number;
  percentage_of_category: number;
  avg_ms: number;
  min_ms: number;
  max_ms: number;
  last_occurred_at: string | null;
  pct_of_all?: number;
}

export interface LastScrapeProfile {
  monitor_id: number;
  monitor_name: string;
  finished_at: string;
  duration_seconds: number;
  pages_fetched: number;
  items_found: number;
  new_items: number;
  breakdown_seconds: {
    web_scraping?: number;
    db_write?: number;
    db_read?: number;
    time_sleep?: number;
    other?: number;
  };
  breakdown_percentages: {
    web_scraping?: number;
    db_write?: number;
    db_read?: number;
    time_sleep?: number;
    other?: number;
  };
  primary_bottleneck: string;
  error?: string | null;
}

export interface PerformanceResponse {
  uptime_seconds: number;
  total_tracked_seconds: number;
  primary_bottleneck: string;
  primary_bottleneck_pct: number;
  insights: string[];
  summary: {
    web_scraping: CategoryMetric;
    db_write: CategoryMetric;
    db_read: CategoryMetric;
    time_sleep: CategoryMetric;
    other: CategoryMetric;
  };
  top_operations: OperationMetric[];
  operations_by_category: Record<string, OperationMetric[]>;
  last_scrape: LastScrapeProfile | null;
}
