import os
import re
import requests
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
URL = "https://www.amazon.it/gp/goldbox"

def send_telegram_photo(photo_url, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "photo": photo_url, "parse_mode": "Markdown"}
    resp = requests.post(url, data=data)
    print("Telegram photo response:", resp.status_code, resp.text)

def send_telegram_text(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    resp = requests.post(url, data=data)
    print("Telegram text response:", resp.status_code, resp.text)

def fetch_html():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0 Safari/537.36",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    r = requests.get(URL, headers=headers, timeout=20)
    print("Amazon status:", r.status_code)
    return r.text if r.status_code == 200 else ""

def extract():
    html = fetch_html()
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []

    # Card delle offerte (regex per classi dinamiche DealGridItem)
    deal_items = soup.find_all("div", class_=re.compile(r"^DealGridItem-module__dealItem_"))
    print("DealGridItem trovati:", len(deal_items))

    def parse_node(node):
        title_node = (node.select_one("span.a-text-normal")
                      or node.select_one("a.a-link-normal[aria-label]"))
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

        return {"title": title, "img": img, "price": price, "old_price": old_price, "reviews": reviews}

    for node in deal_items[:8]:
        results.append(parse_node(node))

    # Fallback: cerca blocchi prezzo/immagine nel DOM se non trova card
    if not results:
        print("Fallback parsing attivato.")
        price_blocks = soup.select("span.a-price")
        for pb in price_blocks[:10]:
            container = pb.find_parent(["div", "li", "a"])
            parsed = parse_node(container or pb)
            if parsed["title"] != "N/A" or parsed["img"]:
                results.append(parsed)

    # Deduplica
    unique = []
    seen = set()
    for r in results:
        key = (r["title"], r["price"])
        if r["title"] != "N/A" and key not in seen:
            seen.add(key)
            unique.append(r)

    print("Totale risultati estratti:", len(unique))
    return unique[:5]

def main():
    products = extract()
    if not products:
        print("Nessun prodotto trovato.")
        send_telegram_text("⚠️ Nessun prodotto trovato su Amazon GoldBox. Il bot è attivo ma non ha trovato offerte.")
        return

    for p in products:
        if not p["img"]:
            print("Prodotto senza immagine:", p["title"])
            continue
        caption = f"""🔥 *OFFERTA AMAZON*

📌 *{p['title']}*

💶 Prezzo: {p['price']}
❌ Prezzo consigliato: {p['old_price']}
⭐ Recensioni: {p['reviews']}

🔗 https://www.amazon.it/gp/goldbox
"""
        print("Invio prodotto:", p["title"])
        send_telegram_photo(p["img"], caption)

if __name__ == "__main__":
    main()
