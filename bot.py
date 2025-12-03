import requests
from bs4 import BeautifulSoup
import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

URL = "https://www.amazon.it/gp/goldbox"

def send_telegram(photo_url, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "caption": text,
        "photo": photo_url,
        "parse_mode": "Markdown"  # abilita grassetto, emoji ecc.
    }
    resp = requests.post(url, data=data)
    print("Telegram response:", resp.status_code, resp.text)

def extract():
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(URL, headers=headers)
    print("Amazon status:", r.status_code)
    soup = BeautifulSoup(r.text, "html.parser")

    items = soup.select("div.GBHb")
    print(f"Trovati {len(items)} items")
    results = []
    for item in items[:5]:
        title = item.select_one("h2")
        title = title.get_text(strip=True) if title else "N/A"

        img = item.select_one("img")
        img = img["src"] if img else None

        price = item.select_one(".a-price .a-offscreen")
        price = price.get_text(strip=True) if price else "N/A"

        old_price = item.select_one(".a-text-price .a-offscreen")
        old_price = old_price.get_text(strip=True) if old_price else "N/A"

        last30 = item.select_one(".a-size-base.a-color-secondary")
        last30 = last30.get_text(strip=True) if last30 else "N/A"

        reviews = item.select_one(".a-size-small .a-link-normal")
        reviews = reviews.get_text(strip=True) if reviews else "N/A"

        results.append({
            "title": title,
            "img": img,
            "price": price,
            "old_price": old_price,
            "last30": last30,
            "reviews": reviews
        })
    return results

def main():
    products = extract()
    if not products:
        print("Nessun prodotto trovato.")
    for p in products:
        if not p["img"]:
            print(f"Prodotto senza immagine: {p['title']}")
            continue
        text = f"""🔥 *OFFERTA AMAZON*

📌 *{p['title']}*

💶 Prezzo: {p['price']}
❌ Prezzo Consigliato: {p['old_price']}
📉 Ultimi 30 giorni: {p['last30']}
⭐ Recensioni: {p['reviews']}

🔗 https://www.amazon.it/gp/goldbox
"""
        send_telegram(p["img"], text)

if __name__ == "__main__":
    main()
