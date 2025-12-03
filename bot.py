import os
import time
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
URL = "https://www.amazon.it/gp/goldbox"

def send_telegram_text(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    resp = requests.post(url, data=data)
    print("Telegram response:", resp.status_code, resp.text)

def send_telegram_photo(photo_url, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "photo": photo_url, "parse_mode": "Markdown"}
    resp = requests.post(url, data=data)
    print("Telegram photo response:", resp.status_code, resp.text)

def extract():
    # Configura Chrome headless
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=options)

    driver.get(URL)
    time.sleep(5)  # aspetta che la pagina carichi le offerte via JS

    soup = BeautifulSoup(driver.page_source, "html.parser")
    driver.quit()

    results = []
    items = soup.select("div.a-section.a-spacing-none.gbh1") or soup.select("div.DealGridItem-module__dealItem_")
    print("Items trovati:", len(items))

    for item in items[:5]:
        title = item.select_one("span.a-text-normal")
        title = title.get_text(strip=True) if title else "N/A"

        img = item.select_one("img.s-image")
        img = img["src"] if img else None

        price = item.select_one("span.a-price span.a-offscreen")
        price = price.get_text(strip=True) if price else "N/A"

        old_price = item.select_one("span.a-text-price span.a-offscreen")
        old_price = old_price.get_text(strip=True) if old_price else "N/A"

        reviews = item.select_one("span.a-size-base")
        reviews = reviews.get_text(strip=True) if reviews else "N/A"

        results.append({
            "title": title,
            "img": img,
            "price": price,
            "old_price": old_price,
            "reviews": reviews
        })

    return results

def main():
    products = extract()
    if not products:
        send_telegram_text("⚠️ Nessun prodotto trovato su Amazon GoldBox. Il bot è attivo ma la pagina è vuota.")
        return

    for p in products:
        if not p["img"]:
            continue
        caption = f"""🔥 *OFFERTA AMAZON*

📌 *{p['title']}*

💶 Prezzo: {p['price']}
❌ Prezzo consigliato: {p['old_price']}
⭐ Recensioni: {p['reviews']}

🔗 https://www.amazon.it/gp/goldbox
"""
        send_telegram_photo(p["img"], caption)

if __name__ == "__main__":
    main()
