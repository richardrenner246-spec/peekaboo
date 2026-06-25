"""
Airbnb Trips Scraper
Öffnet Chromium, navigiert zu airbnb.com/trips,
wartet auf manuellen Login, speichert Buchungen als CSV.
"""

import csv
import time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright


LOGIN_WAIT_SECONDS = 30
OUTPUT_FILE = Path("airbnb_buchungen.csv")


def wait_for_login(page, seconds: int):
    print(f"\n>>> Bitte jetzt in Airbnb einloggen. Du hast {seconds} Sekunden. <<<\n")
    for remaining in range(seconds, 0, -5):
        print(f"  Noch {remaining} Sekunden...")
        time.sleep(5)
    print("  Zeit abgelaufen – fahre fort.\n")


def extract_trips(page) -> list[dict]:
    """Liest alle Buchungskarten auf der /trips-Seite aus."""
    page.wait_for_load_state("networkidle", timeout=15_000)

    trips = []

    # Airbnb rendert Trips als Cards; Selektoren können sich ändern.
    # Wir versuchen mehrere bekannte Strukturen.
    cards = page.query_selector_all('[data-testid="trips-card"], [data-testid="trip-card"], article')

    if not cards:
        # Fallback: alle sichtbaren Texte pro "section" sammeln
        print("Keine strukturierten Karten gefunden – versuche Fallback-Extraktion.")
        cards = page.query_selector_all("section, div[class*='trip'], div[class*='booking']")

    print(f"  {len(cards)} Karten gefunden.\n")

    for card in cards:
        text = card.inner_text().strip()
        if not text:
            continue

        # Link zur Buchungsdetailseite
        link_el = card.query_selector("a")
        link = link_el.get_attribute("href") if link_el else ""
        if link and link.startswith("/"):
            link = "https://www.airbnb.com" + link

        # Bild-Alt-Text als Unterkunftsname (oft aussagekräftiger)
        img = card.query_selector("img")
        title_from_img = img.get_attribute("alt").strip() if img else ""

        # Versuche dedizierte Label-Elemente
        title_el = card.query_selector(
            '[data-testid="trip-title"], h2, h3, [class*="title"], [class*="name"]'
        )
        title = (title_el.inner_text().strip() if title_el else "") or title_from_img

        date_el = card.query_selector(
            '[data-testid="trip-dates"], [class*="date"], time'
        )
        dates = date_el.inner_text().strip() if date_el else ""

        status_el = card.query_selector(
            '[data-testid="trip-status"], [class*="status"], [class*="state"]'
        )
        status = status_el.inner_text().strip() if status_el else ""

        trips.append({
            "Titel": title,
            "Datum": dates,
            "Status": status,
            "Link": link,
            "Volltext": " | ".join(text.splitlines()[:6]),  # erste 6 Zeilen
        })

    return trips


def save_csv(trips: list[dict], path: Path):
    if not trips:
        print("Keine Buchungen gefunden – CSV wird nicht erstellt.")
        return

    fieldnames = ["Titel", "Datum", "Status", "Link", "Volltext"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(trips)

    print(f"CSV gespeichert: {path.resolve()}  ({len(trips)} Einträge)")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/opt/pw-browsers/chromium",
            headless=False,          # sichtbares Fenster
            slow_mo=50,
            args=["--start-maximized"],
        )

        context = browser.new_context(
            viewport=None,           # maximiertes Fenster übernehmen
            locale="de-DE",
            timezone_id="Europe/Berlin",
        )
        page = context.new_page()

        print("Öffne airbnb.com/trips ...")
        page.goto("https://www.airbnb.com/trips", wait_until="domcontentloaded")

        # Warte auf Login
        wait_for_login(page, LOGIN_WAIT_SECONDS)

        # Nach Login ggf. nochmal zur Trips-Seite navigieren
        if "trips" not in page.url:
            print("Navigiere erneut zu /trips ...")
            page.goto("https://www.airbnb.com/trips", wait_until="domcontentloaded")

        # Kurz warten bis Inhalte geladen sind
        page.wait_for_timeout(3000)

        print("Extrahiere Buchungen ...")
        trips = extract_trips(page)

        for i, t in enumerate(trips, 1):
            print(f"  [{i}] {t['Titel'] or '(kein Titel)'} | {t['Datum']} | {t['Status']}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = OUTPUT_FILE.with_stem(f"airbnb_buchungen_{timestamp}")
        save_csv(trips, output)

        input("\nFertig. Drücke Enter um den Browser zu schließen.")
        browser.close()


if __name__ == "__main__":
    main()
