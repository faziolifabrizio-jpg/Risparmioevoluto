import os
import re
import requests
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
URL = "https://www.amazon.it/gp/goldbox"

DEBUG = os.getenv("DEBUG", "0") == "1"

def send_telegram_text(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    resp = requests.post(url, data=data)
    print("Telegram text response:", resp.status_code, resp.text)

def send_telegram_photo(photo_url, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "photo": photo_url, "parse_mode": "Markdown"}
    resp = requests.post(url, data=data)
    print("Telegram photo response:", resp.status_code, resp.text)

def fetch_html():
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(URL, headers=headers, timeout=20)
    print("Amazon status:", r.status_code)

    if DEBUG:
        print("DEBUG mode attivo:", DEBUG)
        print("=== HTML DEBUG START ===")
        print(r.text[:2000])  # stampiamo i primi 2000 caratteri per non saturare i log
        print("=== HTML DEBUG END ===")

    return r.text if r.status_code == 200 else ""

def extract():
    html = fetch_html()
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []

    deal_items = soup.find_all("div", class_=re.compile(r"^DealGridItem-module__dealItem_"))
    print("DealGridItem trovati:", len(deal_items))

    def parse_node(node):
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

        reviews_node = node.select
