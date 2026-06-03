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
