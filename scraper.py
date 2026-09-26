"""Scrape coach and choreographer data for active ISU figure skaters.

Downloads every skater bio linked from the ISU results site's per-discipline
lists, keeps skaters who competed recently, and writes data.csv.
"""

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "http://www.isuresults.com/bios"
CATEGORIES = ["pairs", "men", "women", "dance"]
OUTPUT_FILE = Path(__file__).parent / "data.csv"

SEASON_START = (7, 1)  # (month, day): the official ISU season start
SEASON_BEST_URL = "http://www.isuresults.com/isujsstat/sb{start}-{end:02d}/sbts{discipline}to.htm"
SEASON_BEST_DISCIPLINE = {"men": "m", "women": "w", "pairs": "p", "dance": "d"}

MAX_WORKERS = 8
TIMEOUT = 30
FETCH_ATTEMPTS = 3
TRANSIENT_ERRORS = (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError)
SEASON_LABEL = re.compile(r"\d\d/\d\d")
EVENT_YEAR = re.compile(r"\b(20\d\d)\b")
MIN_KEEP_RATIO = 0.6  # refuse to overwrite data.csv if we'd lose >40% of rows

_local = threading.local()


@dataclass(frozen=True)
class ActiveRule:
    """Who counts as active. No single ISU page says so, and each one misses skaters:

    - a bio's championship table (Olympics, Worlds, Europeans, Four Continents, World
      Juniors, nationals) has exact seasons, but many juniors never appear in it;
    - the season's best lists add Grand Prix, Junior Grand Prix and Challenger events;
    - a bio's Competition Results page lists every event, smaller internationals
      included, but only by name, e.g. "Tallinn Trophy 2025", with no date or season.

    A skater counts if any of the three shows them competing recently. The event-name
    check is the loose one: an event named with last year counts all of this year, so
    a skater can stay in the data for up to a year after they stop.
    """

    seasons: tuple[str, str]  # last season and the current one, e.g. ("25/26", "26/27")
    season_best: frozenset[str]  # bio URLs on those seasons' season's best lists
    min_event_year: int  # an event named with this year or later counts


def _season(start_year: int) -> str:
    return f"{start_year % 100:02d}/{(start_year + 1) % 100:02d}"


def season_start_year(today: date) -> int:
    return today.year if (today.month, today.day) >= SEASON_START else today.year - 1


def active_seasons(today: date) -> tuple[str, str]:
    """Last season and the current one, e.g. ("25/26", "26/27")."""
    start_year = season_start_year(today)
    return _season(start_year - 1), _season(start_year)


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
    """Download and parse a page, retrying drops the session's retries can't see.

    urllib3's Retry only covers failures before the body starts arriving. The ISU
    server sometimes cuts the connection mid-body, which surfaces here instead.
    """
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            return BeautifulSoup(_session().get(url, timeout=TIMEOUT).content, "html.parser")
        except TRANSIENT_ERRORS:
            if attempt == FETCH_ATTEMPTS:
                raise
            time.sleep(2 * attempt)
    raise AssertionError("unreachable")


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


def season_best_bios(category: str, start_year: int) -> dict[str, str]:
    """{bio url: skater name} for one season's best list: every skater, juniors included,
    with a score at an ISU-judged event that season. Empty if the list isn't up yet (early July)."""
    url = SEASON_BEST_URL.format(
        start=start_year, end=(start_year + 1) % 100, discipline=SEASON_BEST_DISCIPLINE[category]
    )
    return {a["href"]: a.text for a in fetch(url).find_all("a", href=True) if f"{BASE_URL}/isufs" in a["href"]}


def season_best_lists(today: date) -> dict[str, dict[str, str]]:
    """Per discipline, {bio url: skater name} for everyone on last season's and this season's lists."""
    start_year = season_start_year(today)
    lists = {}
    for category in CATEGORIES:
        lists[category] = {}
        for year in (start_year - 1, start_year):
            bios = season_best_bios(category, year)
            print(f"season's best {_season(year)} {category}: {len(bios)} skaters")
            lists[category] |= bios
    return lists


def active_rule(today: date, season_best: dict[str, dict[str, str]]) -> ActiveRule:
    bios = frozenset(url for category_bios in season_best.values() for url in category_bios)
    return ActiveRule(active_seasons(today), bios, today.year - 1)


def skater_links(category: str, season_best: dict[str, str]) -> list[tuple[str, str]]:
    """(skater name, bio url) for everyone to look at: the discipline's list page, plus anyone
    on the season's best lists it's missing. The ISU stopped updating the list pages (ice dance
    in July 2024, the others in April 2026), so newer skaters are only reachable this way."""
    links = {url: name for name, url in bio_links(category)}
    added = {url: name for url, name in season_best.items() if url not in links}
    print(f"{category}: {len(links)} on the list page, {len(added)} more from the season's best lists")
    return [(name, url) for url, name in (links | added).items()]


def seasons_with_results(soup: BeautifulSoup) -> set[str]:
    """Seasons in which the bio's championship table has at least one result.

    The table is a heading row of season labels (after some blank cells), then one row
    per championship: a label cell and one cell per season, blank if not entered. The
    heading row alone says nothing: it shows eight seasons whether or not they were skated.
    """

    def season_labels(tr) -> list[str]:
        return [td.text.strip() for td in tr.find_all("td") if SEASON_LABEL.fullmatch(td.text.strip())]

    heading = next((tr for tr in soup.find_all("tr") if season_labels(tr)), None)
    if heading is None:
        return set()
    seasons = season_labels(heading)
    active = set()
    for row in heading.find_next_siblings("tr"):
        cells = row.find_all("td")
        if len(cells) != len(seasons) + 1:
            break  # past the last championship row
        active |= {season for season, cell in zip(seasons, cells[1:], strict=True) if cell.get_text(strip=True)}
    return active


def latest_event_year(bio_url: str) -> int | None:
    """Newest year named in the skater's Competition Results page, e.g. 2026 for
    "ISU CS Kinoshita Group Cup 2026". None if no event names a year."""
    soup = fetch(bio_url.replace("/isufs", "/isufs_cr_"))
    years = [int(y) for td in soup.find_all("td", class_="flx5") for y in EVENT_YEAR.findall(td.get_text())]
    return max(years, default=None)


def is_active(url: str, soup: BeautifulSoup, rule: ActiveRule) -> bool:
    """Cheapest check first: only a skater the first two miss costs a second download."""
    if url in rule.season_best or seasons_with_results(soup) & set(rule.seasons):
        return True
    year = latest_event_year(url)
    return year is not None and year >= rule.min_event_year


def scrape_bio(name: str, url: str, rule: ActiveRule) -> dict | None:
    """Extract coach/choreographer from one bio, or None if inactive/unparseable."""
    try:
        soup = fetch(url)
        if not soup.find(class_="flx4"):
            return None  # old bio format without coach data
        if not is_active(url, soup, rule):
            return None
    except TRANSIENT_ERRORS as e:
        # One unreachable page shouldn't sink the run; the skater is back next week,
        # and the shrink guard in main() still catches a site-wide outage.
        print(f"skipping {name}: {type(e).__name__}")
        return None

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


def main(today: date | None = None) -> None:
    today = today or datetime.now(UTC).date()
    season_best = season_best_lists(today)
    rule = active_rule(today, season_best)
    print(
        f"Keeping skaters with a championship result or a season's best in {' or '.join(rule.seasons)}, "
        f"or any event named {rule.min_event_year} or later"
    )

    rows = []
    for category in CATEGORIES:
        links = skater_links(category, season_best[category])
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            results = pool.map(lambda link: scrape_bio(*link, rule), links)
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
