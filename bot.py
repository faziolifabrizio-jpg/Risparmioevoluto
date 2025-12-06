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

MAX_CARDS_PER_PAGE = 40      # quante card massimo per ogni pagina search
MIN_DISCOUNT = 10            # sconto minimo in %
MAX_OFFERS_SEND = 10         # quante offerte mandare su Telegram per ogni run

SEARCH_PAGES = [
    "https://www.amazon.it/s?k=offerte",
    "https://www.amazon.it/s?k=offerte+oggi",
    "https://www.amazon.it/s?k=sconto",
]

# Memorizza ASIN pubblicati nelle ultime 24 ore
HISTORY_FILE = Path("published.json")
if not HISTORY_FILE.exists():
    HISTORY_FILE.write_text(json.dumps({}))


def load_history():
    try:
        data = json.loads(HISTORY_FILE.read_text())
        cutoff = time.time() - 86400  # 24 ore
        return {asin: ts for asin, ts in data.items() if ts > cutoff}
    except Exception:
        return {}


def save_history(history):
    HISTORY_FILE.write_text(json.dumps(history))


# =========================
#   TELEGRAM
# =========================
def tg_send_text(msg: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TG TEXT] Variabili non impostate, salto invio")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(
        url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML",
        },
        timeout=20,
    )
    print("[TG TEXT]", r.status_code)


def tg_send_photo(photo_url: str, caption: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TG PHOTO] Variabili non impostate, salto invio")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    r = requests.post(
        url,
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "photo": photo_url,
            "caption": caption,
            "parse_mode": "HTML",
        },
        timeout=20,
    )
    print("[TG PHOTO]", r.status_code)


# ===============================
#   DETTAGLIO PAGINA PRODOTTO
# ===============================
async def get_full_product_data(asin: str, context):
    """Visita la pagina prodotto e prende titolo, prezzi e sconto reali."""
    url = f"https://www.amazon.it/dp/{asin}"
    page = await context.new_page()
    print(f"[DETAIL] Apro pagina prodotto per ASIN {asin}")

    title = f"Prodotto {asin}"
    price_now = None
    price_list = None
    discount = None

    try:
        await page.goto(url, timeout=30000)

        # Cookie
        try:
            if await page.locator("#sp-cc-accept").is_visible():
                await page.locator("#sp-cc-accept").click()
                print("[DETAIL COOKIE] Accettato")
        except Exception:
            pass

        # Titolo
        try:
            await page.wait_for_selector("span#productTitle", timeout=8000)
            t = await page.locator("span#productTitle").inner_text()
            title = t.strip()
        except Exception:
            pass

        # Prezzo attuale
        try:
            pnow = await page.locator("span.a-price span.a-offscreen").first.inner_text()
            price_now = pnow.strip()
        except Exception:
            pass

        # Prezzo consigliato (intelligente)
        try:
            candidates = await page.locator(
                "span.a-price.a-text-price > span.a-offscreen, "
                "span.a-size-small.a-color-secondary.a-text-strike"
            ).all_inner_texts()

            blacklist = ["/l", "/kg", "/ml", "/100", "litro", "kg", "ml", "al "]

            for raw in candidates:
                p = raw.strip()
                if any(x in p.lower() for x in blacklist):
                    continue
                try:
                    val = float(p.replace("€", "").replace(",", "."))
                    if price_now:
                        now_val = float(price_now.replace("€", "").replace(",", "."))
                        if val > now_val:
                            price_list = p
                            break
                except Exception:
                    continue
        except Exception:
            pass

        # Sconto
        try:
            if price_now and price_list:
                p_now = float(price_now.replace("€", "").replace(",", "."))
                p_list = float(price_list.replace("€", "").replace(",", "."))
                if p_list > p_now:
                    discount = round(100 - (p_now / p_list * 100))
        except Exception:
            pass

    finally:
        await page.close()

    print(f"[DETAIL] ASIN {asin} → titolo OK, sconto: {discount}")
    return {
        "title": title,
        "price_now": price_now,
        "price_list": price_list,
        "discount": discount,
        "url": url,
    }


# =========================
# PARSING CARD AMAZON
# =========================
async def parse_card(card, page, idx: int, total: int):
    print(f"[CHECK] Card {idx}/{total} → analizzo…")
    asin = await card.get_attribute("data-asin")
    if not asin or asin.strip() == "":
        return None

    # --- Titolo dalla card ---
    raw_title = None
    try:
        t = await card.locator(
            "h2 a span, h2 span, span.a-size-base-plus, span.a-size-medium"
        ).first.inner_text(timeout=1000)
        t = t.strip()
        raw_title = t
    except Exception:
        raw_title = None

    # Filtra titoli inutili/brevi
    bad_words = ["pack", "kg", "ml", "pez", "litro", "variante", "conf", "%"]
    if raw_title:
        if len(raw_title) < 20 or any(w in raw_title.lower() for w in bad_words):
            raw_title = None

    # --- Prezzo dalla card ---
    price_now = None
    try:
        el = await card.query_selector("span.a-price > span.a-offscreen")
        if el:
            price_now = (await el.inner_text()).strip()
    except Exception:
        pass

    price_list = None
    try:
        el2 = await card.query_selector("span.a-text-price > span.a-offscreen")
        if el2:
            p = (await el2.inner_text()).strip()
            bad = ["/l", "/kg", "/ml", "/100", "litro", "kg", "ml"]
            if not any(x in p.lower() for x in bad):
                price_list = p
    except Exception:
        pass

    # --- Sconto calcolato dalla card ---
    discount = None
    try:
        if price_now and price_list:
            p_now = float(price_now.replace("€", "").replace(",", "."))
            p_list = float(price_list.replace("€", "").replace(",", "."))
            if p_list > p_now:
                discount = round(100 - (p_now / p_list * 100))
    except Exception:
        discount = None

    # Se titolo o prezzo consigliato mancano, o sconto è None → entro nella pagina prodotto
    if raw_title is None or price_list is None or discount is None:
        details = await get_full_product_data(asin, page.context)
        raw_title = details["title"]
        price_now = details["price_now"]
        price_list = details["price_list"]
        discount = details["discount"]

    # Se ancora niente sconto valido → scarta
    if not discount or discount < MIN_DISCOUNT:
        print(f"[SKIP] ASIN {asin} → sconto insufficiente ({discount})")
        return None

    print(f"[OK] ASIN {asin} → sconto {discount}%")
    return {
        "asin": asin,
        "title": raw_title,
        "price_now": price_now,
        "price_list": price_list,
        "discount": discount,
        "img": f"https://m.media-amazon.com/images/I/{asin}.jpg",
        "url": f"https://www.amazon.it/dp/{asin}/?tag={AFF_TAG}",
    }


# =========================
# SCRAPING AMAZON
# =========================
async def scrape_all(page):
    results = {}

    for url in SEARCH_PAGES:
        print("[SCRAPE] Carico:", url)
        await page.goto(url, timeout=30000)

        # Cookie
        try:
            if await page.locator("#sp-cc-accept").is_visible():
                await page.locator("#sp-cc-accept").click()
                print("[COOKIE] Accettato")
        except Exception:
            pass

        cards = await page.locator("div[data-asin]").element_handles()
        total_cards = len(cards)
        print(f"[SCRAPE] Carte trovate: {total_cards}")

        # Limitiamo il numero di card per velocizzare
        cards = cards[:MAX_CARDS_PER_PAGE]
        print(f"[SCRAPE] Analizzo solo le prime {len(cards)} card")

        for idx, c in enumerate(cards, start=1):
            data = await parse_card(c, page, idx, len(cards))
            if data:
                results[data["asin"]] = data

    print("[SCRAPE] Totale prodotti scontati (deduplicati):", len(results))
    return list(results.values())


# =========================
# MAIN BOT
# =========================
async def main():
    tg_send_text("🔍 Cerco le migliori offerte Amazon…")

    history = load_history()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(locale="it-IT")
        page = await context.new_page()

        items = await scrape_all(page)

        # Rimuovi già pubblicati (24h)
        items = [x for x in items if x["asin"] not in history]

        if not items:
            tg_send_text("❌ Nessuna nuova offerta trovata.")
            await browser.close()
            return

        # Ordina per sconto
        items.sort(key=lambda x: x["discount"], reverse=True)

        publish = items[:MAX_OFFERS_SEND]

        for p_item in publish:
            caption = f"""🔥 <b>{p_item['title']}</b>

💶 <b>{p_item['price_now']}</b>
❌ <s>{p_item['price_list']}</s>
🎯 Sconto: <b>{p_item['discount']}%</b>

🔗 <a href="{p_item['url']}">Apri l'offerta</a>
"""
            tg_send_photo(p_item["img"], caption)
            history[p_item["asin"]] = time.time()
            save_history(history)

        await browser.close()
        tg_send_text(f"✅ Pubblicate {len(publish)} offerte migliori (per sconto).")


if __name__ == "__main__":
    asyncio.run(main())
