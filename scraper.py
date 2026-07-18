"""Scrape coach and choreographer data for active ISU figure skaters.

Downloads every skater bio linked from the ISU results site's per-discipline
lists, keeps skaters active in the current season, and writes data.csv.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "http://www.isuresults.com/bios"
CATEGORIES = ["pairs", "men", "women", "dance"]
OUTPUT_FILE = Path(__file__).parent / "data.csv"

# The official ISU season starts July 1, but a bio only mentions the new
# season once the skater has competed in it (Junior Grand Prix from
# ~mid-August, Challengers in September, Grand Prix through late November).
# We flip on Nov 1, when most of the active field has competed.
SEASON_FLIP = (11, 1)  # (month, day)

MAX_WORKERS = 8
TIMEOUT = 30
MIN_KEEP_RATIO = 0.6  # refuse to overwrite data.csv if we'd lose >40% of rows

_local = threading.local()


def active_season(today: date | None = None) -> str:
    """Season string to filter bios on, e.g. "26/27"."""
    today = today or date.today()
    start_year = today.year if (today.month, today.day) >= SEASON_FLIP else today.year - 1
    return f"{start_year % 100:02d}/{(start_year + 1) % 100:02d}"


def _session() -> requests.Session:
    """One keep-alive session per worker thread, with retries on 5xx."""
    if not hasattr(_local, "session"):
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            raise_on_status=False,
        )
        session = requests.Session()
        session.mount("http://", HTTPAdapter(max_retries=retry))
        _local.session = session
    return _local.session


def fetch(url: str) -> BeautifulSoup:
    return BeautifulSoup(_session().get(url, timeout=TIMEOUT).content, "html.parser")


def bio_links(category: str) -> list[tuple[str, str]]:
    """(skater name, bio url) for every bio linked from a discipline's list page."""
    soup = fetch(f"{BASE_URL}/fsbios{category}.htm")
    links = [
        (a.text, a["href"])
        for a in soup.find_all("a", href=True)
        if "fsbios" not in a["href"]  # skip nav links between discipline lists
    ]
    assert len(links) > 50, f"suspiciously few skater links for {category}: {len(links)}"
    return links


def scrape_bio(name: str, url: str, season: str) -> dict | None:
    """Extract coach/choreographer from one bio, or None if inactive/unparseable."""
    soup = fetch(url)
    if not soup.find(class_="flx4"):
        return None  # old bio format without coach data
    if not any(season in td.text for td in soup.find_all("td")):
        return None  # skater not active this season

    labels = soup.find_all(class_="flx2")

    def value(label: str) -> str | None:
        cell = next((c for c in labels if label in c.text), None)
        return cell.find_next_sibling("td").text if cell else None

    return {"skater": name, "coach": value("Coach"), "choreographer": value("Choreographer")}


def build_dataframe(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)

    # Title-case all string fields
    df = df.map(lambda x: x.title() if isinstance(x, str) else x)

    # Only keep rows with either coach or choreographer
    df = df[df["coach"].notna() | df["choreographer"].notna()]

    df.columns = df.columns.str.capitalize()
    df = df.sort_values(by=["Category", "Skater"])
    return df[["Category", "Skater", "Coach", "Choreographer"]]


def main() -> None:
    season = active_season()
    print(f"Filtering on season {season}")

    rows = []
    for category in CATEGORIES:
        print(category)
        links = bio_links(category)
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            results = pool.map(lambda link: scrape_bio(*link, season), links)
        rows += [row | {"category": category} for row in results if row]

    assert rows, "no active skaters scraped"
    df = build_dataframe(rows)

    # Shrink guard: a site outage or layout change must not gut the dataset.
    if OUTPUT_FILE.exists():
        old_n = len(pd.read_csv(OUTPUT_FILE))
        assert len(df) > MIN_KEEP_RATIO * old_n, (
            f"suspicious shrink: scraped {len(df)} rows vs {old_n} in {OUTPUT_FILE.name}"
        )

    df.to_csv(OUTPUT_FILE, index=False)
    print(f"Wrote {len(df)} skaters to {OUTPUT_FILE.name}")


if __name__ == "__main__":
    main()
