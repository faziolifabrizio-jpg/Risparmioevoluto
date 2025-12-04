import os, time, random, requests
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DEBUG = os.getenv("DEBUG", "0") == "1"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.amazon.it/",
    "Cache-Control": "no-cache",
}

FALLBACK_URLS = [
    "https://www.amazon.it/s?i=electronics&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",
    "https://www.amazon.it/s?i=computers&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",
    "https://www.amazon.it/s?i=kitchen&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",
    "https://www.amazon.it/s?i=fashion&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",
    "https://www.amazon.it/s?i=beauty&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",
    "https://www.amazon.it/s?i=health&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",
    "https://www.amazon.it/s?i=toys&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",
    "https://www.amazon.it/s?i=pets&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",
    "https://www.amazon.it/s?i=automotive&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",
    "https://www.amazon.it/s?i=garden&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",
    "https://www.amazon.it/s?i=appliances&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",
    "https://www.amazon.it/s?i=lighting&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",
    "https://www.amazon.it/s?i=movies&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",
    "https://www.amazon.it/s?i=stripbooks&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",
    "https://www.amazon.it/s?i=videogames&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",
    "https://www.amazon.it/s?i=musical-instruments&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",
    "https://www.amazon.it/s?i=sporting&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",
    "https://www.amazon.it/s?i=office-products&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",
    "https://www.amazon.it/s?i=grocery&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",
    "https://www.amazon.it/s?i=baby&rh=p_n_deal_type%3A26980358031&dc&sort=featured-rank",
]

def send_telegram_text(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, data=data, timeout=20)
        print("Telegram text response:", r.status_code, r.text, flush=True)
    except Exception as e:
        print("Errore Telegram sendMessage:", e, flush=True)

def send_telegram_photo(photo_url: str, caption: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    data = {"chat_id": TELEGRAM_CHAT_ID, "photo": photo_url, "caption": caption, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, data=data, timeout=20)
        print("Telegram photo response:", r.status_code, r.text, flush=True)
    except Exception as e:
        print("Errore Telegram sendPhoto:", e, flush=True)

def is_captcha(html: str) -> bool:
    t = html.lower()
    return ("robot check" in t) or ("inserisci i caratteri" in t) or ("captcha" in t)

def fetch_html(url: str) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        print(f"[fetch_html] {url} status:", r.status_code, flush=True)
        if DEBUG:
            print("=== HTML DEBUG START ==="); print(r.text[:1500]); print("=== HTML DEBUG END ===")
        if r.status_code == 200 and not is_captcha(r.text):
            return r.text
    except Exception as e:
        print("Errore fetch_html:", e, flush=True)
    return ""

def parse_cards(html: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("div.s-card-container, div.s-result-item[data-component-type='s-search-result']")
    print("Cards trovati:", len(cards), flush=True)
    results = []
    for card in cards[:10]:
        title_node = card.select_one("h2 a span") or card.select_one("a.a-link-normal[aria-label]")
        if title_node and title_node.parent and title_node.parent.has_attr("aria-label"):
            title = title_node.parent.get("aria-label")
        elif title_node:
            title = title_node.get_text(strip=True)
        else:
            title = "N/A"

        img_node = card.select_one("img.s-image") or card.select_one("img")
        img = None
        if img_node:
            for attr in ["src", "data-src", "data-image-src"]:
                if img_node.has_attr(attr) and img_node.get(attr):
                    img = img_node.get(attr); break

        price_node = card.select_one("span.a-price span.a-offscreen") or card.select_one("span.a-offscreen")
        price = price_node.get_text(strip=True) if price_node else "N/A"

        old_price_node = card.select_one("span.a-text-price span.a-offscreen")
        old_price = old_price_node.get_text(strip=True) if old_price_node else "N/A"

        reviews_node = card.select_one("span.a-size-base") or card.select_one("span.a-size-small")
        reviews = reviews_node.get_text(strip=True) if reviews_node else "N/A"

        if title == "N/A" and not img and price == "N/A":
            continue

        results.append({"title": title, "img": img, "price": price, "old_price": old_price, "reviews": reviews})
    return results

def extract() -> list:
    print("INIZIO FALLBACK SEARCH", flush=True)
    all_results = []
    for url in FALLBACK_URLS:
        time.sleep(random.uniform(1.2, 2.5))
        html = fetch_html(url)
        if not html:
            print("Fallback: nessun HTML, continuo", flush=True); continue
        res = parse_cards(html)
        if res:
            print(f"Risultati ottenuti da: {url}", flush=True)
            all_results = res
            break
    print("Totale risultati estratti:", len(all_results), flush=True)
    return all_results[:8]

def main():
    print("Entrato in main(), DEBUG mode attivo:", DEBUG, flush=True)
    products = extract()
    print("Prodotti estratti:", len(products), flush=True)

    if not products:
        send_telegram_text("⚠️ Nessun prodotto trovato. Amazon potrebbe servire contenuti via JS o CAPTCHA. Riprovo più tardi.")
        return

    for p in products:
        if not p.get("img"):
            continue
        caption = (
            "🔥 *OFFERTA AMAZON*\n\n"
            f"📌 *{p.get('title','N/A')}*\n\n"
            f"💶 Prezzo: {p.get('price','N/A')}\n"
            f"❌ Prezzo consigliato: {p.get('old_price','N/A')}\n"
            f"⭐ Recensioni: {p.get('reviews','N/A')}\n"
        )
        send_telegram_photo(p["img"], caption)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Errore in main:", e, flush=True)
