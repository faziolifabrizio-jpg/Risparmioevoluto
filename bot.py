import os
import asyncio
from typing import List, Dict, Any, Set
from playwright.async_api import async_playwright
import requests

# ================== CONFIG ==================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
AFFILIATE_TAG = os.getenv("AFFILIATE_TAG", "risparmioevol-21")

# pagine di ricerca da usare (funzionano meglio di Goldbox)
SEARCH_URLS = [
    "https://www.amazon.it/s?k=offerte",
    "https://www.amazon.it/s?k=offerte+oggi",
    "https://www.amazon.it/s?k=sconto",
    "https://www.amazon.it/s?k=super+offerta",
]

MIN_DISCOUNT = 30   # sconto minimo in percentuale (> 30%)

MAX_ASIN = 30       # quanti ASIN massimo analizzare
MAX_OFFERS = 10     # quante offerte mandare a ogni run


# ================== TELEGRAM ==================

def tg_send(text: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TG] Manca TELEGRAM_TOKEN o TELEGRAM_CHAT_ID")
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML"
            },
            timeout=15
        )
        print("[TG]", r.status_code)
    except Exception as e:
        print("[TG ERRORE]", e)


# ================== UTILITY ==================

def parse_price(price_str: str) -> float:
    """
    Converte '1.234,56 €' → float 1234.56
    """
    if not price_str:
        return 0.0
    s = price_str
    s = s.replace("€", "").replace("\u00a0", "").strip()
    # togli i separatori di migliaia, cambia virgola in punto
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


def format_offer(prod: Dict[str, Any]) -> str:
    """
    Prepara il messaggio formattato per Telegram.
    """
    lines = []
    lines.append(f"🔥 <b>{prod['title']}</b>")
    if prod.get("stars") != "N/A" or prod.get("reviews") != "N/A":
        lines.append(f"⭐ {prod['stars']} • {prod['reviews']}")
    lines.append(f"💶 Prezzo: <b>{prod['price_now']}</b>")
    lines.append(f"❌ Prezzo precedente: <s>{prod['price_was']}</s>")
    lines.append(f"🎯 Sconto: <b>-{prod['discount']}%</b>")
    lines.append("")
    lines.append(f"🔗 <a href=\"{prod['link']}\">Apri l'offerta</a>")
    return "\n".join(lines)


# ================== PLAYWRIGHT HELPERS ==================

async def launch_browser(pw):
    """
    Avvia Chromium in modalità compatibile Railway FREE.
    """
    browser = await pw.chromium.launch(
        headless=True,
        args=[
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
            "--no-zygote",
            "--single-process",
        ],
    )
    return browser


async def accept_cookies_if_present(page):
    """
    Tenta di cliccare il pulsante 'Accetta' dei cookie, se presente.
    """
    try:
        btn = page.locator("#sp-cc-accept")
        if await btn.count() > 0:
            await btn.click()
            await asyncio.sleep(1)
            print("[COOKIE] Accettati")
    except Exception:
        pass


# ================== SCRAPING RICERCHE ==================

async def collect_asins_from_search(page) -> Set[str]:
    """
    Visita tutte le SEARCH_URLS, scrolla e raccoglie ASIN
    dalle card prodotto.
    """
    asins: Set[str] = set()
    first = True

    for url in SEARCH_URLS:
        print(f"[SEARCH] Carico: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)

        if first:
            await accept_cookies_if_present(page)
            first = False

        # pochi scroll per caricare più prodotti
        for i in range(5):
            await page.mouse.wheel(0, 4000)
            await asyncio.sleep(1)

            cards = page.locator("div.s-result-item[data-asin]")
            count = await cards.count()
            print(f"[SEARCH] Scroll {i+1}/5: carte trovate finora su questa pagina: {count}")

            for idx in range(count):
                asin = await cards.nth(idx).get_attribute("data-asin")
                if asin and len(asin) == 10:
                    asins.add(asin)

            if len(asins) >= MAX_ASIN:
                break

        print(f"[SEARCH] ASIN raccolti totali: {len(asins)}")
        if len(asins) >= MAX_ASIN:
            break

    return asins


# ================== SCRAPING PAGINA PRODOTTO ==================

async def scrape_product(page, asin: str) -> Dict[str, Any]:
    """
    Apre la pagina prodotto /dp/ASIN e ne estrae:
      - titolo
      - prezzo attuale
      - prezzo barrato
      - stelle
      - numero recensioni
    """
    url = f"https://www.amazon.it/dp/{asin}/?tag={AFFILIATE_TAG}"
    print(f"[PRODUCT] Carico prodotto {asin}…")
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)

    data: Dict[str, Any] = {"asin": asin, "link": url}

    # titolo
    try:
        title = await page.locator("#productTitle").inner_text()
        data["title"] = title.strip()
    except Exception:
        data["title"] = f"Prodotto {asin}"

    # prezzo attuale
    price_now = "N/A"
    try:
        price_now = await page.locator("span.a-price span.a-offscreen").first.inner_text()
    except Exception:
        try:
            price_now = await page.locator("span#priceblock_ourprice").inner_text()
        except Exception:
            price_now = "N/A"
    data["price_now"] = price_now

    # prezzo barrato / consigliato
    price_was = "N/A"
    try:
        price_was = await page.locator("span.a-text-price span.a-offscreen").first.inner_text()
    except Exception:
        price_was = "N/A"
    data["price_was"] = price_was

    # stelle
    try:
        stars = await page.locator("span[data-hook='rating-out-of-text']").first.inner_text()
        data["stars"] = stars.strip()
    except Exception:
        data["stars"] = "N/A"

    # numero recensioni
    try:
        reviews = await page.locator("#acrCustomerReviewText").first.inner_text()
        data["reviews"] = reviews.strip()
    except Exception:
        data["reviews"] = "N/A"

    # calcolo sconto
    now_val = parse_price(price_now)
    was_val = parse_price(price_was)
    if now_val > 0 and was_val > now_val:
        discount_pct = int(round((was_val - now_val) / was_val * 100))
    else:
        discount_pct = 0

    data["discount"] = discount_pct
    print(f"[PRODUCT] {asin}: sconto calcolato {discount_pct}%")

    return data


# ================== MAIN ==================

async def main():
    tg_send("🔍 Cerco offerte Amazon con sconto > 30%…")

    async with async_playwright() as pw:
        browser = await launch_browser(pw)
        context = await browser.new_context(locale="it-IT")
        page = await context.new_page()

        # 1) Raccolta ASIN dalle ricerche
        asins = await collect_asins_from_search(page)
        asins_list = list(asins)[:MAX_ASIN]
        print(f"[MAIN] ASIN totali raccolti: {len(asins_list)}")

        if not asins_list:
            tg_send("❌ Nessun prodotto trovato nelle ricerche.")
            await browser.close()
            return

        # 2) Scraping dettagli prodotto
        products: List[Dict[str, Any]] = []
        for asin in asins_list:
            try:
                p = await scrape_product(page, asin)
                # filtra per sconto minimo
                if p["discount"] >= MIN_DISCOUNT and p["price_now"] != "N/A" and p["price_was"] != "N/A":
                    products.append(p)
            except Exception as e:
                print(f"[ERR PRODUCT {asin}]", e)
            # piccola pausa per non stressare troppo
            await asyncio.sleep(1)

        await browser.close()

    if not products:
        tg_send(f"❌ Nessun prodotto con sconto > {MIN_DISCOUNT}% trovato.")
        return

    # 3) Ordina per sconto discendente e invia le migliori
    products.sort(key=lambda x: x["discount"], reverse=True)
    best = products[:MAX_OFFERS]

    tg_send(f"🎯 Trovate {len(products)} offerte con sconto > {MIN_DISCOUNT}%. Ecco le migliori {len(best)}:")

    for prod in best:
        msg = format_offer(prod)
        tg_send(msg)

    print("[MAIN] Completato, offerte inviate.")


if __name__ == "__main__":
    asyncio.run(main())
