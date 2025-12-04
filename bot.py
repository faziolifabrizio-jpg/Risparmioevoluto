import os
import time
import random
import threading
import requests
from http.server import SimpleHTTPRequestHandler
import socketserver
from bs4 import BeautifulSoup

# ================================
# CONFIGURAZIONE BASE
# ================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
AFFILIATE_TAG = "risparmioevol-21"
DEBUG = os.getenv("DEBUG", "0") == "1"

# Alcuni user-agent diversi per sembrare più "umani"
HEADERS_LIST = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.amazon.it/",
        "Cache-Control": "no-cache",
    },
    {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.amazon.it/",
        "Cache-Control": "no-cache",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.amazon.it/",
        "Cache-Control": "no-cache",
    },
]

# URL PIÙ GENERALI DI OFFERTE (meno categorie, meno rischio blocco)
FALLBACK_URLS = [
    # Offerte del giorno / goldbox
    "https://www.amazon.it/gp/goldbox",
    # Altra pagina offerte
    "https://www.amazon.it/deals?ref_=nav_cs_gb",
    # Fallback aggiuntivo
    "https://www.amazon.it/gp/deals",
]


# ================================
# SERVER WEB "FINT0" PER RENDER
# ================================
def fake_webserver():
    """
    Piccolo server HTTP per soddisfare Render (servizio di tipo web).
    Non influisce sulla logica del bot.
    """
    port = int(os.getenv("PORT", "10000"))
    handler = SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"[fake_webserver] In ascolto sulla porta {port}", flush=True)
        httpd.serve_forever()


# Avvio il webserver finto in background
threading.Thread(target=fake_webserver, daemon=True).start()


# ================================
# FUNZIONI TELEGRAM
# ================================
def send_telegram_text(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[send_telegram_text] TOKEN o CHAT_ID mancanti", flush=True)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, data=data, timeout=15)
        print(f"[Telegram text] {r.status_code}", flush=True)
    except Exception as e:
        print(f"[Telegram text ERROR] {e}", flush=True)


def send_telegram_photo(photo_url: str, caption: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[send_telegram_photo] TOKEN o CHAT_ID mancanti", flush=True)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    data = {"chat_id": TELEGRAM_CHAT_ID, "photo": photo_url, "caption": caption, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, data=data, timeout=20)
        print(f"[Telegram photo] {r.status_code}", flush=True)
    except Exception as e:
        print(f"[Telegram photo ERROR] {e}", flush=True)


def notify_error(msg: str):
    print(f"[ERRORE] {msg}", flush=True)
    try:
        send_telegram_text(f"⚠️ *Errore bot Amazon:*\n{msg}")
    except Exception:
        pass


# ================================
# PARSING AMAZON
# ================================
def is_captcha(html: str) -> bool:
    t = html.lower()
    return (
        "captcha" in t
        or "robot check" in t
        or "inserisci i caratteri" in t
        or "enter the characters" in t
    )


def fetch_html(url: str) -> str | None:
    headers = random.choice(HEADERS_LIST)
    print(f"[fetch_html] GET {url}", flush=True)
    try:
        # delay più "umano"
        time.sleep(random.uniform(2.5, 4.5))
        r = requests.get(url, headers=headers, timeout=25)
        print(f"[fetch_html] Status {r.status_code}", flush=True)
        if r.status_code != 200:
            notify_error(f"Risposta HTTP non 200 da Amazon: {r.status_code}")
            return None
        if is_captcha(r.text):
            notify_error("Amazon ha restituito una pagina con CAPTCHA / robot check.")
            return None
        if DEBUG:
            fname = f"debug_{int(time.time())}.html"
            with open(fname, "w", encoding="utf-8") as f:
                f.write(r.text)
        return r.text
    except Exception as e:
        notify_error(f"Errore richiamando Amazon: {e}")
        return None


def parse_cards(html: str) -> list[dict]:
    # uso lxml se presente per parsing più robusto
    soup = BeautifulSoup(html, "lxml")
    # molti layout usano ancora questi container
    cards = soup.select("div.s-card-container, div.s-result-item[data-component-type='s-search-result']")
    print(f"[parse_cards] Carte trovate: {len(cards)}", flush=True)

    results: list[dict] = []

    for card in cards[:20]:
        # Titolo
        title_node = card.select_one("h2 a span") or card.select_one("a.a-link-normal[aria-label]")
        if title_node and title_node.parent and title_node.parent.has_attr("aria-label"):
            title = title_node.parent.get("aria-label")
        elif title_node:
            title = title_node.get_text(strip=True)
        else:
            title = "N/A"

        # Immagine
        img_node = card.select_one("img.s-image") or card.select_one("img")
        img = None
        if img_node:
            for attr in ("src", "data-src", "data-image-src"):
                if img_node.has_attr(attr) and img_node.get(attr):
                    img = img_node.get(attr)
                    break

        # Prezzo
        price_node = card.select_one("span.a-price span.a-offscreen") or card.select_one("span.a-offscreen")
        price = price_node.get_text(strip=True) if price_node else "N/A"

        # Vecchio prezzo
        old_price_node = card.select_one("span.a-text-price span.a-offscreen")
        old_price = old_price_node.get_text(strip=True) if old_price_node else "N/A"

        # Link
        link_node = card.select_one("h2 a")
        link = None
        if link_node and link_node.get("href"):
            href = link_node["href"]
            if href.startswith("/"):
                href = "https://www.amazon.it" + href

            # applica tag affiliato se non presente
            if "tag=" not in href:
                href = href + ("&tag=" + AFFILIATE_TAG if "?" in href else "?tag=" + AFFILIATE_TAG)

            link = href

        # filtro card "vuote"
        if not img or not link or title == "N/A":
            continue

        results.append(
            {
                "title": title,
                "img": img,
                "price": price,
                "old_price": old_price,
                "link": link,
            }
        )

    print(f"[parse_cards] Prodotti validi: {len(results)}", flush=True)
    return results


def extract_products() -> list[dict]:
    """
    Prova alcune pagine generali di offerte fino a trovare qualcosa.
    """
    all_products: list[dict] = []
    for url in FALLBACK_URLS:
        html = fetch_html(url)
        if not html:
            continue
        products = parse_cards(html)
        if products:
            all_products.extend(products)
        if len(all_products) >= 6:
            break
    return all_products[:6]


# ================================
# ROUTINE PRINCIPALE
# ================================
def main_routine():
    print("[main_routine] Avvio ricerca offerte Amazon…", flush=True)
    send_telegram_text("🔍 Sto cercando le offerte Amazon, un attimo...")

    products = extract_products()
    if not products:
        notify_error("Nessun prodotto estratto. Possibile CAPTCHA o layout Amazon cambiato.")
        send_telegram_text("❌ Nessuna offerta trovata. Amazon potrebbe aver mostrato CAPTCHA o contenuti dinamici.")
        return

    for p in products:
        caption = (
            "🔥 *OFFERTA AMAZON*\n\n"
            f"📌 *{p['title']}*\n\n"
            f"💶 Prezzo: *{p['price']}*\n"
            f"💸 Vecchio prezzo: {p['old_price']}\n\n"
            f"🔗 [Apri l'offerta]({p['link']})"
        )
        send_telegram_photo(p["img"], caption)

    send_telegram_text("✅ Ho appena pubblicato le offerte Amazon sul canale.")


# ================================
# SCHEDULER INTERNO
# ================================
def scheduler_loop():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[scheduler_loop] Manca TELEGRAM_TOKEN o TELEGRAM_CHAT_ID. Il bot non può inviare messaggi.", flush=True)
        return

    send_telegram_text("🤖 Bot avviato correttamente e in attesa (Render FREE). Orari: 09:00 e 21:00.")

    last_run_marker = None  # evita doppi invii nello stesso slot

    while True:
        now = time.localtime()
        current_time = f"{now.tm_hour:02d}:{now.tm_min:02d}"
        current_marker = f"{now.tm_year}-{now.tm_mon}-{now.tm_mday}-{now.tm_hour}"

        if current_time in ("09:00", "21:00") and current_marker != last_run_marker:
            print(f"[scheduler_loop] Esecuzione programmata alle {current_time}", flush=True)
            try:
                main_routine()
            except Exception as e:
                notify_error(f"Eccezione non gestita in main_routine: {e}")
            last_run_marker = current_marker
            time.sleep(70)
        else:
            time.sleep(20)


if __name__ == "__main__":
    print("[__main__] Avvio bot Amazon con scheduler interno…", flush=True)
    scheduler_loop()
