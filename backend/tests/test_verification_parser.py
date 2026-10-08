import pytest
from bs4 import BeautifulSoup
from backend.app.services.vinted_service import (
    ItemStatus,
    ItemVerificationResult,
    _get_item_status_data,
    SOLD_STATUS_KEYWORDS,
    RESERVED_STATUS_KEYWORDS,
)

SAMPLE_ACTIVE_RSC_HTML = """
<!DOCTYPE html><html><head><title>Apple AirPods 4 (ANC) | Vinted</title></head>
<body>
<div class="standard-layout">
<span class="react-loading-skeleton"></span>
<div data-testid="item-price">130,00 €</div>
<div data-testid="item-attributes-status">Condizioni Nuovo con cartellino</div>
<div class="web_ui__Cell__content"><div class="web_ui__Cell__body">Descrizione prodotto</div></div>
</div>
<script>self.__next_f.push([1, "{\\"id\\":\\"12345\\",\\"can_buy\\":false,\\"is_closed\\":false,\\"is_reserved\\":false}"])</script>
</body></html>
"""

SAMPLE_SOLD_RSC_HTML = """
<!DOCTYPE html><html><head><title>Apple AirPods 4 (ANC) | Vinted</title></head>
<body>
<div class="standard-layout">
<div data-testid="item-price">100,00 €</div>
<div class="web_ui__Cell__cell web_ui__Cell__success"><div class="web_ui__Cell__body">Venduto</div></div>
</div>
<script>self.__next_f.push([1, "{\\"name\\":\\"buyer_item_status\\",\\"title\\":\\"Venduto\\"}"])</script>
</body></html>
"""

SAMPLE_REMOVED_HTML = """
<!DOCTYPE html><html><head><title>Vinted</title></head>
<body>
<div class="flash_messages">L'articolo non è più disponibile</div>
</body></html>
"""

def _resolve_status_from_html(html: str) -> ItemStatus:
    soup = BeautifulSoup(html, "html.parser")

    if soup.find(attrs={"data-testid": "item-buy-button"}):
        return ItemStatus.ACTIVE
    if soup.find(attrs={"data-testid": "item-buyer-offer-button"}):
        return ItemStatus.ACTIVE

    success_cells = soup.find_all(class_=lambda x: x and "web_ui__Cell__success" in x)
    for cell in success_cells:
        txt = cell.get_text(strip=True).lower()
        if any(w in txt for w in SOLD_STATUS_KEYWORDS) or any(w in txt for w in RESERVED_STATUS_KEYWORDS):
            return ItemStatus.SOLD

    if soup.find(attrs={"data-testid": "item-status-content"}):
        return ItemStatus.SOLD

    for el in soup.find_all(["div", "span", "p"], class_=lambda x: x and any(c in x for c in ["Cell", "status", "Badge", "badge", "banner"])):
        txt = el.get_text(strip=True).lower()
        if txt in SOLD_STATUS_KEYWORDS or txt in RESERVED_STATUS_KEYWORDS:
            return ItemStatus.SOLD

    import re
    buyer_status_matches = re.findall(r'\"name\":\"buyer_item_status\".*?\"title\":\"([^\"]+)\"', html)
    if not buyer_status_matches:
        buyer_status_matches = re.findall(r'\"title\":\"([^\"]+)\".*?\"name\":\"buyer_item_status\"', html)
    for title in buyer_status_matches:
        title_lower = title.strip().lower()
        if title_lower in SOLD_STATUS_KEYWORDS or title_lower in RESERVED_STATUS_KEYWORDS:
            return ItemStatus.SOLD

    item_data = _get_item_status_data(html)
    if item_data.get("item_closing_action") == "sold":
        return ItemStatus.SOLD
    if item_data.get("item_closing_action") in ("removed", "deleted"):
        return ItemStatus.REMOVED
    if item_data.get("is_closed") or item_data.get("is_reserved"):
        return ItemStatus.SOLD

    body_text = soup.get_text().lower()
    REMOVED_KEYWORDS = (
        "non è più disponibile", "no longer available", "plus disponible",
        "nicht mehr verfügbar", "ya no está disponible", "eliminato", "deleted",
        "rimosso", "supprimé", "gelöscht"
    )
    if any(rm in body_text for rm in REMOVED_KEYWORDS):
        return ItemStatus.REMOVED

    has_price = bool(soup.find(attrs={"data-testid": "item-price"}) or re.search(r'itemProp=[\"\']price[\"\']', html))
    has_status = bool(soup.find(attrs={"data-testid": "item-attributes-status"}))
    has_title = bool(soup.title and soup.title.string and "vinted" in soup.title.string.lower())

    if has_price and (has_status or has_title):
        return ItemStatus.ACTIVE

    if has_title:
        return ItemStatus.ACTIVE

    return ItemStatus.ERROR


def test_active_item_without_buy_button():
    status = _resolve_status_from_html(SAMPLE_ACTIVE_RSC_HTML)
    assert status == ItemStatus.ACTIVE, "Active RSC item must NOT be classified as sold"


def test_sold_item_with_badge():
    status = _resolve_status_from_html(SAMPLE_SOLD_RSC_HTML)
    assert status == ItemStatus.SOLD, "Item with Venduto badge must be classified as sold"


def test_removed_item_with_banner():
    status = _resolve_status_from_html(SAMPLE_REMOVED_HTML)
    assert status == ItemStatus.REMOVED, "Item with removed banner must be classified as removed"
