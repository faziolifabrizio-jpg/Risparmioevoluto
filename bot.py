import os
import re
import time
import requests
from bs4 import BeautifulSoup
import traceback

# Variabili ambiente
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DEBUG = os.getenv("DEBUG", "0") == "1"

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

# Funzioni Telegram
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

# Funzioni scraping
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
                    time.sleep(2)
                    continue
                return r.text
            else:
                time.sleep(2)
        except Exception as e:
            print(f"Errore richiesta ({url}) tentativo {attempt}:", e, flush=True)
            time.sleep(2)
    return ""

def parse_search_layout(html: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("div.s-card-container, div.s-result-item[data-component-type='s-search-result']")
    print("Cards trovati:", len(cards), flush=True)

    results = []
    for card in cards[:10]:
        title_node = card.select_one("h2 a span") or card.select_one("a.a-link-normal[aria-label]")
        if title_node and title_node.parent and title_node.parent.has_attr("aria-label"):
            title = title_node.parent.get("aria-label")
        elif title_node:
            title = title_node.get_text(strip=True)
        else:
            title = "N/A"

        img_node = card.select_one("img.s-image") or card.select_one("img")
        img = None
        if img_node:
            for attr in ["src", "data-src", "data-image-src"]:
                if img_node.has_attr(attr) and img_node.get(attr):
                    img = img_node.get(attr)
                    break

        price_node = card.select_one("span.a-price span.a-offscreen") or card.select_one("span.a-offscreen")
        price = price_node.get_text(strip=True) if price_node else "N/A"

        old_price_node = card.select_one("span.a-text-price span.a-offscreen")
        old_price = old_price_node.get_text(strip=True) if old_price_node else "N/A"

        reviews_node = card.select_one("span.a-size-base") or card.select_one("span.a-size-small")
        reviews = reviews_node.get_text(strip=True) if reviews_node else "N/A"

        if title == "N/A" and not img and price == "N/A":
            continue

        results.append({
            "title": title,
            "img": img,
            "price": price,
            "old_price": old_price,
            "reviews": reviews
        })

    return results

def extract() -> list:
    print("Entrato in extract()", flush=True)

    FALLBACK_URLS = [
        "https://www.amazon.it/s?i=aps&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",  # Tutto
        "https://www.amazon.it/s?i=grocery&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",  # Alimentari
        "https://www.amazon.it/s?i=automotive&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",  # Auto e Moto
        "https://www.amazon.it/s?i=beauty&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",  # Bellezza
        "https://www.amazon.it/s?i=office-products&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",  # Ufficio
        "https://www.amazon.it/s?i=kitchen&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",  # Casa e cucina
        "https://www.amazon.it/s?i=music&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",  # CD e Vinili
        "https://www.amazon.it/s?i=industrial&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",  # Industria
        "https://www.amazon.it/s?i=electronics&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",  # Elettronica
        "https://www.amazon.it/s?i=diy&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",  # Fai da te
        "https://www.amazon.it/s?i=movies&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",  # Film e TV
        "https://www.amazon.it/s?i=garden&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",  # Giardino
        "https://www.amazon.it/s?i=toys&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",  # Giocattoli
        "https://www.amazon.it/s?i=appliances&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",  # Elettrodomestici
        "https://www.amazon.it/s?i=lighting&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",  # Illuminazione
        "https://www.amazon.it/s?i=computers&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",  # Informatica
        "https://www.amazon.it/s?i=digital-text&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",  # Kindle
        "https://www.amazon.it/s?i=stripbooks&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",  # Libri
        "https://www.amazon.it/s?i=fashion&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",  # Moda
        "https://www.amazon.it/s?i=baby&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank", 
