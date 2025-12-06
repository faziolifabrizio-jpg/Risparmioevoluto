import os
import time
import json
import re
from typing import List, Dict, Any, Optional

import requests

# ============ CONFIG ============

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
AFFILIATE_TAG = "risparmioevol-21"

PAGES = [
    "https://www.amazon.it/deals",
    "https://www.amazon.it/gp/deals",
    "https://www.amazon.it/gp/goldbox",
    "https://www.amazon.it/s?k=offerte",
    "https://www.amazon.it/s?k=offerte+oggi",
    "https://www.amazon.it/s?k=sconto",
]

MAX_OFFERS_SEND = 10          # quante offerte mandare ad ogni esecuzione
HISTORY_FILE = "published.json"
HISTORY_HOURS = 24            # non ripubblicare offerte con stesso ASIN nelle ultime 24h

DEBUG = os.getenv("DEBUG", "0") == "1"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
}


# ============ TELEGRAM ============

def tg_text(msg: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TG] TELEGRAM_TOKEN / TELEGRAM_CHAT_ID mancanti, salto invio testo")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(url, data=data, timeout=20)
        print("[TG text]", r.status_code)
    except Exception as e:
        print("[TG text ERRORE]", e)


def tg_photo(photo_url: str, caption: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TG] TELEGRAM_TOKEN / TELEGRAM_CHAT_ID mancanti, salto invio foto")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "HTML",
    }
    try:
        r = requests.post(url, data=data, timeout=20)
        print("[TG photo]", r.status_code)
    except Exception as e:
        print("[TG photo ERRORE]", e)


# ============ UTILITY ============

def parse_price(price: Optional[str]) -> Optional[float]:
    if not price:
        return None
    try:
        p = price.replace("€", "").replace("\u00a0", "").replace(" ", "")
        p = p.replace(".", "").replace(",", ".")
        return float(p)
    except Exception:
        return None


def rating_to_stars(rating: Optional[float]) -> Optional[str]:
    if rating is None:
        return None
    try:
        full = int(rating)
        half = (rating - full) >= 0.5
        return "⭐" * full + ("✨" if half else "")
    except Exception:
        return None


def load_history() -> List[Dict[str, Any]]:
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_history(history: List[Dict[str, Any]]) -> None:
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False)
    except Exception as e:
        print("[HISTORY] Errore salvataggio:", e)


def filter_recent(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cutoff = time.time() - HISTORY_HOURS * 3600
    return [h for h in history if h.get("ts", 0) >= cutoff]


# ============ ESTRAZIONE JSON INCORPORATO ============

def extract_deal_json_from_html(html: str) -> List[Dict[str, Any]]:
    """
    Cerca un blocco JSON grosso che contiene "dealDetails".
    È best-effort: Amazon cambia spesso, quindi usiamo regex + bilanciamento parentesi.
    Se trova qualcosa tipo {"dealDetails":{...}} lo parsa e restituisce la lista dei deal.
    """
    deals: List[Dict[str, Any]] = []

    idx = html.find('{"dealDetails":')
    if idx == -1:
        # tentativo alternativo: "dealDetails":{""
        idx = html.find('"dealDetails":{')
        if idx == -1:
            print("[JSON] 'dealDetails' non trovato in pagina")
            return deals

        # risaliamo fino alla '{' più vicina prima di "dealDetails"
        start = html.rfind("{", 0, idx)
    else:
        start = idx

    if start == -1:
        print("[JSON] Nessuna '{' iniziale trovata")
        return deals

    depth = 0
    in_str = False
    prev = ""
    end = None

    for i in range(start, len(html)):
        ch = html[i]
        if ch == '"' and prev != '\\':
            in_str = not in_str
        if not in_str:
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        prev = ch

    if end is None:
        print("[JSON] Bilanciamento parentesi fallito")
        return deals

    chunk = html[start:end]

    try:
        obj = json.loads(chunk)
    except Exception as e:
        print("[JSON] Errore json.loads:", e)
        if DEBUG:
            print("=== CHUNK JSON FALLITO ===")
            print(chunk[:1000])
        return deals

    deal_details = obj.get("dealDetails")
    if isinstance(deal_details, dict):
        deals = list(deal_details.values())
    elif isinstance(deal_details, list):
        deals = deal_details
    else:
        print("[JSON] 'dealDetails' con formato inatteso")
        deals = []

    if DEBUG and deals:
        print("[JSON] Esempio di deal trovato:")
        print(json.dumps(deals[0], indent=2, ensure_ascii=False))

    print(f"[JSON] Deal estratti da pagina: {len(deals)}")
    return deals


def fetch_all_deals_from_pages() -> List[Dict[str, Any]]:
    session = requests.Session()
    session.headers.update(HEADERS)

    all_deals: List[Dict[str, Any]] = []

    for url in PAGES:
        print(f"[FETCH] GET {url}")
        try:
            r = session.get(url, timeout=25)
        except Exception as e:
            print("[FETCH] Errore HTTP:", e)
            continue

        print("[FETCH] status", r.status_code)
        if r.status_code != 200:
            continue

        deals = extract_deal_json_from_html(r.text)
        all_deals.extend(deals)
        time.sleep(1.0)

    print(f"[FETCH] Totale deal grezzi raccolti da tutte le pagine: {len(all_deals)}")
    return all_deals


# ============ MAPPATURA DEAL → PRODOTTO ============

def map_deal_to_product(deal: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Traduciamo il JSON di Amazon in un dizionario semplice:
    - asin
    - title
    - price_now_str
    - list_price_str
    - discount_pct
    - rating_num / rating_stars
    - review_count
    - image
    - url affiliato
    """

    # Titolo
    title = (
        deal.get("title")
        or deal.get("dealTitle")
        or deal.get("headline")
    )

    # ASIN
    asin = (
        deal.get("asin")
        or deal.get("entityId")
        or deal.get("primaryItem", {}).get("asin")
    )

    # Rating (numero)
    rating = (
        deal.get("averageRating")
        or deal.get("rating")
        or deal.get("primaryItem", {}).get("averageRating")
    )

    if isinstance(rating, dict):
        rating = rating.get("value")

    rating_num = None
    try:
        if rating is not None:
            rating_num = float(str(rating).replace(",", "."))
    except Exception:
        rating_num = None

    # Numero recensioni
    review_count = (
        deal.get("totalReviews")
        or deal.get("reviewCount")
        or deal.get("primaryItem", {}).get("totalReviews")
    )

    # Immagine
    image = (
        deal.get("primaryItem", {}).get("imageUrl")
        or deal.get("imageUrl")
    )

    # Prezzi
    # Qui tentiamo diverse chiavi comuni che Amazon usa
    price_now_str = (
        deal.get("dealPrice", {}).get("formattedPrice")
        or deal.get("price", {}).get("formattedPrice")
        or deal.get("minDealPrice", {}).get("formattedPrice")
        or deal.get("maxDealPrice", {}).get("formattedPrice")
        or deal.get("displayPrice")
    )

    list_price_str = (
        deal.get("listPrice", {}).get("formattedPrice")
        or deal.get("originalPrice", {}).get("formattedPrice")
        or deal.get("wasPrice", {}).get("formattedPrice")
    )

    p_now = parse_price(price_now_str)
    p_list = parse_price(list_price_str)

    if not p_now or not p_list or p_now >= p_list:
        # niente sconto vero
        return None

    discount_pct = round((p_list - p_now) / p_list * 100)

    if not asin:
        return None

    url_aff = f"https://www.amazon.it/dp/{asin}/?tag={AFFILIATE_TAG}"

    prod = {
        "asin": asin,
        "title": title or f"Offerta {asin}",
        "price_now_str": price_now_str or f"{p_now:.2f}€",
        "list_price_str": list_price_str or f"{p_list:.2f}€",
        "discount_pct": discount_pct,
        "rating_num": rating_num,
        "rating_stars": rating_to_stars(rating_num) if rating_num else None,
        "review_count": review_count,
        "image": image,
        "url": url_aff,
    }

    return prod


# ============ MAIN ============

def main() -> None:
    print("[MAIN] Avvio bot Amazon deals (HTML+JSON)…")
    tg_text("🔍 <b>Analizzo le offerte Amazon…</b>")

    raw_deals = fetch_all_deals_from_pages()
    if not raw_deals:
        tg_text("❌ <b>Nessun deal trovato nelle pagine offerte.</b>")
        return

    products: List[Dict[str, Any]] = []
    for d in raw_deals:
        prod = map_deal_to_product(d)
        if prod:
            products.append(prod)

    if DEBUG:
        print(f"[MAIN] Prodotti scontati mappati: {len(products)}")

    if not products:
        tg_text("❌ <b>Nessun prodotto con sconto reale trovato.</b>")
        return

    # ordina per sconto decrescente
    products.sort(key=lambda x: x["discount_pct"], reverse=True)

    # history (no duplicati 24h)
    history = filter_recent(load_history())
    seen = {h["asin"] for h in history}
    now = time.time()

    to_send: List[Dict[str, Any]] = []
    for p in products:
        if p["asin"] in seen:
            continue
        to_send.append(p)
        history.append({"asin": p["asin"], "ts": now})
        if len(to_send) >= MAX_OFFERS_SEND:
            break

    save_history(history)

    if not to_send:
        tg_text("ℹ️ Nessuna nuova offerta (tutte già pubblicate nelle ultime 24h).")
        return

    # invio su Telegram
    for p in to_send:
        lines = [f"🔥 <b>{p['title']}</b>"]

        if p.get("rating_stars"):
            lines.append(f"⭐ {p['rating_stars']}")
        if p.get("review_count"):
            lines.append(f"💬 {p['review_count']} recensioni")

        lines.append(f"💶 Prezzo: <b>{p['price_now_str']}</b>")
        lines.append(f"❌ Prezzo consigliato: <s>{p['list_price_str']}</s>")
        lines.append(f"🎯 Sconto: <b>-{p['discount_pct']}%</b>")
        lines.append("")
        lines.append(f"🔗 <a href='{p['url']}'>Apri l'offerta</a>")

        caption = "\n".join(lines)

        if p.get("image"):
            tg_photo(p["image"], caption)
        else:
            tg_text(caption)

    tg_text(f"✅ <b>Pubblicate {len(to_send)} offerte con lo sconto più alto.</b>")


if __name__ == "__main__":
    main()
