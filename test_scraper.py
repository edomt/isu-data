"""Offline tests for scraper.py: fake pages shaped like the real ISU ones, no network."""

from datetime import date

import pandas as pd
import pytest
import requests
import scraper
from bs4 import BeautifulSoup

LIST_URL = f"{scraper.BASE_URL}/fsbiosmen.htm"


def list_page(n_skaters: int) -> str:
    """A discipline list page: nav links to the other lists, then one link per skater."""
    nav = "".join(f"<a href='{scraper.BASE_URL}/fsbios{c}.htm'>{c}</a>" for c in scraper.CATEGORIES)
    skaters = "".join(
        f"<a href='{scraper.BASE_URL}/isufs{i:08d}.htm'>Skater NUMBER{i}</a><br>" for i in range(n_skaters)
    )
    return f"<html><body>{nav}<table><tr><td>{skaters}</td></tr></table></body></html>"


WINDOW = ["19/20", "20/21", "21/22", "22/23", "23/24", "24/25", "25/26", "26/27"]
CHAMPIONSHIPS = [
    "Olympic Games",
    "World Championship",
    "European Championship",
    "National Championship",
]


def season_table(results: dict[tuple[str, str], str], window: list[str]) -> str:
    """The championship table as the ISU lays it out: a heading row (four blank cells, then
    the season labels), one row per championship (a label, then one cell per season, `&nbsp;`
    when not entered), and a trailing row of blanks. `results` maps (championship, season)
    to what goes in the cell."""
    heading = "<td class='flx11'></td>" * 4 + "".join(f"<td class='flx12'>{s}</td>" for s in window)
    rows = [
        f"<td class='flx13' colspan='4'>{c}</td>"
        + "".join(f"<td class='flx14'>{results.get((c, s), '&nbsp;')}</td>" for s in window)
        for c in CHAMPIONSHIPS
    ]
    trailing = "<td class='flx11'></td>" * (4 + len(window))
    return "".join(f"<tr>{r}</tr>" for r in [heading, *rows, trailing])


def bio_page(
    results: dict[tuple[str, str], str] | None = None,
    window: list[str] = WINDOW,
    coach: str | None = "Veronika Daineko",
    choreographer: str | None = "Nikolai Moroshkin",
    former_coach: str | None = "Alexei Mishin",
) -> str:
    """A new-format bio: name block (flx4), label rows (flx2), then the championship table.
    By default the skater won nationals last season."""
    results = {("National Championship", "25/26"): "1.S"} if results is None else results
    rows = [("Date of birth:", "01.01.2002"), ("Home town:", "Somewhere")]
    rows += [(label, v) for label, v in [("Coach:", coach), ("Choreographer:", choreographer)] if v]
    rows += [("Former Coach:", former_coach)] if former_coach else []
    label_rows = "".join(f"<tr><td class='flx2'>{label}</td><td class='flx5'>{v}</td></tr>" for label, v in rows)
    return (
        "<html><body><table>"
        "<tr><td class='flx4'><div class='flx4'>Skater NAME</div></td></tr>"
        f"{label_rows}"
        f"{season_table(results, window)}"
        "</table></body></html>"
    )


OLD_FORMAT_BIO = "<html><script>var x = 1;</script><body><table><tr><td>25/26</td></tr></table></body></html>"
SEASONS = (
    "25/26",
    "26/27",
)  # what active_seasons() gives between July 2026 and June 2027
TODAY = date(2026, 9, 26)
RULE = scraper.ActiveRule(SEASONS, frozenset(), min_event_year=2025)
BIO_URL = f"{scraper.BASE_URL}/isufs00054617.htm"
CR_URL = f"{scraper.BASE_URL}/isufs_cr_00054617.htm"
# Last competed in 23/24: the ISU still shows headings up to 24/25, but no result after 23/24.
RETIRED = bio_page({("World Championship", "23/24"): "5"}, window=["17/18", "18/19", *WINDOW[:6]])


def cr_page(*events: str) -> str:
    """A Competition Results page: section headings, then one row per event
    (event name, category, place), all names in class flx5."""
    rows = "".join(
        f"<tr><td class='flx4'></td><td class='flx5'>{e}</td><td class='flx5'>Men</td><td class='flx6'>3</td></tr>"
        for e in events
    )
    return f"<html><table><tr><td class='flx2'>Competition Results</td></tr>{rows}</table></html>"


def season_best_page(bio_urls: list[str]) -> str:
    rows = "".join(
        f"<tr><td>{i}</td><td><a href='{u}'>Skater {i}</a></td><td>ISU JGP Riga 2025</td></tr>"
        for i, u in enumerate(bio_urls, 1)
    )
    return f"<html><table><tr><td>ISU Season Best Scores Statistics</td></tr>{rows}</table></html>"


NOT_FOUND = "<html><body><h1>404 - File or directory not found.</h1></body></html>"


def season_best_url(category: str, start_year: int) -> str:
    return scraper.SEASON_BEST_URL.format(
        start=start_year,
        end=(start_year + 1) % 100,
        discipline=scraper.SEASON_BEST_DISCIPLINE[category],
    )


class FakeResponse:
    def __init__(self, html: str):
        self.content = html.encode()


class FakeSession:
    """Serves pages from a dict; a URL listed in `drops` raises mid-body that many times first."""

    def __init__(self, pages: dict[str, str], drops: dict[str, int] | None = None):
        self.pages = pages
        self.drops = dict(drops or {})
        self.calls: list[str] = []

    def get(self, url: str, timeout: int) -> FakeResponse:
        assert timeout == scraper.TIMEOUT, "every request should carry the timeout"
        self.calls.append(url)
        if self.drops.get(url, 0) > 0:
            self.drops[url] -= 1
            raise requests.exceptions.ChunkedEncodingError("Response ended prematurely")
        return FakeResponse(self.pages[url])


@pytest.fixture
def sleeps(monkeypatch) -> list[float]:
    """Record retry pauses instead of waiting for them."""
    waited: list[float] = []
    monkeypatch.setattr(scraper.time, "sleep", waited.append)
    return waited


@pytest.fixture
def site(monkeypatch):
    """Install a FakeSession for every thread; returns a function to set its pages."""

    def install(pages: dict[str, str], drops: dict[str, int] | None = None) -> FakeSession:
        session = FakeSession(pages, drops)
        monkeypatch.setattr(scraper, "_session", lambda: session)
        return session

    return install


# active_seasons


@pytest.mark.parametrize(
    ("today", "want"),
    [
        (date(2026, 6, 30), ("24/25", "25/26")),  # last day of 25/26
        (date(2026, 7, 1), ("25/26", "26/27")),  # official season start
        (date(2026, 11, 1), ("25/26", "26/27")),  # no switch in the autumn any more
        (date(2027, 1, 15), ("25/26", "26/27")),  # new calendar year, same season
        (date(2027, 6, 30), ("25/26", "26/27")),
        (date(2100, 7, 1), ("99/00", "00/01")),  # century wrap
        (date(2000, 3, 1), ("98/99", "99/00")),
        (date(2010, 7, 1), ("09/10", "10/11")),  # leading zeros
    ],
)
def test_active_seasons(today, want):
    assert scraper.active_seasons(today) == want, f"seasons on {today}"


# season's best lists and the rule


def test_season_best_url_matches_the_real_one():
    assert season_best_url("women", 2025) == "http://www.isuresults.com/isujsstat/sb2025-26/sbtswto.htm"
    assert season_best_url("dance", 2099) == "http://www.isuresults.com/isujsstat/sb2099-00/sbtsdto.htm"


def test_season_best_bios(site):
    urls = [f"{scraper.BASE_URL}/isufs{i:08d}.htm" for i in range(3)]
    page = season_best_page(urls).replace(
        "</table>", "<tr><td><a href='http://elsewhere/x.htm'>x</a></td></tr></table>"
    )
    site({season_best_url("pairs", 2025): page})
    want = {u: f"Skater {i}" for i, u in enumerate(urls, 1)}
    assert scraper.season_best_bios("pairs", 2025) == want, "bio links only, with the skater's name"


def test_season_best_bios_before_the_list_is_up(site):
    site({season_best_url("men", 2026): NOT_FOUND})
    assert scraper.season_best_bios("men", 2026) == {}, "early July: no list yet, not an error"


def test_season_best_lists(site, capsys):
    a, b, c = (f"{scraper.BASE_URL}/isufs{i:08d}.htm" for i in range(3))
    pages = {season_best_url(cat, y): NOT_FOUND for cat in scraper.CATEGORIES for y in (2025, 2026)}
    pages[season_best_url("men", 2025)] = season_best_page([a, b])
    pages[season_best_url("men", 2026)] = season_best_page([b, c])  # b skated both seasons
    pages[season_best_url("dance", 2026)] = season_best_page([c])
    site(pages)
    got = scraper.season_best_lists(TODAY)
    assert set(got) == set(scraper.CATEGORIES)
    assert set(got["men"]) == {a, b, c}, "both seasons, each skater once"
    assert set(got["dance"]) == {c}
    assert got["pairs"] == got["women"] == {}
    assert "season's best 25/26 men: 2 skaters" in capsys.readouterr().out


def test_active_rule():
    a, b = (f"{scraper.BASE_URL}/isufs{i:08d}.htm" for i in range(2))
    rule = scraper.active_rule(TODAY, {"men": {a: "A"}, "dance": {b: "B"}, "pairs": {}, "women": {}})
    assert rule == scraper.ActiveRule(SEASONS, frozenset({a, b}), 2025)


def test_active_rule_event_year_follows_the_calendar():
    """The event-name check uses calendar years: in January the window moves on."""
    assert scraper.active_rule(date(2026, 12, 31), {}).min_event_year == 2025
    assert scraper.active_rule(date(2027, 1, 1), {}).min_event_year == 2026


# skater_links


def test_skater_links_adds_skaters_missing_from_the_list_page(site, capsys):
    site({LIST_URL: list_page(60)})
    on_list = f"{scraper.BASE_URL}/isufs00000005.htm"
    newcomer = f"{scraper.BASE_URL}/isufs00123484.htm"
    links = scraper.skater_links("men", {on_list: "Skater NUMBER5", newcomer: "New SKATER"})
    assert len(links) == 61, "the list page's 60, plus the one it's missing"
    assert ("New SKATER", newcomer) in links
    assert [url for _, url in links].count(on_list) == 1, "a skater on both isn't scraped twice"
    assert "men: 60 on the list page, 1 more from the season's best lists" in capsys.readouterr().out


def test_skater_links_keeps_the_list_page_name(site):
    site({LIST_URL: list_page(60)})
    url = f"{scraper.BASE_URL}/isufs00000005.htm"
    assert ("Skater NUMBER5", url) in scraper.skater_links("men", {url: "Other SPELLING"})


def test_skater_links_without_season_best(site):
    site({LIST_URL: list_page(60)})
    assert scraper.skater_links("men", {}) == scraper.bio_links("men")


# latest_event_year


def test_latest_event_year(site):
    site(
        {
            CR_URL: cr_page(
                "ISU CS Kinoshita Group Cup 2026",
                "National Championships 2025",
                "Cup de Nice 2015",
            )
        }
    )
    assert scraper.latest_event_year(BIO_URL) == 2026


@pytest.mark.parametrize(
    ("event", "want"),
    [
        ("2023 Kings Cup International", 2023),  # year first
        ("ISU Junior Grand Prix Final 2019/20", 2019),  # season-style suffix
        ("European Youth Olympic Festival \xa02025", 2025),  # stray non-breaking space
        ("ISU CS Denis Ten Memorial Challenge", None),  # no year at all
        ("Skate 12000 Trophy", None),  # a number that isn't a year
    ],
)
def test_latest_event_year_reads_names(site, event, want):
    site({CR_URL: cr_page(event)})
    assert scraper.latest_event_year(BIO_URL) == want, event


def test_latest_event_year_empty_page(site):
    site({CR_URL: cr_page()})
    assert scraper.latest_event_year(BIO_URL) is None


# seasons_with_results


def results_on(html: str) -> set[str]:
    return scraper.seasons_with_results(BeautifulSoup(html, "html.parser"))


def test_seasons_with_results_combines_championships():
    got = results_on(
        bio_page(
            {
                ("Olympic Games", "25/26"): "<span><a href='x'>6</a>&nbsp;</span>",
                ("World Championship", "21/22"): "10",
                ("National Championship", "19/20"): "7.S, 2.J",
                ("National Championship", "25/26"): "1.S",
            }
        )
    )
    assert got == {"19/20", "21/22", "25/26"}


def test_seasons_with_results_ignores_headings():
    """The bug this replaced: every season in the heading row used to count."""
    assert results_on(bio_page({})) == set(), "eight season headings, no results"


def test_seasons_with_results_ignores_blank_cells():
    assert results_on(bio_page({("Olympic Games", "24/25"): " &nbsp; "})) == set()


def test_seasons_with_results_matches_columns():
    """A result in the last column belongs to the last season, not the one next to it."""
    assert results_on(bio_page({("World Championship", "26/27"): "3"})) == {"26/27"}
    assert results_on(bio_page({("World Championship", "19/20"): "3"})) == {"19/20"}


def test_seasons_with_results_stops_after_the_table():
    later = "<tr><td>Other</td>" + "<td>x</td>" * len(WINDOW) + "</tr>"
    html = bio_page({}).replace("</table>", f"</table><table>{later}</table>")
    assert results_on(html) == set(), "a row-shaped thing in another table isn't a result"


def test_seasons_with_results_without_a_table():
    assert results_on("<html><table><tr><td>Coach:</td><td>X</td></tr></table></html>") == set()
    assert results_on(OLD_FORMAT_BIO) == set(), "a lone season label with nothing under it"


# fetch


def test_fetch_parses_page(site, sleeps):
    site({"u": "<p class='x'>hello</p>"})
    soup = scraper.fetch("u")
    assert isinstance(soup, BeautifulSoup)
    assert soup.find(class_="x").text == "hello"
    assert sleeps == [], "no pause when the first try works"


def test_fetch_retries_a_mid_page_drop(site, sleeps):
    session = site({"u": "<p>ok</p>"}, drops={"u": 2})
    assert scraper.fetch("u").text == "ok"
    assert session.calls == ["u", "u", "u"], "two drops then success = three tries"
    assert sleeps == [2, 4], "pause grows between tries"


def test_fetch_gives_up_after_three_tries(site, sleeps):
    session = site({"u": "<p>ok</p>"}, drops={"u": scraper.FETCH_ATTEMPTS})
    with pytest.raises(requests.exceptions.ChunkedEncodingError):
        scraper.fetch("u")
    assert len(session.calls) == scraper.FETCH_ATTEMPTS
    assert len(sleeps) == scraper.FETCH_ATTEMPTS - 1, "no pause after the last try"


@pytest.mark.parametrize(
    "error",
    [
        requests.ConnectionError,
        requests.Timeout,
        requests.exceptions.ChunkedEncodingError,
    ],
)
def test_fetch_retries_every_transient_error(monkeypatch, sleeps, error):
    attempts = []

    class Flaky:
        def get(self, url, timeout):
            attempts.append(url)
            if len(attempts) == 1:
                raise error("boom")
            return FakeResponse("<p>ok</p>")

    monkeypatch.setattr(scraper, "_session", Flaky)
    assert scraper.fetch("u").text == "ok"
    assert len(attempts) == 2, f"{error.__name__} should be retried"


def test_fetch_does_not_retry_other_errors(monkeypatch, sleeps):
    attempts = []

    class Broken:
        def get(self, url, timeout):
            attempts.append(url)
            raise requests.exceptions.InvalidURL("bad url")

    monkeypatch.setattr(scraper, "_session", Broken)
    with pytest.raises(requests.exceptions.InvalidURL):
        scraper.fetch("u")
    assert len(attempts) == 1, "a bug in our own request isn't worth retrying"


def test_session_is_one_per_thread():
    import threading

    got = []
    threads = [threading.Thread(target=lambda: got.append(scraper._session())) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert got[0] is not got[1], "each worker thread gets its own session"
    assert scraper._session() is scraper._session(), "same thread reuses its session"


# bio_links


def test_bio_links_skips_nav_links(site):
    site({LIST_URL: list_page(60)})
    links = scraper.bio_links("men")
    assert len(links) == 60, "one link per skater, none for the discipline nav"
    assert links[0] == ("Skater NUMBER0", f"{scraper.BASE_URL}/isufs00000000.htm")
    assert all("fsbios" not in url for _, url in links)


def test_bio_links_refuses_a_near_empty_list(site):
    site({LIST_URL: list_page(50)})
    with pytest.raises(AssertionError, match="suspiciously few"):
        scraper.bio_links("men")


def test_bio_links_does_not_swallow_a_dropped_list_page(site, sleeps):
    site({LIST_URL: list_page(60)}, drops={LIST_URL: scraper.FETCH_ATTEMPTS})
    with pytest.raises(requests.exceptions.ChunkedEncodingError):
        scraper.bio_links("men")


# scrape_bio and is_active


def test_scrape_bio_active_skater(site):
    site({BIO_URL: bio_page()})
    got = scraper.scrape_bio("Petr GUMENNIK", BIO_URL, RULE)
    assert got == {
        "skater": "Petr GUMENNIK",
        "coach": "Veronika Daineko",
        "choreographer": "Nikolai Moroshkin",
    }


@pytest.mark.parametrize("season", SEASONS)
def test_active_by_championship_result_in_either_season(site, season):
    session = site({BIO_URL: bio_page({("European Championship", season): "4"})})
    assert scraper.scrape_bio("A", BIO_URL, RULE), f"a result in {season} counts"
    assert session.calls == [BIO_URL], "no need for the Competition Results page"


def test_active_by_season_best(site):
    session = site({BIO_URL: bio_page({})})
    rule = scraper.ActiveRule(SEASONS, frozenset({BIO_URL}), 2025)
    assert scraper.scrape_bio("A", BIO_URL, rule)
    assert session.calls == [BIO_URL], "no need for the Competition Results page"


@pytest.mark.parametrize(("event", "active"), [("Tallinn Trophy 2025", True), ("Crystal Skate 2026", True)])
def test_active_by_a_recent_event_name(site, event, active):
    session = site({BIO_URL: bio_page({}), CR_URL: cr_page("Cup de Nice 2019", event)})
    assert bool(scraper.scrape_bio("A", BIO_URL, RULE)) is active
    assert session.calls == [BIO_URL, CR_URL]


def test_inactive_when_nothing_is_recent(site):
    site(
        {
            BIO_URL: bio_page({("World Championship", "24/25"): "1"}),
            CR_URL: cr_page("ISU World Championships 2024"),
        }
    )
    assert scraper.scrape_bio("A", BIO_URL, RULE) is None, "last result 24/25, last event named 2024"


def test_inactive_when_events_name_no_year(site):
    site({BIO_URL: bio_page({}), CR_URL: cr_page("ISU CS Denis Ten Memorial Challenge")})
    assert scraper.scrape_bio("A", BIO_URL, RULE) is None


def test_retired_skater_whose_headings_reach_the_season(site):
    site({BIO_URL: RETIRED, CR_URL: cr_page("ISU World Championships 2024")})
    rule = scraper.ActiveRule(("24/25", "25/26"), frozenset(), 2025)
    assert scraper.scrape_bio("A", BIO_URL, rule) is None, "24/25 is a heading, not a result"


def test_scrape_bio_takes_current_coach_not_former(site):
    site({BIO_URL: bio_page(coach="Current Person", former_coach="Old Person")})
    assert scraper.scrape_bio("A", BIO_URL, RULE)["coach"] == "Current Person"


def test_scrape_bio_missing_choreographer(site):
    site({BIO_URL: bio_page(choreographer=None)})
    got = scraper.scrape_bio("A", BIO_URL, RULE)
    assert got["choreographer"] is None
    assert got["coach"] == "Veronika Daineko"


def test_scrape_bio_skips_old_format(site):
    session = site({BIO_URL: OLD_FORMAT_BIO})
    assert scraper.scrape_bio("A", BIO_URL, RULE) is None, "old layout has no coach data"
    assert session.calls == [BIO_URL], "no point checking activity for a bio we can't read"


def test_scrape_bio_skips_a_page_that_keeps_dropping(site, sleeps, capsys):
    site({BIO_URL: bio_page()}, drops={BIO_URL: scraper.FETCH_ATTEMPTS})
    assert scraper.scrape_bio("Petr GUMENNIK", BIO_URL, RULE) is None
    assert "skipping Petr GUMENNIK: ChunkedEncodingError" in capsys.readouterr().out


def test_scrape_bio_skips_when_results_page_keeps_dropping(site, sleeps, capsys):
    site(
        {BIO_URL: bio_page({}), CR_URL: cr_page("Crystal Skate 2026")},
        drops={CR_URL: scraper.FETCH_ATTEMPTS},
    )
    assert scraper.scrape_bio("A", BIO_URL, RULE) is None
    assert "skipping A: ChunkedEncodingError" in capsys.readouterr().out


def test_scrape_bio_recovers_from_one_drop(site, sleeps):
    site({BIO_URL: bio_page()}, drops={BIO_URL: 1})
    assert scraper.scrape_bio("A", BIO_URL, RULE)["coach"] == "Veronika Daineko"


# build_dataframe


def test_build_dataframe():
    rows = [
        {
            "skater": "zed ZULU",
            "coach": "JANE doe",
            "choreographer": None,
            "category": "women",
        },
        {
            "skater": "amy ALPHA",
            "coach": None,
            "choreographer": None,
            "category": "men",
        },  # dropped
        {
            "skater": "bob BRAVO",
            "coach": None,
            "choreographer": "john smith",
            "category": "men",
        },
        {"skater": "al ALPHA", "coach": "x", "choreographer": "y", "category": "men"},
    ]
    df = scraper.build_dataframe(rows)
    assert list(df.columns) == ["Category", "Skater", "Coach", "Choreographer"]
    assert df["Skater"].tolist() == ["Al Alpha", "Bob Bravo", "Zed Zulu"], "sorted by category then skater"
    assert df["Category"].tolist() == ["Men", "Men", "Women"], "title-cased"
    assert df.iloc[2]["Coach"] == "Jane Doe"
    assert pd.isna(df.iloc[1]["Coach"]), "a missing coach stays empty, not the string 'None'"


# main


@pytest.fixture
def full_site(site, monkeypatch, tmp_path):
    """Four disciplines of 60 skaters each, as of TODAY:
    0-19 championship result last season, 20-29 on the season's best list only,
    30-39 a small event named 2025 only, 40-49 retired, 50-59 old-format bios.
    Plus one ice dance team missing from the dance list page, found through the season's best list."""
    monkeypatch.setattr(scraper, "OUTPUT_FILE", tmp_path / "data.csv")
    bio = [f"{scraper.BASE_URL}/isufs{i:08d}.htm" for i in range(60)]
    pages = {season_best_url(cat, y): NOT_FOUND for cat in scraper.CATEGORIES for y in (2025, 2026)}
    pages[season_best_url("men", 2025)] = season_best_page(bio[20:30])
    newcomer = f"{scraper.BASE_URL}/isufs00123484.htm"
    pages[season_best_url("dance", 2026)] = season_best_page([newcomer])
    pages[newcomer] = bio_page()
    pages[newcomer.replace("/isufs", "/isufs_cr_")] = cr_page("ISU Four Continents Championships 2026")
    for category in scraper.CATEGORIES:
        pages[f"{scraper.BASE_URL}/fsbios{category}.htm"] = list_page(60)
    for i, url in enumerate(bio):
        cr = url.replace("/isufs", "/isufs_cr_")
        if i < 20:
            pages[url], pages[cr] = bio_page(), cr_page("National Championships 2026")
        elif i < 30:
            pages[url], pages[cr] = bio_page({}), cr_page("ISU JGP Riga 2025")
        elif i < 40:
            pages[url], pages[cr] = bio_page({}), cr_page("Tallinn Trophy 2025")
        elif i < 50:
            pages[url], pages[cr] = RETIRED, cr_page("ISU World Championships 2024")
        else:
            pages[url] = OLD_FORMAT_BIO
    return lambda drops=None: site(pages, drops)


def test_main_writes_active_skaters(full_site, capsys):
    full_site()
    scraper.main(TODAY)
    df = pd.read_csv(scraper.OUTPUT_FILE)
    assert len(df) == 4 * 40 + 1, "each of the three ways of counting as active, in every discipline"
    assert df["Category"].value_counts().to_dict() == {"Dance": 41, "Men": 40, "Pairs": 40, "Women": 40}
    out = capsys.readouterr().out
    assert "season's best in 25/26 or 26/27, or any event named 2025 or later" in out
    assert "dance: 60 on the list page, 1 more from the season's best lists" in out
    assert "Wrote 161 skaters" in out


def test_main_survives_one_bio_that_keeps_dropping(full_site, sleeps):
    full_site(drops={f"{scraper.BASE_URL}/isufs00000000.htm": 99})
    scraper.main(TODAY)
    assert len(pd.read_csv(scraper.OUTPUT_FILE)) == 4 * 39 + 1, "that skater is missing, the rest are saved"


def test_main_shrink_guard_keeps_old_file(full_site):
    old = pd.DataFrame(
        {
            "Category": ["Men"] * 400,
            "Skater": range(400),
            "Coach": "x",
            "Choreographer": "y",
        }
    )
    old.to_csv(scraper.OUTPUT_FILE, index=False)
    before = scraper.OUTPUT_FILE.read_text()
    full_site()
    with pytest.raises(AssertionError, match="suspicious shrink"):
        scraper.main(TODAY)  # 161 new rows vs 400 old: lost more than 40%
    assert scraper.OUTPUT_FILE.read_text() == before, "old data.csv left untouched"


def test_main_shrink_guard_allows_normal_change(full_site):
    old = pd.DataFrame(
        {
            "Category": ["Men"] * 200,
            "Skater": range(200),
            "Coach": "x",
            "Choreographer": "y",
        }
    )
    old.to_csv(scraper.OUTPUT_FILE, index=False)
    full_site()
    scraper.main(TODAY)  # 161 vs 200 = 80% kept
    assert len(pd.read_csv(scraper.OUTPUT_FILE)) == 161


def test_main_refuses_when_nobody_is_active(full_site, monkeypatch):
    full_site()
    monkeypatch.setattr(
        scraper,
        "active_rule",
        lambda today, season_best: scraper.ActiveRule(("38/39", "39/40"), frozenset(), 2039),
    )
    with pytest.raises(AssertionError, match="no active skaters"):
        scraper.main(TODAY)
    assert not scraper.OUTPUT_FILE.exists()
