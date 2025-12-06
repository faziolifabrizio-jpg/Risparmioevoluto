import asyncio
import json
import os
import time
from pathlib import Path
import requests
from playwright.async_api import async_playwright

# =========================
#   CONFIG
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
AFF_TAG = "risparmioevol-21"

# Storico per evitare duplicati (24h)
HISTORY_FILE = Path("published.json")
if not HISTORY_FILE.exists():
    HISTORY_FILE.write_text(json.dumps({}))


def load_history():
    try:
        data = json.loads(HISTORY_FILE.read_text())
        cutoff = time.time() - 86400  # ultimi 7 giorni
        return {asin: ts for asin, ts in data.items() if ts > cutoff}
    except:
        return {}


def save_history(history):
    HISTORY_FILE.write_text(json.dumps(history))


# =========================
#   TELEGRAM
# =========================
def tg_send_text(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML"
    })
    print("[TG text]", r.status_code)


def tg_send_photo(photo_url, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    r = requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "HTML"
    })
    print("[TG photo]", r.status_code)


# =========================
# PARSING CARD AMAZON
# =========================
async def parse_card(card, page):
    asin = await card.get_attribute("data-asin")
    if not asin or asin.strip() == "":
        return None

    # ==== TITOLO (dalla card) ====
    try:
        raw_title = await card.locator(
            "h2, span.a-size-base-plus, span.a-size-medium"
        ).first.inner_text(timeout=2000)
        raw_title = raw_title.strip()
    except:
        raw_title = ""

    # Filtra titoli scarsi
    title_blacklist = ["pack", "kg", "ml", "pez", "litro", "variante", "conf", "%"]
    if len(raw_title) < 20 or any(w in raw_title.lower() for w in title_blacklist):
        raw_title = None

    # ==== Recupero titolo visitando la pagina ====
    if not raw_title:
        prod_page = await page.context.new_page()
        try:
            await prod_page.goto(f"https://www.amazon.it/dp/{asin}", timeout=25000)
            await prod_page.wait_for_selector("#productTitle", timeout=8000)
            raw_title = await prod_page.locator("#productTitle").inner_text()
            raw_title = raw_title.strip()
        except:
            raw_title = f"Prodotto {asin}"
        finally:
            await prod_page.close()

    # ==== PREZZO ATTUALE ====
    price_now = None
    try:
        el = await card.query_selector("span.a-price > span.a-offscreen")
        if el:
            price_now = (await el.inner_text()).strip()
    except:
        pass

    # ==== PREZZO CONSIGLIATO (NO €/L, €/kg ecc.) ====
    price_list = None
    try:
        el2 = await card.query_selector("span.a-text-price > span.a-offscreen")
        if el2:
            p = (await el2.inner_text()).strip()

            blacklist = ["/l", "/kg", "/ml", "/100", "litro", "kg", "ml"]
            if not any(x in p.lower() for x in blacklist):
                price_list = p
    except:
        pass

    # ==== CALCOLO SCONTO ====
    discount = None
    try:
        if price_now and price_list:
            p_now = float(price_now.replace("€", "").replace(",", "."))
            p_list = float(price_list.replace("€", "").replace(",", "."))
            if p_list > p_now:
                discount = int(((p_list - p_now) / p_list) * 100)
    except:
        pass

    if not discount or discount < 10:
        return None

    return {
        "asin": asin,
        "title": raw_title,
        "price_now": price_now,
        "price_list": price_list,
        "discount": discount,
        "img": f"https://m.media-amazon.com/images/I/{asin}.jpg",
        "url": f"https://www.amazon.it/dp/{asin}/?tag={AFF_TAG}"
    }


# =========================
# SCRAPING AMAZON
# =========================

SEARCH_PAGES = [
    "https://www.amazon.it/s?k=offerte",
    "https://www.amazon.it/s?k=offerte+oggi",
    "https://www.amazon.it/s?k=sconto"
]


async def scrape_all(page):
    results = {}

    for url in SEARCH_PAGES:
        print("[SCRAPE] Carico:", url)
        await page.goto(url, timeout=30000)

        # Cookie
        try:
            btn = page.locator("#sp-cc-accept")
            if await btn.is_visible():
                await btn.click()
                print("[COOKIE] Accettato")
        except:
            pass

        # Carte Amazon
        cards = await page.locator("div[data-asin]").element_handles()
        print("[SCRAPE] Carte trovate:", len(cards))

        for c in cards:
            data = await parse_card(c, page)
            if data:
                results[data["asin"]] = data

    print("[SCRAPE] Totale prodotti scontati:", len(results))
    return list(results.values())


# =========================
# MAIN
# =========================
async def main():
    tg_send_text("🔍 Cerco le migliori offerte Amazon…")

    history = load_history()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(locale="it-IT")
        page = await context.new_page()

        items = await scrape_all(page)

        # Rimuovi elementi pubblicati nelle ultime 24 ore
        items = [x for x in items if x["asin"] not in history]

        if not items:
            tg_send_text("❌ Nessuna nuova offerta trovata.")
            return

        # Ordina per sconto maggiore
        items.sort(key=lambda x: x["discount"], reverse=True)

        # Pubblica solo 10
        publish = items[:10]

        for p in publish:
            caption = f"""🔥 <b>{p['title']}</b>

💶 <b>{p['price_now']}</b>
❌ <s>{p['price_list']}</s>
🎯 Sconto: <b>{p['discount']}%</b>

🔗 <a href="{p['url']}">Apri l'offerta</a>
"""
            tg_send_photo(p["img"], caption)

            # Aggiorna storico
            history[p["asin"]] = time.time()
            save_history(history)

        tg_send_text("✅ Pubblicate 10 offerte migliori.")


if __name__ == "__main__":
    asyncio.run(main())
