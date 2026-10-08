import logging
import random
import re
import time
import threading
from enum import Enum
from curl_cffi import requests
from curl_cffi.requests.exceptions import Timeout, RequestException
from datetime import datetime, timedelta
from typing import List, Optional
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

VINTED_BASE_URL = "https://www.vinted.it"
VINTED_CATALOG_URL = "https://api.vinted.it/svc-catalogue/items"
CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 10.0
DEFAULT_TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)
SESSION_TTL_SECONDS = 45 * 60  # Renew session every 45 minutes

_session_local = threading.local()

def reset_vinted_session():
    """Explicitly closes and discards the thread-local Vinted session."""
    session = getattr(_session_local, "session", None)
    if session is not None:
        try:
            session.close()
        except Exception:
            pass
    _session_local.session = None
    _session_local.created_at = 0.0

def get_vinted_session(force_refresh: bool = False):
    session = getattr(_session_local, "session", None)
    created_at = getattr(_session_local, "created_at", 0.0)
    now = time.time()

    is_expired = (now - created_at) > SESSION_TTL_SECONDS

    if session is None or force_refresh or is_expired:
        if is_expired and session is not None:
            logger.info("Vinted session expired (age > %ds), renewing...", SESSION_TTL_SECONDS)
        elif force_refresh and session is not None:
            logger.info("Forcing refresh of Vinted session...")

        reset_vinted_session()

        new_session = requests.Session(impersonate="safari")
        try:
            response = new_session.get(VINTED_BASE_URL, timeout=DEFAULT_TIMEOUT)
            response.raise_for_status()
            _session_local.session = new_session
            _session_local.created_at = time.time()
        except (Timeout, RequestException) as exc:
            logger.error("Network error during Vinted session warm-up: %s", exc)
            new_session.close()
            reset_vinted_session()
            raise
        except Exception as exc:
            logger.error("Unexpected error during Vinted session warm-up: %s", exc)
            new_session.close()
            reset_vinted_session()
            raise

    return _session_local.session

def _get_api_headers(session):
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "it-IT,it;q=0.8,en-US;q=0.5,en;q=0.3",
        "Platform": "web",
        "x-next-app": "marketplace-web",
        "Origin": VINTED_BASE_URL,
        "Referer": f"{VINTED_BASE_URL}/",
    }
    anon_id = session.cookies.get("anon_id")
    if anon_id:
        headers["X-Anon-Id"] = anon_id
    return headers

def _parse_item(item):
    price_info = item.get("total_item_price") or item.get("price") or {}
    photo = item.get("photo") or {}
    high_res = photo.get("high_resolution") or {}
    unix_time = high_res.get("timestamp")

    if unix_time:
        listing_date = datetime.fromtimestamp(unix_time).strftime("%Y-%m-%d %H:%M:%S")
    else:
        unix_time = int(time.time())
        listing_date = datetime.fromtimestamp(unix_time).strftime("%Y-%m-%d %H:%M:%S")

    brand = item.get("brand_title")
    item_box = item.get("item_box") or {}
    if not brand and item_box.get("first_line"):
        brand = item_box["first_line"]

    url = item.get("url")
    if url and not url.startswith("http"):
        url = f"{VINTED_BASE_URL}{url}"

    status_id = item.get("status") or item.get("status_id")
    if status_id is None:
        second_line = (item_box.get("second_line") or "").lower()
        label = (item_box.get("accessibility_label") or "").lower()
        combined = f"{second_line} {label}"
        if "sans étiquette" in combined or "senza cartellino" in combined or "without tags" in combined:
            status_id = 6
        elif "avec étiquette" in combined or "con cartellino" in combined or "with tags" in combined:
            status_id = 1
        elif "très bon" in combined or "ottime" in combined or "very good" in combined:
            status_id = 2
        elif "bon état" in combined or "buone" in combined or "good condition" in combined:
            status_id = 3
        elif "satisfaisant" in combined or "discrete" in combined or "satisfactory" in combined:
            status_id = 5

    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "brand": brand,
        "price": float(price_info.get("amount", 0)),
        "url": url,
        "status_id": status_id,
        "likes": int(item.get("favourite_count", 0)),
        "listed_at": listing_date,
        "listed_at_ts": unix_time,
        "has_been_promoted": 1 if item.get("promoted") else 0,
    }


MIN_PAGE_DELAY_SECONDS = 5.0
DEFAULT_PAGE_DELAY_SECONDS = 6.0


def search_vinted(
    query: str = None,
    brand_id: int = None,
    min_price: float = None,
    max_price: float = None,
    status_ids: List[int] = None,
    max_pages: int = None,
    page_delay_seconds: float = DEFAULT_PAGE_DELAY_SECONDS,
    search_time_seconds: int = 5184000,
    progress_callback=None,
    order: str = "newest_first",
    stop_event: Optional[threading.Event] = None,
):
    if stop_event and stop_event.is_set():
        return None

    session = get_vinted_session()
    effective_delay = max(page_delay_seconds or DEFAULT_PAGE_DELAY_SECONDS, MIN_PAGE_DELAY_SECONDS)

    logger.info(f"🕵️  Scraping Vinted for: {query} (page delay: ~{effective_delay:.1f}s)...")

    try:
        session.get(f"{VINTED_BASE_URL}/")
    except Exception as e:
        logger.error(f"❌ Connection Error (Cookies): {e}")
        return []

    # Realistic pause after establishing session before querying the catalogue
    warmup_pause = random.uniform(1.5, 2.8)
    if stop_event:
        if stop_event.wait(timeout=warmup_pause):
            return None
    else:
        time.sleep(warmup_pause)

    if stop_event and stop_event.is_set():
        return None

    headers = _get_api_headers(session)

    params = {}
    if query:
        params["search_text"] = query
    if brand_id:
        if isinstance(brand_id, (list, tuple)):
            params["attribute_ids[brand]"] = ",".join(map(str, brand_id))
        else:
            params["attribute_ids[brand]"] = str(brand_id)
    if min_price:
        params["price_from"] = min_price
    if max_price:
        params["price_to"] = max_price
    if status_ids:
        if isinstance(status_ids, (list, tuple)):
            params["attribute_ids[status]"] = ",".join(map(str, status_ids))
        else:
            params["attribute_ids[status]"] = str(status_ids)
    if order:
        params["order"] = order
    params["per_page"] = 48

    def _fetch_page(page_num):
        nonlocal headers, session
        if stop_event and stop_event.is_set():
            return None
        try:
            response = session.get(
                VINTED_CATALOG_URL,
                headers=headers,
                params={**params, "page": page_num},
                timeout=30,
            )
        except Exception as e:
            logger.error(f"❌ Connection Error (API page {page_num}): {e}")
            return None

        if response.status_code in (401, 403):
            logger.warning(
                f"⚠️ Received status {response.status_code} on page {page_num}, renewing session and cookies..."
            )
            # Recreate session from scratch
            try:
                session = get_vinted_session(force_refresh=True)
                headers = _get_api_headers(session)
                time.sleep(random.uniform(1.5, 2.5))
                if stop_event and stop_event.is_set():
                    return None
                response = session.get(
                    VINTED_CATALOG_URL,
                    headers=headers,
                    params={**params, "page": page_num},
                    timeout=30,
                )
            except Exception as e:
                logger.warning(f"Failed session refresh on page {page_num}: {e}")

        if response.status_code != 200:
            logger.error(
                f"❌ BLOCK DETECTED on page {page_num}: Status Code {response.status_code}"
            )
            return None

        try:
            return response.json()
        except Exception as e:
            logger.error(f"❌ JSON Error on page {page_num}: {e}")
            return None

    data = _fetch_page(1)
    if data is None:
        return []

    pagination = data.get("pagination", {})
    total_pages = pagination.get("total_pages", 1)
    pages_to_fetch = min(total_pages, max_pages) if max_pages else total_pages

    raw_items = data.get("items", [])
    seen_ids = set()
    clean_items = []

    for item in raw_items:
        try:
            parsed = _parse_item(item)
            seen_ids.add(parsed["id"])
            clean_items.append(parsed)
        except Exception as e:
            logger.warning(f"⚠️ skipped item {item.get('id')} due to error: {e}")
            continue

    if progress_callback:
        progress_callback(1, pages_to_fetch)

    logger.info(f"✅ Page 1/{pages_to_fetch}: {len(raw_items)} raw ({len(clean_items)} kept)")

    for page in range(2, pages_to_fetch + 1):
        if stop_event and stop_event.is_set():
            logger.info("Scrape aborted before page %d.", page)
            return None

        delay = random.uniform(effective_delay * 0.85, effective_delay * 1.35)
        logger.info(f"⏳ Waiting {delay:.1f}s before page {page}...")
        if stop_event:
            if stop_event.wait(timeout=delay):
                logger.info("Scrape aborted during delay before page %d.", page)
                return None
        else:
            time.sleep(delay)

        if stop_event and stop_event.is_set():
            return None

        data = _fetch_page(page)
        if data is None:
            break

        page_raw = data.get("items", [])
        new_on_page = 0

        for item in page_raw:
            try:
                parsed = _parse_item(item)
                item_id = parsed["id"]
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)
                clean_items.append(parsed)
                new_on_page += 1
            except Exception as e:
                logger.warning(
                    f"⚠️ skipped item {item.get('id')} on page {page} due to error: {e}"
                )
                continue

        if progress_callback:
            progress_callback(page, pages_to_fetch)

        logger.info(
            f"✅ Page {page}/{pages_to_fetch}: {len(page_raw)} raw, "
            f"{new_on_page} new (total {len(clean_items)})"
        )

    # Filter by listing time
    now = time.time()
    if search_time_seconds:
        clean_items = [
            i for i in clean_items
            if i["listed_at_ts"] is None or (now - i["listed_at_ts"]) <= search_time_seconds
        ]

    logger.info(
        f"🏁 Finished parsing. Returning {len(clean_items)} valid items "
        f"across {pages_to_fetch} pages."
    )
    return clean_items


# Alias to support both names
vinted_search = search_vinted


class ItemStatus(Enum):
    ACTIVE = "active"
    SOLD = "sold"
    REMOVED = "removed"
    ERROR = "error"


class ItemVerificationResult:
    def __init__(self, status: ItemStatus, listed_at: str | None = None, upload_date_raw: str | None = None):
        self.status = status
        self.listed_at = listed_at
        self.upload_date_raw = upload_date_raw

    def __iter__(self):
        return iter((self.status, self.listed_at))

    def __eq__(self, other):
        if isinstance(other, ItemStatus):
            return self.status == other
        if isinstance(other, ItemVerificationResult):
            return self.status == other.status and self.listed_at == other.listed_at
        return False

    def __str__(self):
        return str(self.status)

    def __repr__(self):
        return f"ItemVerificationResult({self.status}, listed_at={self.listed_at})"


SOLD_STATUS_KEYWORDS = (
    "venduto", "sold", "vendu", "vendido", "verkauft",
    "verkocht", "sprzedane", "sprzedano", "prodano", "vândut",
)
RESERVED_STATUS_KEYWORDS = (
    "prenotato", "reserved", "réservé", "reserve",
    "reservado", "reserviert", "zarezerwowane", "gereserveerd",
)


def parse_relative_date(date_str: str, now: datetime = None) -> datetime | None:
    if not date_str:
        return None
    if now is None:
        now = datetime.now()

    text = date_str.strip().lower()

    # Just now / proprio adesso / a l'instant
    if any(k in text for k in ["proprio adesso", "adesso", "just now", "à l'instant", "instant", "ahora", "gerade"]):
        return now

    # Yesterday / ieri / hier / gestern / ayer
    if any(k in text for k in ["ieri", "yesterday", "hier", "gestern", "ayer"]):
        return now - timedelta(days=1)

    # Check for ISO or YYYY-MM-DD [HH:MM:SS]
    iso_match = re.search(r'\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})[ T](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?', text)
    if not iso_match:
        iso_match = re.search(r'\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b', text)
    if iso_match:
        try:
            year, month, day = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
            hour = int(iso_match.group(4) or 0) if len(iso_match.groups()) >= 4 and iso_match.group(4) else 0
            minute = int(iso_match.group(5) or 0) if len(iso_match.groups()) >= 5 and iso_match.group(5) else 0
            second = int(iso_match.group(6) or 0) if len(iso_match.groups()) >= 6 and iso_match.group(6) else 0
            return datetime(year, month, day, hour, minute, second)
        except ValueError:
            pass

    # Check for DD/MM/YYYY or DD.MM.YYYY
    dmy_match = re.search(r'\b(\d{1,2})[/. -](\d{1,2})[/. -](\d{4})[ T](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?', text)
    if not dmy_match:
        dmy_match = re.search(r'\b(\d{1,2})[/. -](\d{1,2})[/. -](\d{4})\b', text)
    if dmy_match:
        try:
            day, month, year = int(dmy_match.group(1)), int(dmy_match.group(2)), int(dmy_match.group(3))
            hour = int(dmy_match.group(4) or 0) if len(dmy_match.groups()) >= 4 and dmy_match.group(4) else 0
            minute = int(dmy_match.group(5) or 0) if len(dmy_match.groups()) >= 5 and dmy_match.group(5) else 0
            second = int(dmy_match.group(6) or 0) if len(dmy_match.groups()) >= 6 and dmy_match.group(6) else 0
            return datetime(year, month, day, hour, minute, second)
        except ValueError:
            pass

    word_to_num = {
        "un": 1, "uno": 1, "una": 1, "one": 1, "a": 1, "an": 1,
        "due": 2, "two": 2, "deux": 2, "dos": 2, "zwei": 2,
        "tre": 3, "three": 3, "trois": 3, "tres": 3, "drei": 3,
        "quattro": 4, "four": 4, "quatre": 4, "cuatro": 4, "vier": 4,
        "cinque": 5, "five": 5, "cinq": 5, "cinco": 5, "fünf": 5,
        "sei": 6, "six": 6, "seis": 6, "sechs": 6,
        "sette": 7, "seven": 7, "sept": 7, "siete": 7, "sieben": 7,
        "otto": 8, "eight": 8, "huit": 8, "ocho": 8, "acht": 8,
        "nove": 9, "nine": 9, "neuf": 9, "nueve": 9, "neun": 9,
        "dieci": 10, "ten": 10, "dix": 10, "diez": 10, "zehn": 10,
    }

    num_match = re.search(r'\b(\d+)\b', text)
    count = int(num_match.group(1)) if num_match else None

    if count is None:
        for word, val in word_to_num.items():
            if re.search(rf'\b{word}\b', text):
                count = val
                break

    if count is None:
        count = 1

    # Match units with specific regexes to avoid substrings like 'or' in 'giorni'
    if re.search(r'\b(minut[ioe]?|min|minute|minutes)\b', text):
        return now - timedelta(minutes=count)
    elif re.search(r'\b(or[ae]|hour|hours|stunde|stunden|heure|heures)\b', text):
        return now - timedelta(hours=count)
    elif re.search(r'\b(giorn[io]|day|days|jour|jours|tag|tagen|días?)\b', text):
        return now - timedelta(days=count)
    elif re.search(r'\b(settiman[ae]|week|weeks|semaine|semaines|woche|wochen|semanas?)\b', text):
        return now - timedelta(weeks=count)
    elif re.search(r'\b(mes[ie]?|month|months|mois|monat|monaten)\b', text):
        return now - timedelta(days=count * 30)
    elif re.search(r'\b(ann[oi]|year|years|an|ans|jahr|jahren|años?)\b', text):
        return now - timedelta(days=count * 365)

    return None


def extract_upload_date(html: str) -> str | None:
    try:
        soup = BeautifulSoup(html, "html.parser")
        el = soup.find(attrs={"itemprop": "upload_date"})
        if el:
            content_val = el.get("content") or el.get("datetime")
            if content_val:
                return content_val.strip()
            txt = el.get_text(strip=True)
            if txt:
                return txt
    except Exception:
        pass

    m = re.search(r'upload_date(?:(?!upload_date).){1,150}?value[\"\\\s]*:[\"\\\s]*([^\"\\\}]+)', html)
    if m:
        return m.group(1).strip()

    m_direct = re.search(r'upload_date[\"\\\s]*:[\"\\\s]*([^\"\\\},]+)', html)
    if m_direct:
        val = m_direct.group(1).strip()
        if val and val not in ('{', '['):
            return val

    return None


def _get_item_status_data(html: str) -> dict:
    data = {}
    can_buy_matches = re.findall(r'can_buy[\"\\\s]*:\s*(true|false)', html)
    if can_buy_matches:
        data["can_buy"] = any(m == "true" for m in can_buy_matches)
        data["all_cannot_buy"] = all(m == "false" for m in can_buy_matches)

    is_closed_matches = re.findall(r'is_closed[\"\\\s]*:\s*(true|false)', html)
    if is_closed_matches:
        data["is_closed"] = any(m == "true" for m in is_closed_matches)

    is_reserved_matches = re.findall(r'is_reserved[\"\\\s]*:\s*(true|false)', html)
    if is_reserved_matches:
        data["is_reserved"] = any(m == "true" for m in is_reserved_matches)

    closing_matches = re.findall(r'item_closing_action[\"\\\s]*:\s*([\"\\A-Za-z0-9_]+)', html)
    for act in closing_matches:
        cleaned = act.replace('\\', '').replace('"', '').lower()
        if cleaned:
            data["item_closing_action"] = cleaned

    return data


def check_item_status(url: str) -> ItemVerificationResult:
    if url and not url.startswith("http"):
        url = f"{VINTED_BASE_URL}{url}"

    logger.debug(f"Verifying item status for: {url}")
    session = get_vinted_session()

    try:
        response = session.get(url, timeout=30)
    except Exception as e:
        logger.error(f"Connection error verifying item status for {url}: {e}")
        return ItemVerificationResult(ItemStatus.ERROR)

    if response.status_code in (401, 403):
        logger.warning(f"Item {url} returned HTTP {response.status_code}, renewing session...")
        try:
            session = get_vinted_session(force_refresh=True)
            time.sleep(random.uniform(1.0, 2.0))
            response = session.get(url, timeout=30)
        except Exception as e:
            logger.error(f"Failed retry for item {url} after session refresh: {e}")
            return ItemVerificationResult(ItemStatus.ERROR)

    if response.status_code == 404:
        logger.info(f"Item {url} returned 404, marked as REMOVED")
        return ItemVerificationResult(ItemStatus.REMOVED)
    if response.status_code >= 400:
        logger.warning(f"Item {url} returned HTTP {response.status_code}, status ERROR")
        return ItemVerificationResult(ItemStatus.ERROR)

    html = response.text

    # Extract actual upload/listing date from the item page
    upload_date_raw = extract_upload_date(html)
    parsed_dt = parse_relative_date(upload_date_raw) if upload_date_raw else None
    listed_at = parsed_dt.strftime("%Y-%m-%d %H:%M:%S") if parsed_dt else None

    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as e:
        logger.warning(f"HTML parse error for {url}: {e}")
        return ItemVerificationResult(ItemStatus.ERROR, listed_at=listed_at, upload_date_raw=upload_date_raw)

    def _resolved(status: ItemStatus) -> ItemVerificationResult:
        logger.debug(f"Item status for {url} resolved to {status.value} (listed_at: {listed_at})")
        return ItemVerificationResult(status, listed_at=listed_at, upload_date_raw=upload_date_raw)

    # 1. Definite ACTIVE signals: Buy button exists
    if soup.find(attrs={"data-testid": "item-buy-button"}):
        return _resolved(ItemStatus.ACTIVE)

    # 2. Status banners / badges in HTML (e.g. green 'web_ui__Cell__success' badge)
    success_cells = soup.find_all(class_=lambda x: x and "web_ui__Cell__success" in x)
    for cell in success_cells:
        txt = cell.get_text(strip=True).lower()
        if any(w in txt for w in SOLD_STATUS_KEYWORDS) or any(w in txt for w in RESERVED_STATUS_KEYWORDS):
            return _resolved(ItemStatus.SOLD)

    # Legacy or specific data-testid
    if soup.find(attrs={"data-testid": "item-status-content"}):
        return _resolved(ItemStatus.SOLD)

    # Status elements in sidebar / badges
    for el in soup.find_all(["div", "span", "p"], class_=lambda x: x and any(c in x for c in ["Cell", "status", "Badge", "badge", "banner"])):
        txt = el.get_text(strip=True).lower()
        if txt in SOLD_STATUS_KEYWORDS or txt in RESERVED_STATUS_KEYWORDS:
            return _resolved(ItemStatus.SOLD)

    # 3. Check JSON state embedded in the page
    item_data = _get_item_status_data(html)

    if item_data.get("item_closing_action") == "sold":
        return _resolved(ItemStatus.SOLD)
    if item_data.get("item_closing_action") in ("removed", "deleted"):
        return _resolved(ItemStatus.REMOVED)

    if item_data.get("is_closed") or item_data.get("is_reserved"):
        return _resolved(ItemStatus.SOLD)

    if item_data.get("all_cannot_buy"):
        return _resolved(ItemStatus.SOLD)

    # 4. Secondary active signals
    if soup.find(attrs={"data-testid": "item-buyer-offer-button"}):
        return _resolved(ItemStatus.ACTIVE)

    if item_data.get("can_buy") is True:
        return _resolved(ItemStatus.ACTIVE)

    # 5. If no buy buttons exist and can_buy is not True, the item is not purchasable
    return _resolved(ItemStatus.SOLD)

    
