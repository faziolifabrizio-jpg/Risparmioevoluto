import os
import time
import random
import requests
from bs4 import BeautifulSoup

# Porta finta per Render
from http.server import SimpleHTTPRequestHandler
import socketserver
import threading

def fake_webserver():
    PORT = int(os.getenv("PORT", 10000))
    httpd = socketserver.TCPServer(("", PORT), SimpleHTTPRequestHandler)
    httpd.serve_forever()

threading.Thread(target=fake_webserver, daemon=True).start()

# ================================
# CONFIGURAZIONE
# ================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
AFFILIATE_TAG = "risparmioevol-21"
DEBUG = os.getenv("DEBUG", "0") == "1"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.amazon.it/"
}

FALLBACK_URLS = [
    "https://www.amazon.it/s?i=electronics&rh=p_n_deal_type%3A26980358031",
    "https://www.amazon.it/s?i=computers&rh=p_n_deal_type%3A26980358031",
    "https://www.amazon.it/s?i=toys&rh=p_n_deal_type%3A26980358031",
    "https://www.amazon.it/s?i=kitchen&rh=p_n_deal_type%3A26980358031",
    "https://www.amazon.it/s?i=beauty&rh=p_n_deal_type%3A26980358031"
]


# ================================
# FUNZIONI TELEGRAM
# ================================
def send_telegram_text(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, data=data, timeout=15)
        print("Telegram-text:", r.status_code)
    except Exception as e:
        print("Errore Telegram:", e)


def send_telegram_photo(photo_url: str, caption: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    data = {"chat_id": TELEGRAM_CHAT_ID, "photo": photo_url, "caption": caption, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, data=data, timeout=15)
        print("Telegram-photo:", r.status_code)
    except Exception as e:
        print("Errore Telegram-photo:", e)


# ================================
# PARSING AMAZON
# ================================
def is_captcha(html: str) -> bool:
    t = html.lower()
    return "captcha" in t or "robot" in t or "inserisci i caratteri" in t


def fetch_html(url: str) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        if r.status_code == 200 and not is_captcha(r.text):
            return r.text
    except:
        return ""
    return ""


def parse_cards(html: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("div.s-card-container, div.s-result-item[data-component-type='s-search-result']")
    results = []

    for card in cards[:10]:
        # Titolo
        title_node = card.select_one("h2 a span")
        title = title_node.get_text(strip=True) if title_node else "N/A"

        # Immagine
        img_node = card.select_one("img.s-image")
        img = img_node["src"] if img_node else None

        # Prezzo
        price_node = card.select_one("span.a-price span.a-offscreen")
        price = price_node.get_text(strip=True) if price_node else "N/A"

        # Vecchio prezzo
        old_node = card.select_one("span.a-text-price span.a-offscreen")
        old_price = old_node.get_text(strip=True) if old_node else "N/A"

        # Link
        link_node = card.select_one("h2 a")
        link = None
        if link_node and link_node.get("href"):
            href = link_node["href"]
            if href.startswith("/"):
                href = "https://www.amazon.it" + href

            # Applicazione tag affiliate
            if "tag=" not in href:
                href += ("&tag=" + AFFILIATE_TAG) if "?" in href else ("?tag=" + AFFILIATE_TAG)

            link = href

        if img and link:
            results.append({
                "title": title,
                "img": img,
                "price": price,
                "old_price": old_price,
                "link": link
            })

    return results


def extract():
    for url in FALLBACK_URLS:
        time.sleep(random.uniform(1.2, 2.2))
        html = fetch_html(url)
        if html:
            res = parse_cards(html)
            if res:
                return res[:6]
    return []


# ================================
# ROUTINE PRINCIPALE
# ================================
def main_routine():
    send_telegram_text("🔍 Sto cercando le offerte Amazon, un attimo...")

    products = extract()
    if not products:
        send_telegram_text("❌ Nessuna offerta trovata. Amazon potrebbe aver mostrato CAPTCHA.")
        return

    for p in products:
        caption = (
            f"🔥 *OFFERTA AMAZON*\n\n"
            f"📌 *{p['title']}*\n"
            f"💶 Prezzo: *{p['price']}*\n"
            f"💸 Vecchio prezzo: {p['old_price']}\n\n"
            f"🔗 [Apri l'offerta]({p['link']})"
        )

        send_telegram_photo(p["img"], caption)


# ================================
# SCHEDULER INTERNO (NO CRON)
# ================================
def scheduler_loop():
    send_telegram_text("🤖 Bot avviato correttamente e in attesa (Render FREE).")

    while True:
        current = time.strftime("%H:%M")

        if current in ("09:00", "21:00"):
            print("⏰ ORARIO PROGRAMMATO! Invio offerte…")
            main_routine()
            time.sleep(65)  # evita doppio invio

        time.sleep(20)


if __name__ == "__main__":
    scheduler_loop()
