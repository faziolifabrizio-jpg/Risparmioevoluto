import asyncio
import json
import os
import time
import html
import re

import requests
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# ================== CONFIG ==================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or "INSERISCI_TUO_TOKEN"
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID") or "INSERISCI_CHAT_ID"
AFFILIATE_TAG = "risparmioevol-21"

SEARCH_URLS = [
    "https://www.amazon.it/s?k=offerte",
    "https://www.amazon.it/s?k=offerte+oggi",
    "https://www.amazon.it/s?k=sconto",
]

MIN_DISCOUNT = 20          # sconto minimo %
MAX_PRODUCTS = 20          # massimo prodotti da pubblicare per esecuzione

PUBLISHED_FILE = "published.json"
PUBLISHED_ENV_VAR = "PUBLISHED_CACHE"   # per cache in memoria (utile su Railway)

# ================== UTILS ==================


def h(text: str) -> str:
    """Escape HTML per Telegram."""
    return html.escape(str(text), quote=False)


def fmt_eur(val: float) -> str:
    try:
        return f"{val:.2f}".replace(".", ",") + "€"
    except Exception:
        return str(val)


def load_published() -> dict:
    """Carica gli ASIN già pubblicati da env + file locale."""
    data: dict[str, float] = {}

    # Da env (solo per la sessione corrente)
    env_val = os.getenv(PUBLISHED_ENV_VAR)
    if env_val:
        try:
            env_data = json.loads(env_val)
            if isinstance(env_data, dict):
                for k, v in env_data.items():
                    try:
                        data[k] = float(v)
                    except Exception:
                        pass
        except Exception:
            pass

    # Da file locale
    if os.path.exists(PUBLISHED_FILE):
        try:
            with open(PUBLISHED_FILE, "r", encoding="utf-8") as f:
                file_data = json.load(f)
            if isinstance(file_data, dict):
                for k, v in file_data.items():
                    try:
                        v_float = float(v)
                        data[k] = max(v_float, data.get(k, 0.0))
                    except Exception:
                        pass
        except Exception:
            pass

    return data


def save_published(data: dict):
    """Salva lo storico pubblicazioni su file + env (per la sessione)."""
    try:
        with open(PUBLISHED_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print("[PUBLISHED] Errore salvataggio file:", e)

    try:
        os.environ[PUBLISHED_ENV_VAR] = json.dumps(data)
    except Exception:
        pass


def send_telegram_photo(image_url: str | None, caption: str):
    """Invia foto se disponibile, altrimenti solo testo, senza spam di errori sul canale."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[TG] TELEGRAM_TOKEN o TELEGRAM_CHAT_ID non impostati")
        return

    try:
        if image_url:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "photo": image_url,
                "caption": caption,
                "parse_mode": "HTML",
            }
            r = requests.post(url, data=payload, timeout=20)
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": caption,
                "parse_mode": "HTML",
            }
            r = requests.post(url, data=payload, timeout=20)

        print("[TG] status:", r.status_code)
    except Exception as e:
        print("[TG] Errore invio:", e)


async def accept_cookies_if_any(page):
    """Prova a cliccare accetta cookie se presente."""
    selectors = [
        "#sp-cc-accept",
        "input#sp-cc-accept",
        "button#sp-cc-accept",
    ]
    for sel in selectors:
        try:
            btn = await page.query_selector(sel)
            if btn:
                await btn.click()
                print("[COOKIE] Accettato tramite", sel)
                await page.wait_for_timeout(1000)
                return
        except Exception:
            continue
    print("[COOKIE] Nessun banner cookie trovato (o già accettato).")


async def get_product_details(page, asin: str) -> dict | None:
    """Apre la pagina prodotto e ritorna dettagli (titolo, prezzi, sconto, rating, ecc.)."""
    url = f"https://www.amazon.it/dp/{asin}"
    print(f"[DETAIL] Apro pagina {url}")
    try:
        await page.goto(url, timeout=60000)
    except PlaywrightTimeoutError:
        print("[DETAIL] Timeout su", url)
        return None
    except Exception as e:
        print("[DETAIL] Errore goto:", e)
        return None

    # Titolo completo (solo span visibile, non l'input hidden)
    title = None
    try:
        el = page.locator("span#productTitle").first
        title_text = await el.inner_text(timeout=5000)
        if title_text:
            title = " ".join(title_text.split()).strip()
    except Exception:
        pass

    if not title or len(title) < 3:
        try:
            t = await page.title()
            if t:
                title = t.strip()
        except Exception:
            pass

    if not title:
        title = asin

    # Prezzo attuale
    price_now = None
    price_selectors = [
        "#corePrice_desktop span.a-price.aok-align-center span.a-offscreen",
        "#corePrice_desktop span.a-price span.a-offscreen",
        "#corePrice_desktop .a-offscreen",
        "#priceblock_dealprice",
        "#priceblock_saleprice",
        "#priceblock_ourprice",
        ".a-price .a-offscreen",
    ]
    for sel in price_selectors:
        try:
            txt = await page.text_content(sel)
            if not txt:
                continue
            clean = txt.replace("€", "").replace("\xa0", "").strip()
            clean = clean.replace(".", "").replace(",", ".")
            price_now = float(clean)
            break
        except Exception:
            continue

    # Prezzo consigliato (evitiamo €/L, €/kg, ecc.)
    price_old = None
    bad_terms = [
        "/l", "/ l", "/litro", "/ litro",
        "/kg", "/ kg",
        "/g", "/ g",
        "/ml", "/ ml",
        "/100 g", "/ 100 g",
        "/100 ml", "/ 100 ml",
        "al litro", "al kg", "per 100", "al metro",
    ]
    try:
        candidates = []
        nodes = await page.query_selector_all(".a-text-price .a-offscreen")
        for node in nodes:
            txt = await node.text_content()
            if not txt:
                continue
            low = txt.lower()
            if any(term in low for term in bad_terms):
                # scartiamo prezzi al litro/kg ecc.
                continue
            c = txt.replace("€", "").replace("\xa0", "").strip()
            c = c.replace(".", "").replace(",", ".")
            try:
                val = float(c)
                candidates.append(val)
            except Exception:
                continue

        if candidates:
            # in genere il prezzo consigliato è quello pieno più alto
            price_old = max(candidates)
    except Exception:
        pass

    # Calcolo sconto
    discount = None
    if price_now and price_old and price_old > 0:
        discount = round((price_old - price_now) / price_old * 100)

    # Rating (es. "4,6 su 5")
    rating_value = None
    try:
        txt = await page.text_content("span[data-hook='rating-out-of-text']")
        if txt:
            txt = txt.strip()
            txt = txt.replace("stelle", "").strip()
            rating_value = txt  # es: "4,6 su 5"
    except Exception:
        try:
            txt = await page.text_content("span.a-icon-alt")
            if txt and "su 5" in txt:
                txt = txt.replace("stelle", "").strip()
                rating_value = txt
        except Exception:
            pass

    # Numero recensioni
    reviews_count = None
    try:
        txt = await page.text_content("#acrCustomerReviewText")
        if txt:
            m = re.search(r"([\d\.\,]+)", txt)
            if m:
                reviews_count = m.group(1)
    except Exception:
        pass

    # Amazon's Choice / Scelta Amazon
    is_choice = False
    try:
        choice_selectors = [
            "#acBadge_feature_div",
            "img[alt*=\"Amazon's Choice\"]",
            "img[alt*=\"Scelta Amazon\"]",
            "span:has-text(\"Scelta Amazon\")",
        ]
        for cs in choice_selectors:
            try:
                node = await page.query_selector(cs)
                if node:
                    is_choice = True
                    break
            except Exception:
                continue
    except Exception:
        pass

    # Immagine principale
    image_url = None
    try:
        image_url = await page.get_attribute("#landingImage", "src")
    except Exception:
        try:
            node = await page.query_selector("img[data-old-hires]")
            if node:
                image_url = await node.get_attribute("data-old-hires")
        except Exception:
            pass

    if not price_now or not price_old or discount is None:
        print(f"[DETAIL] ASIN {asin} senza prezzi completi, skip.")
        return None

    return {
        "asin": asin,
        "title": title,
        "price_now": price_now,
        "price_old": price_old,
        "discount": discount,
        "rating": rating_value,
        "reviews": reviews_count,
        "is_choice": is_choice,
        "image": image_url,
    }


async def scrape_all_products() -> list[dict]:
    """Scrape da tutte le SEARCH_URLS e ritorna prodotti unici con sconto >= MIN_DISCOUNT."""
    products_by_asin: dict[str, dict] = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = await browser.new_page()

        for url in SEARCH_URLS:
            print("[SCRAPE] Carico:", url)
            try:
                await page.goto(url, timeout=60000)
            except PlaywrightTimeoutError:
                print("[SCRAPE] Timeout su", url)
                continue
            except Exception as e:
                print("[SCRAPE] Errore goto:", e)
                continue

            await accept_cookies_if_any(page)

            try:
                await page.wait_for_selector("div.s-main-slot div[data-asin]", timeout=8000)
            except Exception:
                pass

            cards = await page.query_selector_all("div.s-main-slot div[data-asin]")
            # filtra card senza asin
            cards = [c for c in cards if (asyncio.run(c.get_attribute("data-asin")) if False else True)]
            print("[SCRAPE] Carte totali (potenzialmente):", len(cards))

            # più semplice: rileggo asins con un secondo pass (sincrono)
            valid_cards = []
            for c in cards:
                asin = await c.get_attribute("data-asin")
                if asin:
                    valid_cards.append((asin, c))
            print("[SCRAPE] Carte valide (con ASIN):", len(valid_cards))

            # limitiamo per non farlo impazzire
            valid_cards = valid_cards[:40]
            total_cards = len(valid_cards)
            print("[SCRAPE] Analizzo solo le prime", total_cards, "card")

            for idx, (asin, _card) in enumerate(valid_cards, start=1):
                if asin in products_by_asin:
                    continue

                print(f"[CHECK] Card {idx}/{total_cards} ASIN {asin}")
                details = await get_product_details(page, asin)
                if not details:
                    continue

                if details["discount"] is None or details["discount"] < MIN_DISCOUNT:
                    print(f"[SKIP] ASIN {asin} → sconto insufficiente ({details['discount']})")
                    continue

                products_by_asin[asin] = details
                print(f"[OK] ASIN {asin} registrato con sconto {details['discount']}%")

        await browser.close()

    products = list(products_by_asin.values())
    print(f"[SCRAPE] Totale prodotti validi raccolti: {len(products)}")
    return products


async def main():
    published = load_published()
    now = time.time()
    cutoff = now - 24 * 3600  # 24 ore fa

    all_products = await scrape_all_products()
    if not all_products:
        print("[MAIN] Nessun prodotto trovato.")
        return

    # ordina per sconto decrescente
    all_products.sort(key=lambda p: p.get("discount", 0), reverse=True)

    to_publish: list[dict] = []
    for p in all_products:
        asin = p["asin"]
        last_ts = published.get(asin)

        if last_ts and last_ts > cutoff:
            print(f"[SKIP 24h] ASIN {asin} già pubblicato di recente.")
            continue

        to_publish.append(p)
        if len(to_publish) >= MAX_PRODUCTS:
            break

    if not to_publish:
        print("[MAIN] Nessun nuovo prodotto da pubblicare (tutti già inviati nelle ultime 24h).")
        return

    for p in to_publish:
        asin = p["asin"]

        lines = []

        # Titolo
        lines.append(f"🔥 <b>{h(p['title'])}</b>")
        lines.append("")  # riga vuota tra titolo e prezzi

        # Prezzi e sconto
        lines.append(f"💶 Prezzo: <b>{h(fmt_eur(p['price_now']))}</b>")
        lines.append(f"❌ Prezzo consigliato: <s>{h(fmt_eur(p['price_old']))}</s>")
        lines.append(f"🎯 Sconto: <b>{p['discount']}%</b>")
        lines.append("")

        # Rating (solo se presente)
        if p.get("rating"):
            if p.get("reviews"):
                rating_line = f"⭐ {h(p['rating'])} ({h(p['reviews'])} recensioni)"
            else:
                rating_line = f"⭐ {h(p['rating'])}"
            lines.append(rating_line)

        # Scelta Amazon subito sotto la valutazione (se c'è)
        if p.get("is_choice"):
            lines.append("🏅 Scelta Amazon")

        if lines and lines[-1] != "":
            lines.append("")

        # Link affiliato
        link = f"https://www.amazon.it/dp/{asin}/?tag={AFFILIATE_TAG}"
        lines.append(f"🔗 <a href=\"{h(link)}\">Apri l'offerta</a>")

        caption = "\n".join(lines)

        print(f"[SEND] Invio ASIN {asin} con sconto {p['discount']}%")
        send_telegram_photo(p.get("image"), caption)

        # aggiorna storico
        published[asin] = now

    save_published(published)
    print("[MAIN] Pubblicazione completata.")


if __name__ == "__main__":
    asyncio.run(main())
