import asyncio
from playwright.async_api import async_playwright
import json
import os
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
AFF_TAG = "risparmioevol-21"

GOLDBOX_URL = "https://www.amazon.it/gp/goldbox"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "it-IT,it;q=0.9"
}

# --------------------------------------
# TELEGRAM
# --------------------------------------
def send_tg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML"
    })

# --------------------------------------
# LOAD / SAVE PUBLISHED
# --------------------------------------
def load_published():
    if not os.path.exists("published.json"):
        return []
    return json.load(open("published.json"))

def save_published(lst):
    json.dump(lst, open("published.json", "w"))

# --------------------------------------
# PRICE PARSER
# --------------------------------------
def clean_price(p):
    if not p:
        return None
    p = p.replace("€", "").replace(",", ".").strip()
    try:
        return float(p)
    except:
        return None

# --------------------------------------
# SCRAPE PAGINA PRODOTTO
# --------------------------------------
async def scrape_product(page, asin):
    url = f"https://www.amazon.it/dp/{asin}?tag={AFF_TAG}"

    await page.goto(url)

    # titolo
    try:
        title = await page.locator("#productTitle").inner_text(timeout=5000)
        title = title.strip()
    except:
        title = "N/A"

    # prezzo attuale
    try:
        price_now = await page.locator("span.a-price span.a-offscreen").first.inner_text()
        price_now = clean_price(price_now)
    except:
        price_now = None

    # prezzo consigliato (prezzo barrato)
    try:
        price_old = await page.locator("span.a-text-price span.a-offscreen").first.inner_text()
        price_old = clean_price(price_old)
    except:
        price_old = None

    # stelle
    try:
        stars = await page.locator("span[data-hook='rating-out-of-text']").inner_text()
    except:
        stars = "N/A"

    # recensioni
    try:
        reviews = await page.locator("#acrCustomerReviewText").inner_text()
    except:
        reviews = "N/A"

    discount = 0
    if price_now and price_old and price_old > price_now:
        discount = int((1 - price_now / price_old) * 100)

    return {
        "asin": asin,
        "title": title,
        "price_now": price_now,
        "price_old": price_old,
        "discount": discount,
        "stars": stars,
        "reviews": reviews
    }

# --------------------------------------
# GOLD BOX LIST
# --------------------------------------
async def get_goldbox_asins(page):
    await page.goto(GOLDBOX_URL)

    # cookie banner
    try:
        await page.locator("#sp-cc-accept").click(timeout=3000)
    except:
        pass

    asins = set()

    # scroll max 12 volte
    for i in range(12):
        await page.evaluate("window.scrollBy(0, 2000)")
        await asyncio.sleep(1)

        items = page.locator("div[data-asin]")
        count = await items.count()

        for j in range(count):
            asin = await items.nth(j).get_attribute("data-asin")
            if asin and len(asin) == 10:
                asins.add(asin)

    return list(asins)[:100]

# --------------------------------------
# MAIN
# --------------------------------------
async def main():
    send_tg("🔍 Analizzo le offerte Amazon Goldbox…")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # 1) estrai ASIN goldbox
        asins = await get_goldbox_asins(page)

        if not asins:
            send_tg("❌ Nessun prodotto trovato su Goldbox.")
            return

        published = load_published()
        result = []

        # 2) analizza fino a 40 prodotti
        for asin in asins[:40]:
            if asin in published:
                continue
            data = await scrape_product(page, asin)
            if data["discount"] >= 10:  # minimo 10% sconto
                result.append(data)

        await browser.close()

    if not result:
        send_tg("❌ Nessuna offerta valida trovata.")
        return

    # ordina per sconto
    result = sorted(result, key=lambda x: x["discount"], reverse=True)

    # invia solo i primi 10
    new_asins = []

    for product in result[:10]:
        link = f"https://www.amazon.it/dp/{product['asin']}?tag={AFF_TAG}"

        msg = (
            f"🔥 <b>{product['title']}</b>\n"
            f"⭐ {product['stars']} ({product['reviews']})\n"
            f"💶 Prezzo: {product['price_now']}€\n"
            f"❌ Prezzo consigliato: {product['price_old']}€\n"
            f"🎯 Sconto: -{product['discount']}%\n\n"
            f"🔗 <a href='{link}'>Apri l'offerta</a>"
        )

        send_tg(msg)
        new_asins.append(product["asin"])

    # salva per evitare ripubblicazione ultime 24h
    published = new_asins + published
    save_published(published[:30])

if __name__ == "__main__":
    asyncio.run(main())
