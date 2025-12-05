import os
import asyncio
import json
from playwright.async_api import async_playwright
import time
import requests

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
AFFILIATE_TAG = os.getenv("AFFILIATE_TAG", "risparmioevol-21")

GOLDBOX_URL = "https://www.amazon.it/deals"

# ---- TELEGRAM ----
def tg(text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception as e:
        print("[TG ERROR]", e)


# ---- BROWSER LAUNCH (COMPATIBILE RAILWAY FREE) ----
async def launch_browser(playwright):
    return await playwright.chromium.launch(
        headless=True,
        args=[
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
            "--no-zygote",
            "--single-process"
        ]
    )


# ---- ESTRAE I PRODOTTI DALLA PAGINA GOLDBOX ----
async def scrape_goldbox(page):
    print("[SCRAPE] Apro Goldbox…")
    await page.goto(GOLDBOX_URL, wait_until="domcontentloaded", timeout=60000)

    # cookies
    try:
        cookie_btn = page.locator("#sp-cc-accept")
        if await cookie_btn.count() > 0:
            await cookie_btn.click()
            await asyncio.sleep(1)
            print("[COOKIE] accettato")
    except:
        pass

    all_asins = set()

    # scroll controllato
    for i in range(8):  # ridotto per Railway FREE
        await page.mouse.wheel(0, 5000)
        await asyncio.sleep(1.5)

        cards = await page.locator("div[data-asin]").all()

        for c in cards:
            asin = await c.get_attribute("data-asin")
            if asin and len(asin) == 10:
                all_asins.add(asin)

        print(f"[SCRAPE] Scroll {i+1}/8 → ASIN raccolti: {len(all_asins)}")

    return list(all_asins)[:20]   # LIMITO A 20 PER EVITARE CRASH


# ---- SCRAPING PAGINA PRODOTTO ----
async def scrape_product(page, asin):
    url = f"https://www.amazon.it/dp/{asin}"

    print(f"[PRODUCT] Carico {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)

    data = {}

    # Titolo
    try:
        title = await page.locator("#productTitle").inner_text()
        data["title"] = title.strip()
    except:
        data["title"] = "N/A"

    # Prezzo attuale
    try:
        price_now = await page.locator(".a-price .a-offscreen").first.inner_text()
        data["price_now"] = price_now
    except:
        data["price_now"] = "N/A"

    # Prezzo consigliato
    try:
        price_cross = await page.locator("span.a-text-price .a-offscreen").first.inner_text()
        data["price_was"] = price_cross
    except:
        data["price_was"] = "N/A"

    # Stelle
    try:
        stars = await page.locator("span[data-hook='rating-out-of-text']").first.inner_text()
        data["stars"] = stars
    except:
        data["stars"] = "N/A"

    # Numero recensioni
    try:
        reviews = await page.locator("#acrCustomerReviewText").first.inner_text()
        data["reviews"] = reviews
    except:
        data["reviews"] = "N/A"

    # Link affiliato
    data["link"] = f"https://www.amazon.it/dp/{asin}/?tag={AFFILIATE_TAG}"

    return data


# ---- FORMATTATORE OFFERTA ----
def format_offer(p):
    msg = f"🔥 <b>{p['title']}</b>\n"
    msg += f"⭐ {p['stars']} • {p['reviews']}\n"
    msg += f"💶 Prezzo: <b>{p['price_now']}</b>\n"
    msg += f"❌ Prezzo precedente: {p['price_was']}\n"
    msg += f"\n🔗 <a href=\"{p['link']}\">Apri l'offerta</a>"
    return msg


# ---- MAIN ----
async def main():
    tg("🔍 Avvio ricerca offerte Amazon (Railway)…")

    async with async_playwright() as pw:
        browser = await launch_browser(pw)
        context = await browser.new_context()
        page = await context.new_page()

        # Scrape Goldbox ASIN
        asins = await scrape_goldbox(page)

        if not asins:
            tg("❌ Nessun prodotto trovato in Goldbox.")
            return

        tg(f"📦 {len(asins)} prodotti individuati. Analizzo prezzi…")

        offers = []

        for asin in asins:
            try:
                p = await scrape_product(page, asin)

                if p["price_now"] != "N/A" and p["price_was"] != "N/A":
                    offers.append(p)

                await asyncio.sleep(1)
            except Exception as e:
                print("[ERR PRODUCT]", e)

        if not offers:
            tg("❌ Nessuna offerta valida.")
            return

        # ordina per sconto %
        def parse_price(x):
            try:
                return float(x.replace("€","").replace(",","."))
            except:
                return 0

        def discount(p):
            return parse_price(p["price_was"]) - parse_price(p["price_now"])

        offers = sorted(offers, key=discount, reverse=True)[:10]

        tg("🎯 <b>Migliori 10 offerte Goldbox:</b>")

        for o in offers:
            tg(format_offer(o))

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
