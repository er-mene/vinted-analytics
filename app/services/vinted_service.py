import random
import time
from enum import Enum
from curl_cffi import requests
from datetime import datetime
from typing import List
from bs4 import BeautifulSoup

_shared_session = None

def get_vinted_session():
    """
    Returns a session object with necessary Vinted cookies.
    Initializes a new session if one does not exist.
    """
    global _shared_session
    if _shared_session is None:
        _shared_session = requests.Session(impersonate="safari")
        _shared_session.get("https://www.vinted.it")
    return _shared_session

def _parse_item(item):
    price_info = item.get("total_item_price") or {}
    photo = item.get("photo") or {}
    high_res = photo.get("high_resolution") or {}
    unix_time = high_res.get("timestamp")

    listing_date = None
    if unix_time:
        listing_date = datetime.fromtimestamp(unix_time).strftime("%Y-%m-%d %H:%M:%S")

    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "brand": item.get("brand_title"),
        "price": float(price_info.get("amount", 0)),
        "url": item.get("url"),
        "status_id": item.get("status"),
        "likes": int(item.get("favourite_count", 0)),
        "listed_at": listing_date,
        "has_been_promoted": 1 if item.get("promoted") else 0,
    }


def search_vinted(
    query: str,
    brand_id: int = None,
    min_price: float = None,
    max_price: float = None,
    status_ids: List[int] = None,
    max_pages: int = None,
    page_delay_seconds: float = 4.0,
):
    session = get_vinted_session()

    print(f"🕵️  Scraping Vinted for: {query}...")

    try:
        session.get("https://www.vinted.it/")
    except Exception as e:
        print(f"❌ Connection Error (Cookies): {e}")
        return []

    params = {}
    if query:
        params["search_text"] = query
    if brand_id:
        params["brand_ids[]"] = brand_id
    if min_price:
        params["price_from"] = min_price
    if max_price:
        params["price_to"] = max_price
    if status_ids:
        params["status_ids[]"] = status_ids

    def _fetch_page(page_num):
        try:
            response = session.get(
                "https://www.vinted.it/api/v2/catalog/items",
                params={**params, "page": page_num},
            )
        except Exception as e:
            print(f"❌ Connection Error (API page {page_num}): {e}")
            return None

        if response.status_code != 200:
            print(
                f"❌ BLOCK DETECTED on page {page_num}: Status Code {response.status_code}"
            )
            return None

        try:
            return response.json()
        except Exception as e:
            print(f"❌ JSON Error on page {page_num}: {e}")
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
            print(f"⚠️ skipped item {item.get('id')} due to error: {e}")
            continue

    print(f"✅ Page 1/{pages_to_fetch}: {len(raw_items)} raw ({len(clean_items)} kept)")

    for page in range(2, pages_to_fetch + 1):
        delay = random.uniform(page_delay_seconds * 0.7, page_delay_seconds * 1.3)
        print(f"⏳ Waiting {delay:.1f}s before page {page}...")
        time.sleep(delay)

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
                print(
                    f"⚠️ skipped item {item.get('id')} on page {page} due to error: {e}"
                )
                continue

        print(
            f"✅ Page {page}/{pages_to_fetch}: {len(page_raw)} raw, "
            f"{new_on_page} new (total {len(clean_items)})"
        )

    print(
        f"🏁 Finished parsing. Returning {len(clean_items)} valid items "
        f"across {pages_to_fetch} pages."
    )
    return clean_items

class ItemStatus(Enum):
    ACTIVE = "active"
    SOLD = "sold"
    REMOVED = "removed"
    ERROR = "error"

def check_item_status(url: str) -> ItemStatus:
    session = get_vinted_session()

    try:
        response = session.get(url)
    except Exception as e:
        return ItemStatus.ERROR
    if response.status_code >= 400:
        return ItemStatus.ERROR

    try:
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception:
        return ItemStatus.ERROR

    if soup.find(attrs={"data-testid": "item-status—content"}):
        return ItemStatus.SOLD
    
    return ItemStatus.ACTIVE

    
