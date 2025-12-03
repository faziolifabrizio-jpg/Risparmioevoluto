import os
import re
import time
import requests
from bs4 import BeautifulSoup
import traceback

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DEBUG = os.getenv("DEBUG", "0") == "1"

# URL primario Goldbox (pagina ufficiale offerte)
PRIMARY_URL = "https://www.amazon.it/gp/goldbox"
# Fallback: pagina "search" con filtro offerte (Lightning/Deal) — layout server-side con s-card
FALLBACK_URLS = [
    # Tutte le categorie, filtro Deal type
    "https://www.amazon.it/s?rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",
    # Elettronica in offerta (esempio utile per vedere contenuti server-side)
    "https://www.amazon.it/s?i=electronics&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",
    # Casa e cucina
    "https://www.amazon.it/s?i=kitchen&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Referer": "https://www.amazon.it/",
    "Upgrade-Insecure-Requests": "1",
}

def send_telegram_text(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        resp = requests.post(url, data=data, timeout=20)
        print("Telegram text response:", resp.status_code, resp.text, flush=True)
    except Exception as e:
        print("Errore Telegram sendMessage:", e, flush=True)

def send_telegram_photo(photo_url: str, caption: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "photo": photo_url, "parse_mode": "Markdown"}
    try:
        resp = requests.post(url, data=data, timeout=20)
        print("Telegram photo response:", resp.status_code, resp.text, flush=True)
    except Exception as e:
        print("Errore Telegram sendPhoto:", e, flush=True)

def is_captcha(html: str) -> bool:
    text = html.lower()
    return ("robot check" in text) or ("inserisci i caratteri" in text) or ("captcha" in text)

def fetch_html(url: str, max_retries: int = 2) -> str:
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            print(f"[fetch_html] {url} status:", r.status_code, flush=True)
            if DEBUG:
                print("=== HTML DEBUG START ===", flush=True)
                print(r.text[:2000], flush=True)
                print("=== HTML DEBUG END ===", flush=True)

            if r.status_code == 200:
                if is_captcha(r.text):
                    print("Rilevato CAPTCHA/Robot Check", flush=True)
                    # Piccola pausa e ritenta con stesso URL
                    time.sleep(2)
                    continue
                return r.text
            else:
                time.sleep(2)
        except Exception as e:
            print(f"Errore richiesta ({url}) tentativo {attempt}:", e, flush=True)
            time.sleep(2)
    return ""

def parse_goldbox_layout(html: str) -> list:
    """Layout Goldbox (DealGridItem)."""
    soup = BeautifulSoup(html, "html.parser")
    deal_items = soup.find_all("div", class_=re.compile(r"^DealGridItem-module__dealItem_"))
    print("DealGridItem trovati:", len(deal_items), flush=True)

    results = []
    for node in deal_items:
        title_node = node.select_one("span.a-text-normal") or node.select_one("a.a-link-normal[aria-label]")
        if title_node and title_node.has_attr("aria-label"):
            title = title_node.get("aria-label")
        else:
            title = title_node.get_text(strip=True) if title_node else "N/A"

        img_node = node.select_one("img.s-image") or node.select_one("img")
        img = img_node.get("src") if img_node else None

        price_node = node.select_one("span.a-price span.a-offscreen") or node.select_one("span.a-offscreen")
        price = price_node.get_text(strip=True) if price_node else "N/A"

        old_price_node = node.select_one("span.a-text-price span.a-offscreen")
        old_price = old_price_node.get_text(strip=True) if old_price_node else "N/A"

        reviews_node = node.select_one("span.a-size-base") or node.select_one("span.a-size-small")
        reviews = reviews_node.get_text(strip=True) if reviews_node else "N/A"

        results.append({"title": title, "img": img, "price": price, "old_price": old_price, "reviews": reviews})
    return results

def parse_search_layout(html: str) -> list:
    """Layout 'search' delle offerte (s-card-container)."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("div.s-card-container")
    print("s-card-container trovati:", len(cards), flush=True)

    results = []
    for card in cards:
        title_node = card.select_one("h2 a span") or card.select_one("a.a-link-normal[aria-label]")
        if title_node and title_node.parent and title_node.parent.has_attr("aria-label"):
            title = title_node.parent.get("aria-label")
        elif title_node and hasattr(title_node, "get_text"):
            title = title_node.get_text(strip=True)
        else:
            title = "N/A"

        img_node = card.select_one("img.s-image") or card.select_one("img")
        img = img_node.get("src") if img_node else None
        if not img and img_node and img_node.has_attr("data-src"):
            img = img_node.get("data-src")

        # Prezzo
        price_node = card.select_one("span.a-price span.a-offscreen") or card.select_one("span.a-offscreen")
        price = price_node.get_text(strip=True) if price_node else "N/A"

        # Prezzo originale (barrato)
        old_price_node = card.select_one("span.a-text-price span.a-offscreen")
        old_price = old_price_node.get_text(strip=True) if old_price_node else "N/A"

        # Recensioni (numero/valutazioni)
        reviews_node = card.select_one("span.a-size-base") or card.select_one("span.a-size-small")
        reviews = reviews_node.get_text(strip=True) if reviews_node else "N/A"

        # Scarta card senza titolo e immagine
        if title == "N/A" and not img:
            continue

        results.append({"title": title, "img": img, "price": price, "old_price": old_price, "reviews": reviews})
    return results

def extract() -> list:
    print("Entrato in extract()", flush=True)

    # 1) Prova Goldbox ufficiale
    html = fetch_html(PRIMARY_URL)
    results = []
    if html:
        if is_captcha(html):
            print("Goldbox: CAPTCHA rilevato", flush=True)
        else:
            results = parse_goldbox_layout(html)

    # 2) Se vuoto, prova fallback "search" server-side
    if not results:
        print("Goldbox vuoto: avvio fallback search", flush=True)
        for url in FALLBACK_URLS:
            html_fb = fetch_html(url)
            if not html_fb:
                continue
            if is_captcha(html_fb):
                print("Fallback search: CAPTCHA rilevato, continuo", flush=True)
                continue
            parsed = parse_search_layout(html_fb)
            if parsed:
                results = parsed
                break

    # 3) Fallback extra: immagini s-image
    if not results and html:
        print("Fallback immagini s-image", flush=True)
        soup = BeautifulSoup(html, "html.parser")
        for img in soup.select("img.s-image")[:10]:
            title = img.get("alt", "N/A")
            results.append({"title": title, "img": img.get("src"), "price": "N/A", "old_price": "N/A", "reviews": "N/A"})

    print("Totale risultati estratti:", len(results), flush=True)
    return results[:8]

def main():
    print("Entrato in main(), DEBUG mode attivo:", DEBUG, flush=True)
    products = extract()
    print("Prodotti estratti:", len(products), flush=True)

    if not products:
        send_telegram_text("⚠️ Nessun prodotto trovato. Amazon potrebbe mostrare contenuti solo via JS o CAPTCHA. Ritenteremo.")
        return

    for p in products:
        if not p.get("img"):
            continue
        caption = (
            "🔥 *OFFERTA AMAZON*\n\n"
            f"📌 *{p.get('title','N/A')}*\n\n"
            f"💶 Prezzo: {p.get('price','N/A')}\n"
            f"❌ Prezzo consigliato: {p.get('old_price','N/A')}\n"
            f"⭐ Recensioni: {p.get('reviews','N/A')}\n\n"
            "🔗 https://www.amazon.it/gp/goldbox"
        )
        send_telegram_photo(p["img"], caption)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Errore in main:", e, flush=True)
        traceback.print_exc()
